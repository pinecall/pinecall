"""The worker's heartbeat goes on after a beat that raised, and still ends on a cordon."""

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from livekit.agents import AgentServer

from pinecall_runtime.config import load_settings
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.fleet.schemas import HeartbeatRequest, HeartbeatResponse
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.jobs.service.heartbeat import Heartbeats
from pinecall_runtime.jobs.service.measures import LastMinute
from tests.conftest import until


class Gateway:
    """A gateway that fails each of the first beats in its own way, then cordons the worker."""

    def __init__(self) -> None:
        """No beat heard yet."""
        self.beats = 0

    async def heartbeat(self, _beat: HeartbeatRequest) -> HeartbeatResponse:
        """Refuse the first, answer the second in a shape this worker cannot read, cordon from the fourth."""
        self.beats += 1
        if self.beats == 1:
            raise GatewayUnavailable("POST /v1/fleet/heartbeat: 503")
        if self.beats == 2:
            raise ValueError("1 validation error for HeartbeatResponse")
        return HeartbeatResponse(cordoned=self.beats >= 4, full=False)


def heartbeats(gateway: Gateway) -> Heartbeats:
    """A worker that holds nothing and is registered, beating to this gateway."""
    server = SimpleNamespace(id="registered", active_jobs=[], draining=False, load_fnc=None)
    return Heartbeats(cast(AgentServer, server), cast(GatewayClient, gateway), load_settings(), LastMinute())


# A worker that stopped beating is a worker the gateway forgets while it still holds its calls: a
# beat that raised anything but GatewayUnavailable ended the loop for good.
async def test_a_beat_the_gateway_refused_or_answered_unreadably_does_not_end_the_beating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = Gateway()
    worker = heartbeats(gateway)
    monkeypatch.setattr(fleet, "HEARTBEAT_S", 0.01)
    beating = asyncio.create_task(worker.run())
    try:
        await until(lambda: worker.leave.is_set(), 30)
        assert (gateway.beats, worker.cordoned, worker.ready.is_set()) == (4, True, True)
    finally:
        beating.cancel()
        await asyncio.gather(beating, return_exceptions=True)
