"""The worker's client on a served gateway: a call opened, written, sealed, and every batch landing once."""

import secrets
from dataclasses import dataclass, field
from datetime import date
from functools import partial

import httpx
import pytest

from pinecall_runtime.calls.context import CallContext, Route, new_call_id
from pinecall_runtime.calls.schemas import OpenCallRequest, SealCallRequest
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.fleet.schemas import HeartbeatRequest
from pinecall_runtime.jobs.service.client import GatewayClient, _command_of, gateway_at
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.session.writing import Writing
from pinecall_runtime.wire.events import Custom
from tests.conftest import Gateway, Tenant, needs_the_services

pytestmark = needs_the_services


def a_call(tenant: Tenant, agent: str) -> CallContext:
    """A sandbox call of the tenant's agent through the widget."""
    return CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller="web_1",
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 10, 16),
    )


def writing_on(client: GatewayClient, call: str) -> Writing:
    """A call's writer wired to the client's batch door, as a worker wires it."""
    return Writing(partial(client.append_many, call), call)


def custom(name: str) -> Custom:
    """An app's own line, named."""
    return Custom(name=name, data={})


async def names_in(store: Store, call: str) -> list[str]:
    """The names of the app's lines in the call's log, in log order."""
    return [str(entry.data["name"]) for entry in await store.whole(call) if entry.type == "custom"]


async def test_a_call_opened_writes_and_seals_through_the_client(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """Open, one line, seal: the line is the second entry, the log is sealed, and the client lets go."""
    context = a_call(tenant, agent)
    opened = await fleet.open(OpenCallRequest(agent=agent, context=context))
    writing = writing_on(fleet, context.call)
    writing.open()
    written = await writing.write("custom", custom("x"))
    await writing.close(5)
    await fleet.sealed(context.call, SealCallRequest(usage=[], outcome="done"))
    assert opened.seconds_left is None
    assert written.seq == 2
    assert await store.is_sealed(context.call)
    assert context.call not in fleet.opened


# A gateway that died with the open or the seal in flight: the worker asks again, the call is one.
async def test_an_open_asked_again_is_the_same_call_and_a_seal_asked_again_is_done(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """Asked twice, the open rings once and the seal summarizes once."""
    context = a_call(tenant, agent)
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    await fleet.sealed(context.call, SealCallRequest(usage=[], outcome="done"))
    fleet.opened[context.call] = OpenCallRequest(agent=agent, context=context)
    await fleet.sealed(context.call, SealCallRequest(usage=[], outcome="done"))
    kinds = [entry.type for entry in await store.whole(context.call)]
    assert kinds.count("call.ringing") == 1
    assert kinds.count("call.summary") == 1
    assert context.call not in fleet.opened


async def test_a_calls_lines_written_before_and_after_the_writer_opens_land_once_and_in_order(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """Lines queued before the writer opens go first, then the rest, each once."""
    context = a_call(tenant, agent)
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    writing = writing_on(fleet, context.call)
    writing.write("custom", custom("uno"))
    writing.write("custom", custom("dos"))
    writing.open()
    await writing.write("custom", custom("tres"))
    await writing.close(5)
    assert await names_in(store, context.call) == ["uno", "dos", "tres"]
    assert await store.taken_count(context.call) == 3
    assert writing.refused == []


async def test_a_calls_batches_go_down_one_socket_until_the_seal_closes_it(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """The first batch opens the call's socket, the next uses it, and the seal closes it."""
    context = a_call(tenant, agent)
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    writing = writing_on(fleet, context.call)
    writing.open()
    await writing.write("custom", custom("uno"))
    stream = fleet.streams[context.call]
    assert stream.socket is not None, "the first batch opened the call's socket"
    await writing.write("custom", custom("dos"))
    assert fleet.streams[context.call] is stream, "the second went down the same socket"
    await writing.close(5)
    await fleet.sealed(context.call, SealCallRequest(usage=[], outcome="done"))
    assert context.call not in fleet.streams
    assert stream.socket is None
    assert await store.taken_count(context.call) == 2


async def test_a_socket_lost_mid_call_is_opened_again_and_the_batch_lands_once(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """The socket drops between two batches: a new one opens and the second batch is written once."""
    context = a_call(tenant, agent)
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    writing = writing_on(fleet, context.call)
    writing.open()
    await writing.write("custom", custom("uno"))
    first = fleet.streams[context.call].socket
    assert first is not None
    await first.close()
    entry = await writing.write("custom", custom("dos"))
    await writing.close(5)
    second = fleet.streams[context.call].socket
    assert second is not None
    assert second is not first
    assert await names_in(store, context.call) == ["uno", "dos"]
    assert entry.seq == (await store.whole(context.call))[-1].seq
    assert writing.refused == []


@dataclass
class LosingTheFirstBatchAnswer:
    """The real transport, but the answer to the first batch is lost after the gateway took it."""

    real: httpx.AsyncHTTPTransport = field(default_factory=httpx.AsyncHTTPTransport)
    lost: int = 0

    async def handled(self, request: httpx.Request) -> httpx.Response:
        """Pass the request on; drop the first answer to a batch, as a broken connection would."""
        answer = await self.real.handle_async_request(request)
        if not request.url.path.endswith("/entries") or self.lost:
            return answer
        await answer.aread()
        await answer.aclose()
        self.lost += 1
        raise httpx.ReadError("the answer was lost on the way back", request=request)


async def test_a_batch_whose_answer_was_lost_is_sent_again_and_lands_once(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    """The gateway took the batch and its answer never came: sent again, it is written once."""
    losing = LosingTheFirstBatchAnswer()
    headers = dict(fleet.http.headers)
    client = GatewayClient(
        httpx.AsyncClient(base_url=gateway.url, headers=headers, transport=httpx.MockTransport(losing.handled))
    )
    # The batches by request, as a client sends them to a gateway with no socket endpoint: the
    # transport loses that answer, and the socket's own loss is the stream's to test.
    client.unserved = True
    context = a_call(tenant, agent)
    await client.open(OpenCallRequest(agent=agent, context=context))
    writing = writing_on(client, context.call)
    names = ["uno", "dos", "tres"]
    written = [writing.write("custom", custom(name)) for name in names]
    writing.open()
    await writing.close(5)
    customs = [entry for entry in await store.whole(context.call) if entry.type == "custom"]
    assert losing.lost == 1
    assert [str(entry.data["name"]) for entry in customs] == names
    assert [future.result().seq for future in written] == [entry.seq for entry in customs]
    await client.aclose()
    await losing.real.aclose()


async def test_a_heartbeat_says_the_fleet_is_open(fleet: GatewayClient) -> None:
    """A worker of the sandbox fleet that reports in is neither cordoned nor full."""
    beat = HeartbeatRequest(
        fleet="pinecall-sandbox", worker=f"w-{secrets.token_hex(3)}", active=0, max_jobs=4, load=0.1, draining=False
    )
    answered = await fleet.heartbeat(beat)
    assert not answered.cordoned
    assert not answered.full


async def test_a_refusal_names_the_request_refused_and_its_status(fleet: GatewayClient, tenant: Tenant) -> None:
    """The gateway's 404 comes back as one sentence naming the door, with the status beside it."""
    with pytest.raises(GatewayUnavailable, match="/v1/agents/nobody/config") as refused:
        await fleet.agent("nobody", Scope(tenant.org, Env.sandbox))
    assert refused.value.answered == 404


async def test_a_gateway_that_is_not_there_is_a_refusal_and_never_a_traceback() -> None:
    """Nobody answering at the address is a refusal with no status, never a crash."""
    client = gateway_at("http://127.0.0.1:9", "pc_test_x")
    with pytest.raises(GatewayUnavailable) as refused:
        await client.heartbeat(
            HeartbeatRequest(fleet="pinecall", worker="w1", active=0, max_jobs=4, load=0.0, draining=False)
        )
    assert refused.value.answered is None
    await client.aclose()


# A frame of the command stream this worker cannot read (a gateway newer than it) ended the stream with
# an exception its follower did not retry: the call was deaf to every command after it.
def test_a_command_frame_this_worker_cannot_read_is_skipped_and_one_it_can_is_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert _command_of({"type": 7}, "call_1") is None
    read = _command_of(
        {"type": "state.set", "agent": "clinica-norte", "call": "call_1", "id": None, "data": {}}, "call_1"
    )
    assert read is not None and read.type == "state.set"
    assert "reading a command of the app failed on call_1" in caplog.text
