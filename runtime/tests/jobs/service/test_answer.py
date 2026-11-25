"""A spoken call end to end on the worker: LiveKit hands it the job, the app holds the agent, the call is sealed."""

import asyncio
import functools
import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import override

import httpx
import pytest
from livekit import api, rtc
from livekit.agents import JobContext, JobExecutorType, JobProcess
from livekit.agents.job import JobAcceptArguments, RunningJobInfo
from livekit.agents.utils import http_context
from livekit.protocol import agent as livekit_agent
from livekit.protocol import models
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.room import DeleteRoomRequest

from runtime.calls.recordings import Disk
from runtime.enums import Env
from runtime.exceptions import UpstreamError
from runtime.jobs.service import JobSettings, Warmed, answer_job, end_job
from runtime.jobs.service.arrival import arrive
from runtime.jobs.service.call_client import ANOTHER_JOBS, open_call
from runtime.jobs.service.client import GatewayClient, arriving, unavailable
from runtime.jobs.service.traces import OrgSpans
from runtime.kit.text import Json
from runtime.wire.dispatch import Dispatch
from runtime.wire.room import CHAT, SCOPE_ATTRIBUTE, TALK
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received, until
from tests.fakes.livekit import Player, Room, Server, Speaker, seat

GREETING = "Clínica Norte, buen día."
THE_VISITOR = "visitor_1"
RECORDED = "This call may be recorded."
THE_WORKER = "pinecall-sandbox/worker-test.1"


class Assigned(JobContext):
    """The job livekit's worker hands an entrypoint, on a room and a server of the test's."""

    def __init__(self, room: Room, server: Server, dispatch: Dispatch) -> None:
        """A job of this room, started with this dispatch."""
        job = livekit_agent.Job(
            id=f"AJ_{room.name}", room=models.Room(name=room.name, sid=f"RM_{room.name}"), metadata=dispatch.dump()
        )
        info = RunningJobInfo(
            accept_arguments=JobAcceptArguments(name="", identity="agent", metadata=""),
            job=job,
            url="ws://livekit.test",
            token="a-token",
            worker_id="AW_test",
            fake_job=True,
        )
        self.shutdowns: list[str] = []
        process = JobProcess(executor_type=JobExecutorType.THREAD, user_arguments=None, http_proxy=None)
        super().__init__(
            proc=process,
            info=info,
            room=room,
            on_connect=lambda: None,
            on_shutdown=self.shutdowns.append,
            inference_executor=NoInference(),
        )
        self.server = server

    async def finish(self) -> None:
        """What livekit's job runner does once the job ended: the job's own files cleaned up."""
        await self._on_cleanup()

    @functools.cached_property
    @override
    def api(self) -> api.LiveKitAPI:
        """The test's server, as livekit's worker exports its own to the job."""
        return self.server


class NoInference:
    """The worker's inference process, which a call on these stages never asks."""

    async def do_inference(self, method: str, data: bytes) -> bytes | None:
        """Nothing: no local model runs here."""
        del method, data
        return None


class ConnectedRoom(Room):
    """A room the job joins: connecting to it is taking the seat the test set."""

    @override
    async def connect(self, url: str, token: str, options: rtc.RoomOptions | None = None) -> None:
        """Joined: the seats are the test's."""
        del url, token, options


# The visitor hears every sentence the agent says to its end, as a person on the line does.
async def hear_to_the_end(speaker: Speaker) -> None:
    """Each segment the agent speaks, played to its end."""
    while True:
        speaker.played()
        await asyncio.sleep(0.05)


@pytest.fixture
async def server() -> AsyncIterator[Server]:
    """LiveKit's server, its doors the test's."""
    opened = Server()
    yield opened
    await opened.aclose()


def warmed_for(fleet: GatewayClient, tmp_path: Path) -> Warmed:
    """A worker's process readied as `prewarm` readies it, reaching the suite's gateway with the fleet's key."""
    told = JobSettings(
        agent=None,
        app=None,
        zone="America/Montevideo",
        recordings_root=tmp_path,
        voice_lookup_budget_ms=None,
        text_lookup_budget_ms=None,
        tool_steps=None,
        overflow_says="All our lines are busy.",
        worker="worker-test",
        measures=tmp_path / "measures.json",
    )
    return Warmed(gateway=fleet, spans=OrgSpans(), recordings=Disk(tmp_path), told=told, player=Player)


# A job end to end: the gateway, the session and the seal, each on its own clock.
@pytest.mark.timeout(60)
@needs_the_services
async def test_a_widget_call_livekit_hands_the_worker_is_greeted_hung_up_by_its_app_and_sealed(
    gateway: Gateway, fleet: GatewayClient, tenant: Tenant, agent: str, server: Server, tmp_path: Path
) -> None:
    """The job joins, the gateway opens the call for the app that holds the agent, the greeting is spoken,
    the app's hang-up reaches the call through its commands, and the end seals it and deletes its room."""
    # The worker runs every job inside livekit's http session, which its plugins open their sockets with.
    async with http_context.open(), holding(gateway, tenant, agent) as app:
        declared = {"config": {"greeting": {"say": GREETING}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        await received(app, "agent.configured")
        visitor = seat(THE_VISITOR, attributes={SCOPE_ATTRIBUTE: TALK})
        room = ConnectedRoom(f"room_{agent}", visitor)
        dispatch = Dispatch(agent=agent, org=tenant.org, env=Env.sandbox, scope=TALK)
        ctx = Assigned(room, server, dispatch)
        warmed = warmed_for(fleet, tmp_path)
        await answer_job(ctx, warmed)
        job = warmed.job
        assert job is not None
        speaker = Speaker()
        job.setup.running.live.output.audio = speaker
        call = job.link.call
        assert (await received(app, "call.started"))["call"] == call
        listening = asyncio.create_task(hear_to_the_end(speaker))
        try:
            await until(lambda: speaker.frames > 0, within_s=10)
            hangup = {"type": "call.hangup", "agent": agent, "call": call, "data": {"reason": "done"}}
            await app.send(json.dumps(hangup))
            await until(lambda: bool(ctx.shutdowns), within_s=10)
            # livekit's own end of the session, run once the job was told to shut down.
            await end_job(warmed)
        finally:
            listening.cancel()
            await ctx.finish()
    entries = await gateway.http.get(f"/v1/calls/{call}/events", params={"durable": True}, headers=tenant.server)
    page = entries.json()
    kinds = [entry["type"] for entry in page["entries"]]
    assert not page["live"], kinds
    assert kinds.index("call.ringing") < kinds.index("call.started") < kinds.index("call.ended")
    said = [entry["data"]["text"] for entry in page["entries"] if entry["type"] == "turn.agent"]
    # The org's notice that the call is recorded comes first, then the agent's greeting.
    assert said[:2] == [RECORDED, GREETING]
    ended = next(entry["data"] for entry in page["entries"] if entry["type"] == "call.ended")
    assert ended["ended_by"] == "agent"
    assert DeleteRoomRequest(room=room.name) in server.rooms.requests
    assert warmed.job is None


@pytest.mark.timeout(60)
@needs_the_services
async def test_a_chat_in_a_room_livekit_hands_the_worker_is_greeted_in_writing_hung_up_and_sealed(
    gateway: Gateway, fleet: GatewayClient, tenant: Tenant, agent: str, server: Server, tmp_path: Path
) -> None:
    """A written call on the worker: no voice, no notice, the greeting written, the app's hang-up, the seal."""
    async with http_context.open(), holding(gateway, tenant, agent) as app:
        declared = {"config": {"greeting": {"say": GREETING}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        await received(app, "agent.configured")
        room = ConnectedRoom(f"room_{agent}", seat(THE_VISITOR, attributes={SCOPE_ATTRIBUTE: CHAT}))
        ctx = Assigned(room, server, Dispatch(agent=agent, org=tenant.org, env=Env.sandbox, scope=CHAT))
        warmed = warmed_for(fleet, tmp_path)
        try:
            await answer_job(ctx, warmed)
            job = warmed.job
            assert job is not None
            call = job.link.call
            assert (await received(app, "call.started"))["call"] == call
            assert (await received(app, "turn.agent"))["data"]["text"] == GREETING
            hangup = {"type": "call.hangup", "agent": agent, "call": call, "data": {"reason": "done"}}
            await app.send(json.dumps(hangup))
            await until(lambda: bool(ctx.shutdowns), within_s=10)
            await end_job(warmed)
        finally:
            await ctx.finish()
    entries = await gateway.http.get(f"/v1/calls/{call}/events", params={"durable": True}, headers=tenant.server)
    page = entries.json()
    kinds = [entry["type"] for entry in page["entries"]]
    assert not page["live"], kinds
    assert [entry["data"]["text"] for entry in page["entries"] if entry["type"] == "turn.agent"] == [GREETING]
    assert DeleteRoomRequest(room=room.name) in server.rooms.requests


# 2026-11-25: a room rung twice under load had two jobs, and the second ended the call the first was
# holding. The gateway tells the second the call has a worker, and the job leaves the room as it is.
@pytest.mark.timeout(60)
@needs_the_services
async def test_a_job_sent_to_a_room_whose_call_another_job_opened_leaves_it_and_ends_nothing(
    gateway: Gateway, fleet: GatewayClient, tenant: Tenant, agent: str, server: Server, livekit: Server, tmp_path: Path
) -> None:
    """Its open refused, the job is told to shut down: no session, no entry of its own, no seal, no room deleted."""
    async with http_context.open(), holding(gateway, tenant, agent) as app:
        declared = {"config": {"greeting": {"say": GREETING}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        await received(app, "agent.configured")
        room = ConnectedRoom(f"room_{agent}", seat(THE_VISITOR, attributes={SCOPE_ATTRIBUTE: TALK}))
        dispatch = Dispatch(agent=agent, org=tenant.org, env=Env.sandbox, scope=TALK)
        # The first job of the room: it joined, opened the call and sits in its room.
        first = Assigned(room, server, dispatch)
        arrived = await arrive(first, fleet, default_agent=None, zone="America/Montevideo", asking=arriving())
        assert arrived is not None
        opener = await open_call(fleet, arrived.open_with(None, "agent-AJ_first"))
        livekit.rooms.people = {room.name}
        livekit.rooms.seated = {
            room.name: [ParticipantInfo(identity="agent-AJ_first", kind=ParticipantInfo.Kind.AGENT)]
        }
        second = Assigned(room, server, dispatch)
        warmed = warmed_for(fleet, tmp_path)
        try:
            await answer_job(second, warmed)
            await end_job(warmed)
        finally:
            await second.finish()
            await first.finish()
        assert second.shutdowns == [ANOTHER_JOBS]
        assert warmed.job is None
    entries = await gateway.http.get(f"/v1/calls/{room.name}/events", params={"durable": True}, headers=tenant.server)
    page = entries.json()
    assert [entry["type"] for entry in page["entries"]] == ["call.ringing"], "the call is as its opener left it"
    assert page["live"], "nothing sealed it"
    assert DeleteRoomRequest(room=room.name) not in server.rooms.requests
    await opener.aclose()


class BusyAtFirst(GatewayClient):
    """The suite's gateway as a job reaches it on a busy afternoon: the first ask of each of its reads is a `503`."""

    def __init__(self, gateway: GatewayClient) -> None:
        """The same gateway, on the same key; nothing asked or said of a room yet."""
        super().__init__(gateway.http)
        self.asked: list[str] = []
        self.given_back: list[tuple[str, str]] = []

    @override
    async def answer(
        self,
        method: str,
        path: str,
        data: Json = None,
        *,
        wait_s: float | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """A read asked for the first time is refused as a full pool refuses it; asked again, it is answered."""
        if method == "GET":
            self.asked.append(path)
            if self.asked.count(path) == 1:
                raise unavailable(
                    f"GET {path}: 503 the database is busy: no connection came free within 2 s", answered=503
                )
        return await super().answer(method, path, data, wait_s=wait_s, params=params)

    @override
    async def drop_room(self, room: str, agent_name: str) -> None:
        """Kept, and said to the gateway as any job says it."""
        self.given_back.append((room, agent_name))
        await super().drop_room(room, agent_name)


# 2026-11-25, two orgs evaluating at once on the tests' server: the gateway's pool had no connection
# free for two seconds, a job's read of its agent was answered `503`, the job ended on it, and its
# simulated caller waited 110 s for nobody. Three calls of twenty. What a job asks before its call is
# open is asked again.
@pytest.mark.timeout(60)
@needs_the_services
async def test_a_job_whose_gateway_is_busy_as_it_arrives_asks_again_and_answers_its_call(
    gateway: Gateway, fleet: GatewayClient, tenant: Tenant, agent: str, server: Server, tmp_path: Path
) -> None:
    """Its routes, its agent, its stages and its hold are each refused once: the call is opened and greeted anyway."""
    busy = BusyAtFirst(fleet)
    async with http_context.open(), holding(gateway, tenant, agent) as app:
        declared = {"config": {"greeting": {"say": GREETING}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        await received(app, "agent.configured")
        room = ConnectedRoom(f"room_{agent}", seat(THE_VISITOR, attributes={SCOPE_ATTRIBUTE: CHAT}))
        ctx = Assigned(room, server, Dispatch(agent=agent, org=tenant.org, env=Env.sandbox, scope=CHAT))
        ctx.job.agent_name = THE_WORKER
        warmed = warmed_for(busy, tmp_path)
        try:
            await answer_job(ctx, warmed)
            job = warmed.job
            assert job is not None, "the job answered its call"
            call = job.link.call
            assert (await received(app, "call.started"))["call"] == call
            assert (await received(app, "turn.agent"))["data"]["text"] == GREETING
            hangup = {"type": "call.hangup", "agent": agent, "call": call, "data": {"reason": "done"}}
            await app.send(json.dumps(hangup))
            await until(lambda: bool(ctx.shutdowns), within_s=10)
            await end_job(warmed)
        finally:
            await ctx.finish()
    reads = [f"/v1/agents/{agent}/config", f"/v1/agents/{agent}/provider-keys", f"/v1/agents/{agent}/hold-audio"]
    assert {path: busy.asked.count(path) for path in ("/v1/routes", *reads)} == dict.fromkeys(("/v1/routes", *reads), 2)
    assert busy.given_back == [], "a room whose call was opened is not given back"


# A job that leaves before its call is open leaves a room the gateway holds for its worker since the
# job was accepted: said given back, the sweep offers it again while its caller still waits.
@pytest.mark.timeout(60)
@needs_the_services
async def test_a_job_the_gateway_refuses_before_its_call_is_open_gives_its_room_back(
    fleet: GatewayClient, tenant: Tenant, server: Server, tmp_path: Path
) -> None:
    """An agent no org holds is the gateway's refusal: the job ends on it, its room given back first."""
    busy = BusyAtFirst(fleet)
    async with http_context.open():
        room = ConnectedRoom("room_of_nobodys_agent", seat(THE_VISITOR, attributes={SCOPE_ATTRIBUTE: CHAT}))
        dispatch = Dispatch(agent="an-agent-nobody-holds", org=tenant.org, env=Env.sandbox, scope=CHAT)
        ctx = Assigned(room, server, dispatch)
        ctx.job.agent_name = THE_WORKER
        warmed = warmed_for(busy, tmp_path)
        try:
            with pytest.raises(UpstreamError) as refused:
                await answer_job(ctx, warmed)
        finally:
            await ctx.finish()
    assert refused.value.answered == httpx.codes.NOT_FOUND
    assert busy.given_back == [(room.name, THE_WORKER)]
    assert warmed.job is None
