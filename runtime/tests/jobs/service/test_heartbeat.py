"""A worker's words to its gateway: a room said its own as its job is accepted, what a beat reports, a cordon."""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
import pytest
from livekit.agents import AgentServer, JobRequest
from livekit.agents.job import JobAcceptArguments
from livekit.protocol import agent as livekit_agent
from livekit.protocol import models

from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.heartbeat import UNREGISTERED, Accepted, Heartbeats
from runtime.jobs.service.load import Load, Server
from runtime.jobs.service.measures import LastMinute


@dataclass
class Registered:
    """livekit's server as the worker reads it: registered, running these calls, draining or not."""

    id: str = "AW_1"
    active_jobs: Sequence[object] = field(default_factory=list[object])
    draining: bool = False


@dataclass
class Gateway:
    """A gateway that answers each beat as its script says, and keeps what it was told."""

    answers: list[httpx.Response]
    heard: list[dict[str, object]] = field(default_factory=list[dict[str, object]])

    def answer(self, request: httpx.Request) -> httpx.Response:
        """The next answer of the script."""
        self.heard.append(json.loads(request.content))
        return self.answers.pop(0)


def beating(server: Server, gateway: Gateway) -> Heartbeats:
    """A worker of four slots that beats to this gateway."""
    client = GatewayClient(httpx.AsyncClient(transport=httpx.MockTransport(gateway.answer), base_url="http://gw"))
    accepted = Accepted(client, "pinecall-sandbox/w1")
    return Heartbeats(server, client, LastMinute(), Load(4), accepted, fleet_name="pinecall-sandbox", worker="w1")


def cordoned(is_cordoned: bool) -> httpx.Response:
    """The gateway's answer to a beat."""
    return httpx.Response(200, json={"cordoned": is_cordoned, "full": False})


def test_livekits_server_is_what_the_worker_reads() -> None:
    server: Server = AgentServer()
    assert server.id == UNREGISTERED


async def test_a_beat_reports_the_calls_held_the_slots_and_the_load_on_the_gateways_scale() -> None:
    gateway = Gateway([cordoned(False)])
    worker = beating(Registered(active_jobs=[object(), object()]), gateway)
    await worker.tell()
    (beat,) = gateway.heard
    assert (beat["active"], beat["max_jobs"], beat["load"], beat["draining"]) == (2, 4, 0.5, False)
    assert str(beat["agent_name"]).startswith(worker.agent_name)


# 2026-11-25: a job accepted waits for a process on a loaded worker, and livekit counts it among its
# active jobs only once it runs. Its room is the worker's from the accept, so its slot is said from then.
async def test_a_job_accepted_whose_process_has_not_started_is_one_of_the_calls_a_beat_reports() -> None:
    gateway = Gateway([cordoned(False)])
    worker = beating(Registered(active_jobs=[object()]), gateway)
    worker.accepted.starting.update({"AJ_1", "AJ_2"})
    await worker.tell()
    (beat,) = gateway.heard
    assert (beat["active"], beat["load"]) == (3, 0.75)


async def test_a_worker_livekit_has_not_registered_offers_no_name_and_is_not_ready() -> None:
    gateway = Gateway([cordoned(False)])
    worker = beating(Registered(id=UNREGISTERED), gateway)
    await worker.tell()
    assert gateway.heard[0]["agent_name"] is None
    assert not worker.ready.is_set()


# A worker that stopped beating is a worker the gateway forgets while it still holds its calls: a
# beat that raised ended the loop for good until 2026-11.
async def test_a_gateway_away_is_said_and_the_next_beat_goes_on_to_the_cordon(caplog: pytest.LogCaptureFixture) -> None:
    gateway = Gateway([httpx.Response(503, text="away"), cordoned(False), cordoned(True), cordoned(True)])
    worker = beating(Registered(), gateway)
    await worker.tell()
    assert "heartbeat: POST /v1/fleet/heartbeat: 503 away" in caplog.text
    assert not worker.leave.is_set()
    await worker.tell()
    assert worker.ready.is_set() and not worker.leave.is_set()
    await worker.tell()
    assert worker.cordoned and worker.leave.is_set()
    # Asked to leave once; a cordoned worker goes on beating while it drains.
    await worker.tell()
    assert len(gateway.heard) == 4
    assert caplog.text.count("cordoned by the gateway") == 1


THE_WORKER = "pinecall-sandbox/w1.1"


@dataclass
class Hearing:
    """A gateway that keeps what a worker said of its rooms, and answers as told."""

    status: int = 204
    heard: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    def answer(self, request: httpx.Request) -> httpx.Response:
        """The room is kept as said, or the gateway is away."""
        self.heard.append((request.method, str(request.url.raw_path, "ascii")))
        return httpx.Response(self.status)

    @property
    def client(self) -> GatewayClient:
        """The worker's way to this gateway."""
        return GatewayClient(httpx.AsyncClient(transport=httpx.MockTransport(self.answer), base_url="http://gw"))


@dataclass
class Launching:
    """livekit's side of an accept: the job's process found when the test says, or never."""

    started: asyncio.Event = field(default_factory=asyncio.Event)
    fails: Exception | None = None
    accepted: bool = False

    async def accept(self, arguments: JobAcceptArguments) -> None:
        """Hold the accept until the process runs, as livekit does while it finds or makes one."""
        del arguments
        self.accepted = True
        await self.started.wait()
        if self.fails is not None:
            raise self.fails

    async def reject(self, terminate: bool) -> None:
        """Never asked: every job offered is accepted."""
        del terminate
        raise AssertionError("a job offered to the worker is never rejected")

    def request(self, room: str) -> JobRequest:
        """The job LiveKit offers the worker for this room."""
        job = livekit_agent.Job(id=f"AJ_{room}", room=models.Room(name=room, sid=f"RM_{room}"))
        return JobRequest(job=job, on_reject=self.reject, on_accept=self.accept)


# 2026-11-25: with nineteen jobs starting on one worker a process took over twelve seconds to join its
# room, and the gateway rang each room again. The room is said before the process is found, not after.
async def test_a_room_is_said_the_workers_while_its_jobs_process_is_still_being_found() -> None:
    gateway, livekit = Hearing(), Launching()
    accepted = Accepted(gateway.client, THE_WORKER)
    answering = asyncio.create_task(accepted(livekit.request("call_1")))
    await asyncio.sleep(0.05)
    assert livekit.accepted and not answering.done()
    assert gateway.heard == [("POST", "/v1/fleet/rooms/call_1/taken")]
    assert accepted.starting == {"AJ_call_1"}, "a job with no process yet holds one of the worker's slots"
    livekit.started.set()
    await answering
    assert accepted.starting == set(), "once it runs it is one of livekit's active jobs"
    assert len(gateway.heard) == 1


async def test_a_job_that_never_started_gives_its_room_back() -> None:
    gateway, livekit = Hearing(), Launching(fails=RuntimeError("no process could be launched"))
    accepted = Accepted(gateway.client, THE_WORKER)
    livekit.started.set()
    with pytest.raises(RuntimeError, match="no process"):
        await accepted(livekit.request("call_2"))
    assert gateway.heard == [
        ("POST", "/v1/fleet/rooms/call_2/taken"),
        ("DELETE", "/v1/fleet/rooms/call_2/taken?worker=pinecall-sandbox%2Fw1.1"),
    ]
    assert accepted.starting == set()


# The word to the gateway is a seat's bookkeeping, never a condition of the call: a gateway away
# leaves the room the worker's once its agent joins, as it was before the word existed.
async def test_a_gateway_that_does_not_hear_it_changes_nothing_for_the_job(caplog: pytest.LogCaptureFixture) -> None:
    gateway, livekit = Hearing(status=503), Launching()
    accepted = Accepted(gateway.client, THE_WORKER)
    livekit.started.set()
    await accepted(livekit.request("call_3"))
    assert livekit.accepted
    assert "room call_3: the gateway was not told it is this worker's" in caplog.text
    assert gateway.heard == [("POST", "/v1/fleet/rooms/call_3/taken")]
