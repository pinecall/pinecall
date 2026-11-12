"""A worker's call open at a served gateway: written, sealed, each batch landing once, its commands each once."""

import asyncio
import json

import httpx
import pytest

from runtime.calls.log.store import Store
from runtime.calls.service import lists
from runtime.exceptions import UpstreamError
from runtime.jobs.service import call_client
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.client import GatewayClient
from runtime.kit import sse
from runtime.session.service import ToolUse
from runtime.session.writing import Writing
from runtime.wire.base import Command
from runtime.wire.events import Custom
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received
from tests.jobs.factories import opened, opening_of


def writing_on(worker: CallClient) -> Writing:
    """The call's writer wired to its batches, as a worker wires it."""
    return Writing(worker.append_many, worker.call)


def custom(name: str) -> Custom:
    """An app's own line, named."""
    return Custom(name=name, data={})


async def names_in(store: Store, call: str) -> list[str]:
    """The names of the app's lines in the call's log, in log order."""
    return [str(entry.data["name"]) for entry in await store.whole_of(call) if entry.type == "custom"]


async def taken(store: Store, call: str) -> int:
    """How many entries the call's log took from its writer's batches."""
    async with store.sessions() as session:
        return await lists.count_taken(session, call)


@needs_the_services
async def test_a_call_opened_writes_and_seals_through_the_client(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """Open, one line, seal: the line is the second entry, and the log is sealed."""
    worker = await opened(fleet, tenant, agent)
    writing = writing_on(worker)
    writing.open()
    written = await writing.write("custom", custom("x"))
    await writing.close(5)
    await worker.seal([], "done")
    assert worker.opened is not None and worker.opened.seconds_left is None
    assert written.seq == 2
    assert await store.is_sealed(worker.call)


# A gateway that died with the open or the seal in flight: the worker asks again, the call is one.
@needs_the_services
async def test_an_open_asked_again_is_the_same_call_and_a_seal_asked_again_is_done(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """Asked twice, the open rings once and the seal summarizes once."""
    opening = opening_of(tenant, agent)
    await open_call(fleet, opening)
    worker = await open_call(fleet, opening)
    await worker.seal([], "done")
    await worker.seal([], "done")
    kinds = [entry.type for entry in await store.whole_of(worker.call)]
    assert kinds.count("call.ringing") == 1
    assert kinds.count("call.summary") == 1


@needs_the_services
async def test_a_calls_lines_written_before_and_after_the_writer_opens_land_once_and_in_order(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """Lines queued before the writer opens go first, then the rest, each once."""
    worker = await opened(fleet, tenant, agent)
    writing = writing_on(worker)
    writing.write("custom", custom("uno"))
    writing.write("custom", custom("dos"))
    writing.open()
    await writing.write("custom", custom("tres"))
    await writing.close(5)
    assert await names_in(store, worker.call) == ["uno", "dos", "tres"]
    assert await taken(store, worker.call) == 3
    assert writing.refused == []
    await worker.aclose()


@needs_the_services
async def test_a_calls_batches_go_down_one_socket_until_the_seal_closes_it(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """The first batch opens the call's socket, the next uses it, and the seal closes it."""
    worker = await opened(fleet, tenant, agent)
    writing = writing_on(worker)
    writing.open()
    await writing.write("custom", custom("uno"))
    socket = worker.entries.socket
    assert socket is not None, "the first batch opened the call's socket"
    await writing.write("custom", custom("dos"))
    assert worker.entries.socket is socket, "the second went down the same socket"
    await writing.close(5)
    await worker.seal([], "done")
    assert worker.entries.socket is None
    assert await taken(store, worker.call) == 2


@needs_the_services
async def test_a_socket_lost_mid_call_is_opened_again_and_the_batch_lands_once(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    """The socket drops between two batches: a new one opens and the second batch is written once."""
    worker = await opened(fleet, tenant, agent)
    writing = writing_on(worker)
    writing.open()
    await writing.write("custom", custom("uno"))
    first = worker.entries.socket
    assert first is not None
    await first.close()
    entry = await writing.write("custom", custom("dos"))
    await writing.close(5)
    second = worker.entries.socket
    assert second is not None
    assert second is not first
    assert await names_in(store, worker.call) == ["uno", "dos"]
    assert entry.seq == (await store.whole_of(worker.call))[-1].seq
    assert writing.refused == []
    await worker.aclose()


# The worker's scope rides the query of every endpoint it asks: the leg and cold-transfer ones read
# their query into a model that refused it, and every dial on production failed (2026-11-05).
@needs_the_services
async def test_the_leg_and_the_cold_transfer_take_the_workers_scope_in_their_query(
    gateway: Gateway, fleet: GatewayClient, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        worker = await opened(fleet, tenant, agent)
        for ask in (worker.leg("+15550100000", None), worker.send_on("+15550100000")):
            # Answered, or refused on the guards in the gateway's words: never on the query's shape.
            try:
                await ask
            except UpstreamError as refused:
                assert refused.answered != 422, str(refused)
                assert "Extra inputs" not in str(refused)
        await worker.seal([], "done")


def kept(*ids: str) -> str:
    """The commands a gateway keeps for the call's worker, each under its id, as its stream sends them."""
    said = (Command(type="state.set", agent="a", call="call_1", id=None, data={"state": {"n": n}}) for n in ids)
    return "".join(sse.frame(one.dump_json(), event=one.type, id_=one.data["state"]["n"]) for one in said)


def a_worker_hearing(*streams: str) -> CallClient:
    """The worker's client of a call whose command stream answers these, one each time it is opened."""
    answers = iter(streams)

    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=next(answers), headers={"content-type": sse.EVENT_STREAM})

    http = httpx.AsyncClient(transport=httpx.MockTransport(answer), base_url="http://gateway")
    return CallClient(GatewayClient(http), "call_1")


# Every gateway that serves a call keeps its commands for the worker: when the stream moved to a
# second gateway (the first was replaced by a deploy), the worker applied again all the first had sent.
async def test_a_command_a_second_gateway_sends_again_is_handed_to_the_call_once() -> None:
    worker = a_worker_hearing(kept("c1", "c2"), kept("c1", "c2", "c3"))
    try:
        first = [command.data["state"]["n"] async for command in worker.commands()]
        second = [command.data["state"]["n"] async for command in worker.commands()]
    finally:
        await worker.gateway.aclose()
    assert (first, second) == (["c1", "c2"], ["c3"])


# A frame of the command stream this worker cannot read (a gateway newer than it) ended the stream with
# an exception its follower did not retry: the call was deaf to every command after it.
async def test_a_command_frame_this_worker_cannot_read_is_skipped_and_the_next_is_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unread = sse.frame('{"type": 7}', event="whatever", id_="c0")
    worker = a_worker_hearing(unread + kept("c1"))
    try:
        heard = [command.type async for command in worker.commands()]
    finally:
        await worker.gateway.aclose()
    assert heard == ["state.set"]
    assert "reading a command of the app failed on call_1" in caplog.text


# A gateway older than the worker never says a tool settled: its answer is held a moment, said so, and
# given to the model all the same, as before the worker waited at all.
@needs_the_services
async def test_a_tools_answer_from_a_gateway_that_says_nothing_goes_on_after_the_wait(
    fleet: GatewayClient,
    gateway: Gateway,
    tenant: Tenant,
    agent: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(call_client, "SETTLED_WITHIN_S", 0.2)
    async with holding(gateway, tenant, agent) as app:
        worker = await opened(fleet, tenant, agent)
        # Nobody follows the call's stream: what it says of the tool is never read.
        asking = asyncio.create_task(worker.run_tool(ToolUse("t1", "book", {}), None))
        await received(app, "tool.call")
        answer = {"call_id": "t1", "name": "book", "output": "booked"}
        await app.send(json.dumps({"type": "tool.result", "agent": agent, "call": worker.call, "data": answer}))
        result = await asyncio.wait_for(asking, 10)
        await worker.seal([], "done")
        await worker.aclose()
    assert result.output == "booked"
    assert "the stream never said the commands before book's answer came" in caplog.text
