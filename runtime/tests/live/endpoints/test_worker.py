"""A worker's endpoints on its call: what they take, and what the seal does with it."""

import asyncio
import json
import time
from datetime import date

import pytest

from runtime.calls.context import CallContext, Route, dump_context, new_call_id
from runtime.calls.log.store import Store
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import UpstreamError
from runtime.jobs.service.arrival import TEST_VALUES_ON_THE_WIRE
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.client import GatewayClient, open_gateway
from runtime.kit.text import JsonObject
from runtime.live.parts import LiveParts
from runtime.live.service import reaper
from runtime.session.service import ToolUse
from runtime.wire.base import BatchedEntry
from runtime.wire.worker import OpenCallRequest, SealCallRequest
from tests.conftest import THE_FLEET_KEY, Gateway, Tenant, holding, needs_the_services, received, used_of
from tests.live.gateways import a_second_gateway

pytestmark = needs_the_services

NO_CALLER: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica-norte",
    "started_at": 1.0,
}
AN_END: JsonObject = {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 5.0, "duration_s": 4.0}
SEALING = SealCallRequest(usage=[], outcome="done")


def a_call(tenant: Tenant, agent: str) -> CallContext:
    """A sandbox call of the tenant's agent through the widget."""
    return CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller="web_1",
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 10, 23),
    )


async def opened(fleet: GatewayClient, tenant: Tenant, agent: str, **test_values: str) -> CallClient:
    """A call of the tenant's agent a worker opened at the gateway, run on the test values given."""
    said = {
        "agent": agent,
        "context": dump_context(a_call(tenant, agent)),
        TEST_VALUES_ON_THE_WIRE: test_values or None,
    }
    return await open_call(fleet, OpenCallRequest.model_validate(said))


# 2026-11-06: a comparison row in Arabic opened with "This call may be recorded." in English, because the
# worker opened the call without the row's language and the gateway read the team's, unset.
async def test_a_call_opens_with_its_first_words_in_the_language_the_worker_runs_it_in(
    fleet: GatewayClient, tenant: Tenant, agent: str
) -> None:
    plain = await opened(fleet, tenant, agent)
    assert plain.opened is not None and plain.opened.recording_notice == "This call may be recorded."
    arabic = await opened(fleet, tenant, agent, language="ar")
    assert arabic.opened is not None and arabic.opened.recording_notice == "قد يتم تسجيل هذه المكالمة."


# M B10 (2026-10-23): the endpoints took a call.started with no `caller` (`Contact | null`, required
# by wire/events-call.md), and the seal of its call answered 500 for ever, the call holding its seat.
async def test_a_call_started_with_no_caller_is_refused_by_every_endpoint_that_writes_and_nothing_is_written(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    worker = await opened(fleet, tenant, agent)
    call = worker.call

    one = await fleet.http.post(f"/v1/calls/{call}/events", json={"type": "call.started", "data": NO_CALLER})
    assert one.status_code == 400 and "caller" in one.json()["detail"]

    lines: list[JsonObject] = [
        {"type": "custom", "data": {"name": "first", "data": {}}, "ts": time.time()},
        {"type": "call.started", "data": NO_CALLER, "ts": time.time()},
    ]
    batch = await fleet.http.post(f"/v1/calls/{call}/entries", json={"after": 0, "entries": lines})
    assert batch.status_code == 400 and "caller" in batch.json()["detail"]

    with pytest.raises(UpstreamError, match="caller") as socket:
        await worker.append_many([BatchedEntry(type="call.started", data=NO_CALLER, ts=time.time())], after=0)
    assert socket.value.answered == 400

    assert [entry.type for entry in await store.whole_of(call)] == ["call.ringing"]
    answered = await fleet.http.post(
        f"/v1/calls/{call}/events", json={"type": "call.started", "data": {**NO_CALLER, "caller": None}}
    )
    assert answered.status_code == 200, answered.text
    await worker.seal([], "done")
    assert await store.is_sealed(call)


async def test_a_call_whose_start_the_log_took_before_the_endpoints_read_it_is_sealed_all_the_same(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    """A log written before the refusal holds one: its seal writes the summary and the score, and lets go."""
    worker = await opened(fleet, tenant, agent)
    call = worker.call
    assert await used_of(gateway, tenant, "concurrent_calls") == 1
    await store.write("entry", call, agent, "call.started", NO_CALLER)
    await store.write("entry", call, agent, "call.ended", AN_END)
    sealed = await fleet.http.post(f"/v1/calls/{call}/sealed", json=SEALING.dump())
    assert sealed.status_code == 204, sealed.text
    kinds = [entry.type for entry in await store.whole_of(call)]
    assert kinds[-2:] == ["call.summary", "call.score"]
    assert await store.is_sealed(call)
    assert await used_of(gateway, tenant, "concurrent_calls") == 0, "a sealed call holds no seat"
    await worker.aclose()


# The balancer hashes a call's requests to one gateway, but `POST /v1/calls` names no call, so the
# gateway that opened a call and the one its worker seals it on are the same only half the time. The
# seat is the opener's memory of the call: it leaves at the opener's next pass over what is over,
# which the reaper's loop runs every minute and this test runs itself.
async def test_a_call_the_other_gateway_sealed_is_let_go_by_the_one_that_opened_it(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    live: LiveParts = gateway.state["live"]
    async with a_second_gateway() as other:
        sealer = open_gateway(other.url, THE_FLEET_KEY)
        worker = await opened(fleet, tenant, agent)
        await CallClient(sealer, worker.call).seal([], "done")
        await sealer.aclose()
    assert await store.is_sealed(worker.call)
    await reaper.let_go(live, time.monotonic())
    assert worker.call not in live.calls.holding(tenant.org, Env.sandbox)
    await worker.aclose()


async def test_a_call_erased_after_the_other_gateway_sealed_it_holds_no_seat_either(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Erasing the stuck calls of the eval freed none of their seats: the head the pass looked for was gone."""
    live: LiveParts = gateway.state["live"]
    async with a_second_gateway() as other:
        sealer = open_gateway(other.url, THE_FLEET_KEY)
        worker = await opened(fleet, tenant, agent)
        await CallClient(sealer, worker.call).seal([], "done")
        await sealer.aclose()
    erased = await gateway.http.delete(f"/v1/calls/{worker.call}", headers=tenant.person)
    assert erased.status_code == 200, erased.text
    await reaper.let_go(live, time.monotonic())
    assert worker.call not in live.calls.holding(tenant.org, Env.sandbox)
    await worker.aclose()


# S2 (2026-10-23): what an app logs from its end hook lands only before call.score. A worker's call is
# sealed by the gateway while its session is in the worker: the app's word comes down the commands stream
# to the session, which says it to the gateway on `/done`, and the seal that waited goes on.
async def test_a_seal_waits_for_the_app_that_says_done_until_the_worker_says_it_on_done(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    async with holding(gateway, tenant, agent, says_done=True):
        worker = await opened(fleet, tenant, agent)
        sealing = asyncio.create_task(worker.seal([], "done"))
        waited, _ = await asyncio.wait({sealing}, timeout=0.5)
        assert not waited and not await store.is_sealed(worker.call), "the seal waits for the app's word"
        await worker.release_seal()
        await asyncio.wait_for(sealing, 30)
    assert await store.is_sealed(worker.call)


async def test_the_apps_word_for_a_call_sealed_already_is_taken_without_an_error(
    fleet: GatewayClient, tenant: Tenant, agent: str
) -> None:
    worker = await opened(fleet, tenant, agent)
    await worker.seal([], "done")
    await worker.release_seal()


# A tool's answer came back on the worker's own request while the commands its app had sent before it
# were still crossing Redis to the worker's stream: the model's next step read the prompt and the tools
# of before the tool ran, and a call passed to a teammate answered as the agent it had left (2026-11-13).
async def test_a_tools_answer_reaches_the_worker_after_the_commands_its_app_sent_before_it(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent) as app:
        worker = await opened(fleet, tenant, agent)
        applied: list[str] = []

        async def follow() -> None:
            async for command in worker.commands():
                # A command takes a moment to apply: a prompt rendered, a stage built.
                await asyncio.sleep(0.05)
                applied.append(str(command.data["name"]))

        following = asyncio.create_task(follow())
        asking = asyncio.create_task(worker.run_tool(ToolUse("t1", "pass", {}), None))
        await received(app, "tool.call")
        for block in ("identity", "tools", "view"):
            said = {"type": "prompt.set", "agent": agent, "call": worker.call, "data": {"name": block, "text": "…"}}
            await app.send(json.dumps(said))
        answer = {"call_id": "t1", "name": "pass", "output": "passed"}
        await app.send(json.dumps({"type": "tool.result", "agent": agent, "call": worker.call, "data": answer}))
        result = await asyncio.wait_for(asking, 10)
        taken_before_the_answer = list(applied)
        following.cancel()
        await worker.seal([], "done")
        await worker.aclose()
    assert result.output == "passed"
    assert taken_before_the_answer == ["identity", "tools", "view"]
