"""The runner: an env's hosted apps kept running as the gateway wants them, a host each."""

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from runtime.enums import Env
from runtime.exceptions import UpstreamError
from runtime.hosts.service.client import GatewayClient
from runtime.hosts.service.place import Container, Hosts, Launch
from runtime.hosts.service.plan import (
    Failed,
    Revive,
    Start,
    Step,
    Stop,
    WentLive,
    container_label,
    plan_beat,
    recent_exits,
)
from runtime.kit.loops import survive
from runtime.wire.runner import AppLogs, RunnerHeartbeatRequest, RunnerHeartbeatResponse, RunnerReport, WantedApp

logger = logging.getLogger(__name__)

BEAT_S = 5.0
# What a failure says of the process's own output: its last lines, or that there were none.
LAST_LINES = 20
PRINTED_NOTHING = "(the process printed nothing)"
# What a person asking for an app's logs is sent: its process's last lines.
SENT_LINES = 300
LONGEST_WHY = 2000
START = ("start",)
NOT_THE_RELEASE = "release {release}'s sources are not the ones uploaded: sha256 differs"
START_FAILED = "the release could not be started; it said:\n{output}"


@dataclass
class Runner:
    """An env's runner: what it holds between two beats, and the steps it has in hand."""

    hosts: Hosts
    gateway: GatewayClient
    # The gateway as this runner reaches it, which is how its hosts reach it too.
    address: str
    # What the runner is called in its beats: the short name of its machine.
    name: str
    reports: list[RunnerReport] = field(default_factory=list[RunnerReport])
    logs: list[AppLogs] = field(default_factory=list[AppLogs])
    # One task per app with steps under way; an app with one is left alone this beat.
    working: dict[str, asyncio.Task[None]] = field(default_factory=dict[str, asyncio.Task[None]])

    # A gateway or a place that is away is said and the next beat comes on time: a runner that waited
    # longer after each would leave every hosted app of its env unmanaged through a restart.
    async def beat_once(self, now: float) -> None:
        """One beat: tell the gateway what happened, and make the hosts what it answers."""
        try:
            await self.reconcile(await self.beat(), now)
        except UpstreamError as away:
            logger.warning("the runner's beat: %s", away)

    # What was not taken is said again with the next beat.
    async def beat(self) -> RunnerHeartbeatResponse:
        """Send what happened since the last beat; the gateway answers what should be running."""
        reports, self.reports = self.reports, []
        logs, self.logs = self.logs, []
        try:
            return await self.gateway.beat(RunnerHeartbeatRequest(runner=self.name, reports=reports, logs=logs))
        except UpstreamError:
            self.reports, self.logs = reports + self.reports, logs + self.logs
            raise

    async def reconcile(self, wanted: RunnerHeartbeatResponse, now: float) -> None:
        """Make the hosts what the gateway wants; the long steps go on past this beat."""
        # Reaped first: a step that ends after the listing would be planned again on a stale one.
        self._reap()
        containers = await self.hosts.list_running(wanted.env.value)
        for label, steps in plan_beat(wanted.apps, containers, now).items():
            if label not in self.working:
                self.working[label] = asyncio.create_task(self._take_steps(wanted.env, steps, now))
        await self._read_logs(wanted.apps, containers)

    async def close(self) -> None:
        """Leave: every step under way is cut short; the hosts go on as their place says."""
        for task in self.working.values():
            task.cancel()
        await asyncio.gather(*self.working.values(), return_exceptions=True)
        self.working.clear()
        await self.hosts.close()

    def _reap(self) -> None:
        for label, task in list(self.working.items()):
            if task.done():
                del self.working[label]
                if not task.cancelled() and task.exception() is not None:
                    logger.error("%s: its steps failed", label, exc_info=task.exception())

    async def _take_steps(self, env: Env, steps: Sequence[Step], now: float) -> None:
        for step in steps:
            match step:
                case Start(app):
                    await self._start(env, app, app.host, app.release)
                case Revive(app, container, crashed):
                    await self._revive(env, app, container, now, crashed=crashed)
                case Stop(container):
                    await self.hosts.stop(container.name)
                    logger.info("stopped %s", container.name)
                case WentLive(app):
                    self._report(app, "live", "")
                case Failed(app, why, container):
                    output = await self.hosts.read_logs(container.name, LAST_LINES)
                    self._report(app, "failed", why.format(output=_tail(output)))

    # The gateway names its address when the box has a name, else the one this runner dials; the
    # process registers as its host, which is how the gateway knows the release is serving.
    async def _start(self, env: Env, app: WantedApp, host: str, release: int, *, exits: tuple[float, ...] = ()) -> None:
        try:
            source = await self._fetch(app, release)
            named = await self.gateway.get_environment(app)
        except UpstreamError as failure:
            self._report(app, "failed", str(failure))
            return
        launch = Launch(
            env=env.value,
            app=container_label(app),
            host=host,
            release=release,
            sha256=hashlib.sha256(source).hexdigest(),
            source=source,
            arguments=[*START, "--prod"] if env is Env.production else list(START),
            exits=exits,
        )
        try:
            await self.hosts.start(launch, {"PINECALL_URL": self.address, **named, "PINECALL_HOST": host})
        except UpstreamError as failure:
            self._report(app, "failed", START_FAILED.format(output=str(failure)))
            return
        logger.info("started %s release %d as %s", launch.app, release, host)

    # Its last lines are kept as the app's logs before the host goes, so the exit is read. Only an
    # exit of the process's own counts towards giving up; the place's evictions never do. The exits
    # still in the window ride the new host, so a runner restarted finds them there.
    async def _revive(self, env: Env, app: WantedApp, container: Container, now: float, *, crashed: bool) -> None:
        output = await self.hosts.read_logs(container.name, SENT_LINES)
        self.logs.append(AppLogs(org=app.org, name=app.name, host=container.name, lines=output))
        how = "exited" if crashed else "was evicted by the cluster"
        logger.warning("%s: %s %s, run again:\n%s", container_label(app), container.name, how, _tail(output))
        counted = recent_exits(container.exits, now)
        exits = (*counted, now) if crashed else tuple(counted)
        await self.hosts.stop(container.name, grace_s=0)
        await self._start(env, app, container.name, container.release, exits=exits)

    # The wanted release is checked against the digest the gateway kept when it was uploaded; an
    # older one, revived, is the one the gateway still holds under its number. Read each time a host
    # is started: the place that needs the bytes past the start keeps them itself.
    async def _fetch(self, app: WantedApp, release: int) -> bytes:
        source = await self.gateway.get_source(app, release)
        if release == app.release and hashlib.sha256(source).hexdigest() != app.sha256:
            raise UpstreamError(NOT_THE_RELEASE.format(release=release))
        return source

    # The host asked for, else the one still serving while it installs.
    async def _read_logs(self, apps: Sequence[WantedApp], containers: Sequence[Container]) -> None:
        for app in apps:
            # An app whose logs cannot be read is said, and the apps after it are read all the same.
            with survive("reading an app's logs", container_label(app)):
                ours = [each.name for each in containers if each.app == container_label(app)]
                host = app.host if app.host in ours else next(iter(ours), None)
                if not app.logs_wanted or host is None:
                    continue
                output = await self.hosts.read_logs(host, SENT_LINES)
                self.logs.append(AppLogs(org=app.org, name=app.name, host=host, lines=output))

    def _report(self, app: WantedApp, state: Literal["live", "failed"], why: str) -> None:
        if state == "failed":
            logger.warning("%s release %d failed: %s", container_label(app), app.release, why)
        self.reports.append(
            RunnerReport(org=app.org, name=app.name, host=app.host, state=state, why=why[-LONGEST_WHY:])
        )


def _tail(output: str) -> str:
    lines = output.strip().splitlines()
    return "\n".join(lines[-LAST_LINES:]) if lines else PRINTED_NOTHING
