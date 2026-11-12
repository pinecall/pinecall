"""A worker's heartbeat: what it reports, a gateway that refused, and a cordon's way out said once."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
import pytest
from livekit.agents import AgentServer

from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.heartbeat import UNREGISTERED, Heartbeats
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
    return Heartbeats(server, client, LastMinute(), Load(4), fleet_name="pinecall-sandbox", worker="w1")


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
