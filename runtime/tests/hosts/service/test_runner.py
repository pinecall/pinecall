"""The runner's beat: what a gateway that is away costs it, and an app's logs unread not stopping the others'."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx
import pytest

from runtime.hosts.service.client import GatewayClient
from runtime.hosts.service.place import DRAIN_S, Container, Launch
from runtime.hosts.service.plan import container_label
from runtime.hosts.service.runner import Runner
from runtime.kit.text import JsonObject
from runtime.wire.runner import RunnerHeartbeatResponse, RunnerReport, WantedApp

NOW = 10_000.0


def a_wanted(name: str) -> WantedApp:
    """An app of an org whose host is serving, its logs asked for."""
    return WantedApp(
        org="org_1",
        name=name,
        release=1,
        sha256="f" * 64,
        host=f"{name}-r1",
        registered=True,
        failed=False,
        logs_wanted=True,
        live_host=f"{name}-r1",
    )


@dataclass
class Place:
    """Where the env's hosts run, for a runner's beat: every app's host serving, one whose logs cannot be read."""

    apps: list[WantedApp]
    unread: str | None = None
    read: list[str] = field(default_factory=list[str])

    async def list_running(self, env: str) -> list[Container]:
        """Each app's host, running."""
        return [
            Container(name=app.host, app=container_label(app), release=1, state="running", started_at=0.0)
            for app in self.apps
        ]

    async def start(self, launch: Launch, environment: Mapping[str, str]) -> None:
        """Nothing is started: every host is serving."""

    async def stop(self, name: str, grace_s: int = DRAIN_S) -> None:
        """Nothing is stopped."""

    async def read_logs(self, name: str, lines: int) -> str:
        """The host's last lines, but for the one whose pod went."""
        self.read.append(name)
        if name == self.unread:
            raise RuntimeError("the pod went")
        return "a line"

    async def close(self) -> None:
        """Nothing to leave."""


@dataclass
class Gateway:
    """The gateway as the runner asks it: what each beat said, and what it answers."""

    apps: list[WantedApp]
    away: int = 0
    heard: list[JsonObject] = field(default_factory=list[JsonObject])

    def answer(self, asked: httpx.Request) -> httpx.Response:
        """Keep the beat and say what should be running; a 503 while it is away."""
        assert asked.url.path == "/v1/runner/heartbeat"
        if self.away:
            self.away -= 1
            return httpx.Response(503, text="the gateway is restarting")
        self.heard.append(json.loads(asked.content))
        wanted = RunnerHeartbeatResponse.model_validate({"world": "sandbox", "apps": [app.dump() for app in self.apps]})
        return httpx.Response(200, json=wanted.model_dump(mode="json", by_alias=True))


def a_runner(place: Place, gateway: Gateway) -> Runner:
    """An env's runner on the place, asking the gateway."""
    http = httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(gateway.answer))
    return Runner(hosts=place, gateway=GatewayClient(http), address="http://gateway.test", name="runner-1")


# The loop once ended on an answer it could not take, and every hosted app of its env went unmanaged
# until somebody restarted it. A gateway that is away is said, and what the beat carried is said
# again with the next one.
async def test_a_beat_the_gateway_did_not_take_is_said_and_carried_by_the_next(
    caplog: pytest.LogCaptureFixture,
) -> None:
    apps = [a_wanted("front")]
    gateway = Gateway(apps, away=1)
    runner = a_runner(Place(apps), gateway)
    went_live = RunnerReport(org="org_1", name="front", host="front-r1", state="live")
    runner.reports.append(went_live)
    await runner.beat_once(NOW)
    assert "the runner's beat" in caplog.text and "503" in caplog.text
    assert runner.reports == [went_live]
    await runner.beat_once(NOW)
    assert [beat["reports"] for beat in gateway.heard] == [[went_live.dump()]]
    assert runner.reports == []
    await runner.close()
    await runner.gateway.aclose()


async def test_an_apps_logs_that_cannot_be_read_are_said_and_the_next_apps_are(
    caplog: pytest.LogCaptureFixture,
) -> None:
    apps = [a_wanted("bad"), a_wanted("good")]
    place = Place(apps, unread="bad-r1")
    gateway = Gateway(apps)
    runner = a_runner(place, gateway)
    await runner.beat_once(NOW)
    assert place.read == ["bad-r1", "good-r1"]
    assert "reading an app's logs failed on org_1/bad" in caplog.text
    assert [(logs.name, logs.host) for logs in runner.logs] == [("good", "good-r1")]
    await runner.beat_once(NOW)
    assert [(logs["name"], logs["lines"]) for logs in gateway.heard[1]["logs"]] == [("good", "a line")]
    await runner.close()
    await runner.gateway.aclose()
