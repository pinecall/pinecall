"""A worker's endpoints on its call: what they take, and what the seal does with it."""

import asyncio
import json
import time
from datetime import date

import pytest
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.room import RoomParticipantIdentity

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
from tests.conftest import THE_FLEET_KEY, Gateway, Tenant, holding, needs_the_services, received, until, used_of
from tests.fakes.livekit import Server
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


A_START: JsonObject = {**NO_CALLER, "caller": None, "medium": "voice", "started_at": 100.0}


def said(kind: str, text: str) -> BatchedEntry:
    """A turn of the call as its worker's writer sends it."""
    return BatchedEntry(type=kind, data={"text": text}, ts=time.time())


async def left_by_its_worker(fleet: GatewayClient, tenant: Tenant, agent: str) -> CallClient:
    """A call a worker opened, started and spoke two turns of, and then went away from."""
    first = await opened(fleet, tenant, agent)
    started = BatchedEntry(type="call.started", data=A_START, ts=time.time())
    turns = [started, said("turn.user", "I was charged twice."), said("turn.agent", "Let me look at that.")]
    await first.append_many(turns, after=0)
    return first


async def test_a_call_whose_worker_went_away_is_handed_whole_to_the_worker_that_takes_it_up(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store, livekit: Server
) -> None:
    """The caller alone in the room: the taker is told how the call opened, what was said and where its log
    stands, and the log says once that the worker went away."""
    first = await left_by_its_worker(fleet, tenant, agent)
    call = first.call
    livekit.rooms.people = {call}
    taken = await fleet.take_up(call)
    assert (taken.opening.agent, taken.opening.context.call) == (agent, call)
    assert (taken.medium, taken.started_at) == ("voice", 100.0)
    assert [(entry.type, entry.data["text"]) for entry in taken.history] == [
        ("turn.user", "I was charged twice."),
        ("turn.agent", "Let me look at that."),
    ]
    # The gateway's word of the loss is the writer's fourth entry: the taker's writer follows on from it.
    assert (taken.written, taken.taken_up) == (4, 1)
    lost = [entry.data for entry in await store.whole_of(call) if entry.type == "error"]
    assert [(one["code"], one["recoverable"]) for one in lost] == [("worker_lost", True)]
    await first.aclose()


# A worker lost to its room for a while is not dead: when it comes back it ends "its" call. The count
# of the log answers its late batch as one already taken, and its seal is refused as another's.
async def test_the_worker_a_call_was_taken_from_can_no_longer_end_it(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store, livekit: Server
) -> None:
    first = await left_by_its_worker(fleet, tenant, agent)
    call = first.call
    livekit.rooms.people = {call}
    taken = await fleet.take_up(call)
    late = BatchedEntry(type="call.ended", data=AN_END, ts=time.time())
    await first.append_many([late], after=3)
    assert "call.ended" not in [entry.type for entry in await store.whole_of(call)]
    await first.seal([], "done")
    assert first.passed_on, "the gateway says the call is another worker's now"
    assert not await store.is_sealed(call)
    second = CallClient(fleet, call, taken.opening)
    second.written, second.taken_up = taken.written, taken.taken_up
    await second.append_many([BatchedEntry(type="call.ended", data=AN_END, ts=time.time())], after=taken.written)
    await second.seal([], "done")
    assert not second.passed_on
    assert await store.is_sealed(call)
    assert not await store.take_up(call, taken.taken_up), "a call that is over is taken up by nobody"
    await first.aclose()
    await second.aclose()


# 2026-11-16, production: a call's stream of commands was cut on one gateway and its take-up was
# answered by the other. The count of take-ups was then the memory of the gateway that answered, and
# the seal of the worker the call was taken from, reaching the other one, ended a call another worker
# ran. The count is the head's: whichever gateway the seal reaches refuses it.
async def test_the_worker_a_call_was_taken_from_is_refused_by_a_gateway_that_did_not_answer_the_take_up(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store, livekit: Server
) -> None:
    first = await left_by_its_worker(fleet, tenant, agent)
    call = first.call
    livekit.rooms.people = {call}
    taken = await fleet.take_up(call)
    async with a_second_gateway() as other:
        elsewhere = open_gateway(other.url, THE_FLEET_KEY)
        late = CallClient(elsewhere, call)
        await late.seal([], "done")
        assert late.passed_on, "the other gateway says the call is another worker's too"
        assert not await store.is_sealed(call)
        second = CallClient(elsewhere, call, taken.opening)
        second.written, second.taken_up = taken.written, taken.taken_up
        await second.seal([], "done")
        assert not second.passed_on
        await late.aclose()
        await second.aclose()
        await elsewhere.aclose()
    assert await store.is_sealed(call)
    await first.aclose()


# Two workers offered one call ask at the same moment, each of a gateway that read the same count:
# one statement moves it, so one of them is answered and the other told the call is taken.
async def test_two_workers_that_ask_for_one_call_at_once_are_not_both_given_it(
    fleet: GatewayClient, tenant: Tenant, agent: str, livekit: Server
) -> None:
    first = await left_by_its_worker(fleet, tenant, agent)
    livekit.rooms.people = {first.call}
    answers = await asyncio.gather(*(fleet.take_up(first.call) for _ in range(4)), return_exceptions=True)
    given = [answer for answer in answers if not isinstance(answer, BaseException)]
    refused = [answer for answer in answers if isinstance(answer, UpstreamError)]
    assert len(given) == 1, answers
    assert [answer.answered for answer in refused] == [410] * 3, answers
    await first.aclose()


async def test_a_call_is_taken_up_only_while_its_caller_waits_alone_and_only_once_it_started(
    fleet: GatewayClient, tenant: Tenant, agent: str, livekit: Server
) -> None:
    """A room with an agent in it, or with nobody, is left as it is (410); a call that never started has
    nothing to go on with (409), and its caller is told instead."""
    first = await left_by_its_worker(fleet, tenant, agent)
    refused = await fleet.http.post(f"/v1/calls/{first.call}/taken-up")
    assert refused.status_code == 410, refused.text
    livekit.rooms.people = {first.call}
    livekit.rooms.existing = {first.call: True}
    refused = await fleet.http.post(f"/v1/calls/{first.call}/taken-up")
    assert refused.status_code == 410, refused.text
    unstarted = await opened(fleet, tenant, agent)
    livekit.rooms.people = {unstarted.call}
    refused = await fleet.http.post(f"/v1/calls/{unstarted.call}/taken-up")
    assert refused.status_code == 409, refused.text
    await first.aclose()
    await unstarted.aclose()


def an_agent(identity: str) -> ParticipantInfo:
    """A job's agent as LiveKit lists it in the call's room."""
    return ParticipantInfo(identity=identity, kind=ParticipantInfo.Kind.AGENT)


# 2026-11-25: a room rung twice under load had two jobs. The second's open was served as the first's
# said again, its first batch was refused, and its seal ended the call in the middle of the first
# job's conversation: four calls of thirty.
async def test_a_second_job_of_the_room_is_refused_the_call_the_first_opened_and_writes_nothing_to_it(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store, livekit: Server
) -> None:
    """The first open stands: a job that finds another agent in the room is told the call has a worker (410),
    and the call is as its opener left it, open and unsealed."""
    context = dump_context(a_call(tenant, agent))
    by_the_first = OpenCallRequest.model_validate({"agent": agent, "context": context, "seat": "agent-AJ_first"})
    by_the_second = OpenCallRequest.model_validate({"agent": agent, "context": context, "seat": "agent-AJ_second"})
    first = await open_call(fleet, by_the_first)
    call = first.call
    await first.append_many([BatchedEntry(type="call.started", data=A_START, ts=time.time())], after=0)
    livekit.rooms.people = {call}
    livekit.rooms.seated = {call: [an_agent("agent-AJ_first"), an_agent("agent-AJ_second")]}
    with pytest.raises(UpstreamError, match="has a worker already") as refused:
        await open_call(fleet, by_the_second)
    assert refused.value.answered == 410 and not refused.value.retryable
    assert [entry.type for entry in await store.whole_of(call)] == ["call.ringing", "call.started"]
    assert not await store.is_sealed(call)
    # The call goes on in the job that opened it.
    await first.append_many([said("turn.agent", "Clínica Norte, buen día.")], after=1)
    await first.seal([], "done")
    assert await store.is_sealed(call)


# What an open said again was before the refusal, and still is: a worker whose gateway died with the
# answer asks again and is answered, the one agent in its room; a worker that names no seat (a release
# before 2026-11-25) is answered whoever sits there.
async def test_an_open_said_again_by_the_job_that_sits_alone_in_the_room_is_answered(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store, livekit: Server
) -> None:
    context = dump_context(a_call(tenant, agent))
    by_the_first = OpenCallRequest.model_validate({"agent": agent, "context": context, "seat": "agent-AJ_first"})
    first = await open_call(fleet, by_the_first)
    call = first.call
    livekit.rooms.people = {call}
    livekit.rooms.seated = {call: [an_agent("agent-AJ_first")]}
    again = await open_call(fleet, by_the_first)
    livekit.rooms.seated = {call: [an_agent("agent-AJ_first"), an_agent("agent-AJ_second")]}
    unnamed = await open_call(fleet, OpenCallRequest.model_validate({"agent": agent, "context": context}))
    assert [entry.type for entry in await store.whole_of(call)] == ["call.ringing"]
    for worker in (first, again, unnamed):
        await worker.aclose()


async def follow_then_die(worker: CallClient) -> None:
    """The worker reads its call's commands for a moment, and is cut off as a killed process is."""

    async def read() -> None:
        async for _ in worker.commands():
            return

    reading = asyncio.create_task(read())
    await asyncio.sleep(0.5)
    reading.cancel()
    await asyncio.gather(reading, return_exceptions=True)


# LiveKit takes some twenty seconds to say an agent is gone; the stream of commands its worker read
# is cut the moment the worker dies. The gateway waits a second and a half for it to be opened again, then
# takes the agent out of the room and offers the call: a caller waits seconds, not half a minute.
@pytest.mark.timeout(30)
async def test_a_call_whose_worker_stops_reading_its_commands_is_handed_on_within_seconds(
    fleet: GatewayClient, tenant: Tenant, agent: str, livekit: Server
) -> None:
    first = await left_by_its_worker(fleet, tenant, agent)
    livekit.rooms.people, livekit.rooms.existing = {first.call}, {first.call: True}
    await follow_then_die(first)

    def removed() -> list[RoomParticipantIdentity]:
        return [asked for asked in livekit.rooms.requests if isinstance(asked, RoomParticipantIdentity)]

    await until(lambda: bool(removed()), within_s=8)
    assert [(asked.room, asked.identity) for asked in removed()] == [(first.call, "agent")]
    # A call that ended as its worker left is nobody's to hand on: its end is on the log.
    ended = await left_by_its_worker(fleet, tenant, agent)
    await ended.append_many([BatchedEntry(type="call.ended", data=AN_END, ts=time.time())], after=3)
    livekit.rooms.people, livekit.rooms.existing = {ended.call}, {ended.call: True}
    await follow_then_die(ended)
    await asyncio.sleep(3)
    assert [asked.room for asked in removed()] == [first.call]
    await first.aclose()
    await ended.aclose()
