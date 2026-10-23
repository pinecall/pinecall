"""The runner's loop beats until told to stop, whatever one beat met; an app's logs unread do not stop the others'."""

import asyncio
from typing import cast

import httpx
import pytest

from pinecall_runtime.hosting.schemas import RunnerHeartbeatResponse, WantedApp
from pinecall_runtime.hosting.service import runner
from pinecall_runtime.hosting.service.hosts import Container, Hosts
from pinecall_runtime.hosting.service.plan import label_of
from pinecall_runtime.hosting.service.runner import Runner, beating


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


# The loop caught UpstreamError and httpx.HTTPError: an answer it could not read ended the runner, and
# every hosted app of its env went unmanaged until somebody restarted it.
async def test_a_beat_that_met_anything_does_not_end_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    beats: list[str] = []
    stop = asyncio.Event()

    class Beating:
        async def beat(self, name: str) -> RunnerHeartbeatResponse:
            beats.append(name)
            if len(beats) == 1:
                raise ValueError("1 validation error for RunnerHeartbeatResponse")
            return cast(RunnerHeartbeatResponse, None)

        async def reconcile(self, _wanted: RunnerHeartbeatResponse, _now: float) -> None:
            if len(beats) >= 3:
                stop.set()

    monkeypatch.setattr(runner, "BEAT_S", 0.01)
    await asyncio.wait_for(beating(cast(Runner, Beating()), "runner-1", stop), 30)
    assert beats == ["runner-1"] * 3


async def test_an_apps_logs_that_cannot_be_read_are_said_and_the_next_apps_are() -> None:
    read: list[str] = []

    class Hosting:
        async def logs(self, host: str, _lines: int) -> str:
            read.append(host)
            if host == "bad-r1":
                raise RuntimeError("the pod went")
            return "a line"

    apps = [a_wanted("bad"), a_wanted("good")]
    held = Runner(hosts=cast(Hosts, Hosting()), gateway=cast(httpx.AsyncClient, None), address="")
    containers = [
        Container(name=f"{app.name}-r1", app=label_of(app), release=1, state="running", started_at=0.0) for app in apps
    ]
    await held._logs_asked_for(apps, containers)
    assert read == ["bad-r1", "good-r1"]
    assert [(logs.name, logs.host) for logs in held.logs] == [("good", "good-r1")]
