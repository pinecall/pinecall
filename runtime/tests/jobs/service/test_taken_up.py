"""A call whose worker went away, on the worker that takes its job: gone on with from its log, or left as it is."""

import asyncio
import json
import time
from datetime import date
from pathlib import Path

import pytest
from livekit.agents.utils import http_context
from livekit.protocol.room import DeleteRoomRequest

from runtime.calls.context import CallContext, Route, dump_context, new_call_id
from runtime.enums import Channel, Direction, Env
from runtime.jobs.service import answer_job, end_job, take_job, take_up_job
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.taken_up import STAY_ON_THE_LINE
from runtime.kit.text import JsonObject
from runtime.wire.base import BatchedEntry
from runtime.wire.dispatch import Dispatch
from runtime.wire.room import SCOPE_ATTRIBUTE, TALK
from runtime.wire.worker import OpenCallRequest
from tests.conftest import Gateway, Tenant, holding, needs_the_services, until
from tests.fakes.livekit import Server, Speaker, seat
from tests.jobs.service.test_answer import Assigned, ConnectedRoom, hear_to_the_end, warmed_for

THE_VISITOR = "visitor_1"
STARTED_AT = time.time() - 40.0
ASKED = "I was charged twice."
ANSWERED = "Let me look at that."


def entry(kind: str, data: JsonObject) -> BatchedEntry:
    """An entry of the call as its first worker's writer sent it."""
    return BatchedEntry(type=kind, data=data, ts=time.time())


async def left_by_its_worker(fleet: GatewayClient, tenant: Tenant, agent: str) -> CallClient:
    """A widget call a worker opened, started and spoke two turns of before it went away."""
    context = CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller=THE_VISITOR,
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 11, 16),
    )
    first = await open_call(fleet, OpenCallRequest.model_validate({"agent": agent, "context": dump_context(context)}))
    started: JsonObject = {
        "channel": "web",
        "direction": "inbound",
        "from": THE_VISITOR,
        "to": agent,
        "caller": None,
        "started_at": STARTED_AT,
        "medium": "voice",
    }
    turns = [
        entry("call.started", started),
        entry("turn.user", {"text": ASKED}),
        entry("turn.agent", {"text": ANSWERED}),
    ]
    await first.append_many(turns, after=0)
    return first


def gone(tenant: Tenant, agent: str) -> Dispatch:
    """What the gateway sends the fleet for a call whose worker went away."""
    return Dispatch(
        agent=agent, org=tenant.org, env=Env.sandbox, worker_gone=True, entries_written=3, started_at=STARTED_AT
    )


# The whole of it: the gateway hands the call over, the session opens on what was said, the caller
# hears first that the line had a problem, and the call ends once, as any call does.
@pytest.mark.timeout(60)
@needs_the_services
async def test_a_call_whose_worker_went_away_goes_on_in_another_worker_its_caller_told_first(
    gateway: Gateway, fleet: GatewayClient, tenant: Tenant, agent: str, livekit: Server, tmp_path: Path
) -> None:
    """The same call, the same log: no second start, the loss said once, the sentence, then the call's own end."""
    async with http_context.open(), holding(gateway, tenant, agent) as app:
        first = await left_by_its_worker(fleet, tenant, agent)
        call = first.call
        # The worker is gone and its caller waits alone in the room.
        livekit.rooms.people = {call}
        room = ConnectedRoom(call, seat(THE_VISITOR, attributes={SCOPE_ATTRIBUTE: TALK}))
        ctx = Assigned(room, livekit, gone(tenant, agent))
        warmed = warmed_for(fleet, tmp_path)
        await take_job(ctx, warmed, answer_job, take_up_job)
        job = warmed.job
        assert job is not None and job.link.call == call
        speaker = Speaker()
        job.setup.running.live.output.audio = speaker
        listening = asyncio.create_task(hear_to_the_end(speaker))
        try:
            await until(lambda: speaker.frames > 0, within_s=10)
            hangup = {"type": "call.hangup", "agent": agent, "call": call, "data": {"reason": "done"}}
            await app.send(json.dumps(hangup))
            await until(lambda: bool(ctx.shutdowns), within_s=10)
            await end_job(warmed)
        finally:
            listening.cancel()
            await ctx.finish()
            await first.aclose()
    entries = await gateway.http.get(f"/v1/calls/{call}/events", params={"durable": True}, headers=tenant.server)
    page = entries.json()
    kinds = [one["type"] for one in page["entries"]]
    assert not page["live"], kinds
    assert (kinds.count("call.started"), kinds.count("call.ended")) == (1, 1), kinds
    lost = [one["data"]["code"] for one in page["entries"] if one["type"] == "error"]
    assert lost == ["worker_lost"]
    said = [one["data"]["text"] for one in page["entries"] if one["type"] == "turn.agent"]
    assert said == [ANSWERED, STAY_ON_THE_LINE["en"]]
    ended = next(one["data"] for one in page["entries"] if one["type"] == "call.ended")
    # The call lasted from its first worker's start, not from the second's.
    assert ended["duration_s"] >= 40.0
    assert DeleteRoomRequest(room=call) in livekit.rooms.requests
    assert warmed.job is None


# Two workers may be offered the same call, twelve seconds apart: the second finds an agent in the room.
@pytest.mark.timeout(30)
@needs_the_services
async def test_a_call_another_worker_is_already_on_is_left_as_it_is(
    fleet: GatewayClient, tenant: Tenant, agent: str, livekit: Server, tmp_path: Path
) -> None:
    first = await left_by_its_worker(fleet, tenant, agent)
    call = first.call
    livekit.rooms.people, livekit.rooms.existing = {call}, {call: True}
    ctx = Assigned(ConnectedRoom(call, seat(THE_VISITOR)), livekit, gone(tenant, agent))
    warmed = warmed_for(fleet, tmp_path)
    try:
        await take_job(ctx, warmed, answer_job, take_up_job)
    finally:
        await ctx.finish()
        await first.aclose()
    assert warmed.job is None
    assert ctx.shutdowns == ["not taken up"]
    assert DeleteRoomRequest(room=call) not in livekit.rooms.requests
