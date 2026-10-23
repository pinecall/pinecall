"""The runner: an env's hosted apps kept running as the gateway wants them, one pod each."""

import asyncio
import hashlib
import logging
import signal
import socket
import time
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from pinecall_runtime.config import Settings
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ConfigurationError, UpstreamError
from pinecall_runtime.hosting.schemas import (
    AppEnvironment,
    AppLogs,
    RunnerHeartbeatRequest,
    RunnerHeartbeatResponse,
    RunnerReport,
    WantedApp,
)
from pinecall_runtime.hosting.service.cluster import Cluster, Engine, in_cluster
from pinecall_runtime.hosting.service.hosts import Container, Hosts, Launch
from pinecall_runtime.hosting.service.plan import (
    Failed,
    Revive,
    Start,
    Step,
    Stop,
    WentLive,
    crashes_within,
    label_of,
    planned,
)
from pinecall_runtime.hosting.service.processes import Processes
from pinecall_runtime.kit.loops import survived

logger = logging.getLogger(__name__)

BEAT_S = 5.0
# What a failure says of the process's own output: its last lines, or that there were none.
LAST_LINES = 20
PRINTED_NOTHING = "(the process printed nothing)"
# What a person asking for an app's logs is sent: its process's last lines.
SENT_LINES = 300
LONGEST_WHY = 2000
START = ("start",)
NO_KEY = "PINECALL_RUNNER_KEY: a runner signs in to its gateway with its env's runner key"
NOT_THE_RELEASE = "release {release}'s sources are not the ones uploaded: sha256 differs"
START_FAILED = "the release could not be started; it said:\n{output}"
GATEWAY_REFUSED = "the gateway answered {status}: {text}"

# A release is (org, name, release): what the gateway numbers and what a pod carries.
type Release = tuple[str, str, int]


@dataclass
class Runner:
    """An env's runner: what it holds between two beats, and the steps it has in hand."""

    hosts: Hosts
    gateway: httpx.AsyncClient
    # The gateway as this runner reaches it, which is how its hosts reach it too.
    address: str
    reports: list[RunnerReport] = field(default_factory=list[RunnerReport])
    logs: list[AppLogs] = field(default_factory=list[AppLogs])
    # One task per app with steps under way; an app with one is left alone this beat.
    working: dict[str, asyncio.Task[None]] = field(default_factory=dict[str, asyncio.Task[None]])
    # The releases a pod of this env may fetch, by their digest: read off the gateway, checked.
    sources: dict[str, bytes] = field(default_factory=dict[str, bytes])
    digests: dict[Release, str] = field(default_factory=dict[Release, str])

    async def beat(self, name: str) -> RunnerHeartbeatResponse:
        """Send what happened since the last beat; the gateway answers what should be running."""
        reports, self.reports = self.reports, []
        logs, self.logs = self.logs, []
        body = RunnerHeartbeatRequest(runner=name, reports=reports, logs=logs)
        try:
            answer = await self.gateway.post("/v1/runner/heartbeat", json=body.dump())
        except httpx.HTTPError:
            self.reports, self.logs = reports + self.reports, logs + self.logs
            raise
        if not answer.is_success:
            self.reports, self.logs = reports + self.reports, logs + self.logs
            raise UpstreamError(GATEWAY_REFUSED.format(status=answer.status_code, text=answer.text))
        return RunnerHeartbeatResponse.model_validate(answer.json())

    async def reconcile(self, wanted: RunnerHeartbeatResponse, now: float) -> None:
        """Make the pods what the gateway wants; the long steps go on past this beat."""
        # Finished first: a step that ends after the listing would be planned again on a stale one.
        self._finished()
        containers = await self.hosts.running(wanted.env.value)
        for label, steps in planned(wanted.apps, containers, now).items():
            if label not in self.working:
                self.working[label] = asyncio.create_task(self._done(wanted.env, steps, now))
        await self._logs_asked_for(wanted.apps, containers)
        self._swept(wanted.apps, containers)

    async def close(self) -> None:
        """Leave: every step under way is cut short; the hosts go on as their place says."""
        for task in self.working.values():
            task.cancel()
        await asyncio.gather(*self.working.values(), return_exceptions=True)
        self.working.clear()
        await self.hosts.close()

    def _finished(self) -> None:
        for label, task in list(self.working.items()):
            if task.done():
                del self.working[label]
                if not task.cancelled() and task.exception() is not None:
                    logger.error("%s: its steps failed", label, exc_info=task.exception())

    async def _done(self, env: Env, steps: Sequence[Step], now: float) -> None:
        for step in steps:
            match step:
                case Start(app):
                    await self._started(env, app, app.host, app.release)
                case Revive(app, container, crashed):
                    await self._revived(env, app, container, now, crashed=crashed)
                case Stop(container):
                    await self.hosts.stop(container.name)
                    logger.info("stopped %s", container.name)
                case WentLive(app):
                    self._report(app, "live", "")
                case Failed(app, why, container):
                    output = await self.hosts.logs(container.name, LAST_LINES)
                    self._report(app, "failed", why.format(output=_tail(output)))

    async def _started(
        self, env: Env, app: WantedApp, host: str, release: int, *, exits: tuple[float, ...] = ()
    ) -> None:
        try:
            digest = await self._fetched(app, release)
            # The gateway names its address when the box has a name, else the one this runner dials; the
            # process registers as its host, which is how the gateway knows the release is serving.
            environment = {"PINECALL_URL": self.address, **await self._environment(app), "PINECALL_HOST": host}
        except UpstreamError as failure:
            self._report(app, "failed", str(failure))
            return
        launch = Launch(
            env=env.value,
            app=label_of(app),
            host=host,
            release=release,
            sha256=digest,
            source=self.sources[digest],
            arguments=[*START, "--prod"] if env is Env.production else list(START),
            exits=exits,
        )
        try:
            await self.hosts.start(launch, environment)
        except UpstreamError as failure:
            self._report(app, "failed", START_FAILED.format(output=str(failure)))
            return
        logger.info("started %s release %d as %s", label_of(app), release, host)

    # Its last lines are kept as the app's logs before the pod goes, so the exit is read. Only an
    # exit of the process's own counts towards giving up; the cluster's evictions never do. The
    # exits still in the window ride the new pod, so a runner restarted finds them there.
    async def _revived(self, env: Env, app: WantedApp, container: Container, now: float, *, crashed: bool) -> None:
        output = await self.hosts.logs(container.name, SENT_LINES)
        self.logs.append(AppLogs(org=app.org, name=app.name, host=container.name, lines=output))
        how = "exited" if crashed else "was evicted by the cluster"
        logger.warning("%s: %s %s, run again:\n%s", label_of(app), container.name, how, _tail(output))
        counted = crashes_within(container.exits, now)
        exits = (*counted, now) if crashed else tuple(counted)
        await self.hosts.stop(container.name, grace_s=0)
        await self._started(env, app, container.name, container.release, exits=exits)

    # The wanted release is checked against the digest the gateway kept when it was uploaded; an
    # older one, revived, is the one the gateway still holds under its number.
    async def _fetched(self, app: WantedApp, release: int) -> str:
        known = self.digests.get((app.org, app.name, release))
        if known is not None and known in self.sources:
            return known
        answer = await self.gateway.get(f"/v1/runner/apps/{app.org}/{app.name}/releases/{release}/source")
        if not answer.is_success:
            raise UpstreamError(f"the release's sources: {answer.status_code} {answer.text}")
        digest = hashlib.sha256(answer.content).hexdigest()
        if release == app.release and digest != app.sha256:
            raise UpstreamError(NOT_THE_RELEASE.format(release=release))
        self.sources[digest] = answer.content
        self.digests[(app.org, app.name, release)] = digest
        return digest

    async def _environment(self, app: WantedApp) -> Mapping[str, str]:
        answer = await self.gateway.get(f"/v1/runner/apps/{app.org}/{app.name}/environment")
        if not answer.is_success:
            raise UpstreamError(f"the app's environment: {answer.status_code} {answer.text}")
        return AppEnvironment.model_validate(answer.json()).environment

    # The host asked for, else the one still serving while it installs.
    async def _logs_asked_for(self, apps: Sequence[WantedApp], containers: Sequence[Container]) -> None:
        for app in apps:
            # An app whose logs cannot be read is said, and the apps after it are read all the same.
            with survived("reading an app's logs", label_of(app)):
                ours = [each.name for each in containers if each.app == label_of(app)]
                host = app.host if app.host in ours else next(iter(ours), None)
                if not app.logs_wanted or host is None:
                    continue
                output = await self.hosts.logs(host, SENT_LINES)
                self.logs.append(AppLogs(org=app.org, name=app.name, host=host, lines=output))

    # A release no pod runs and nobody wants is no longer anybody's to fetch.
    def _swept(self, apps: Sequence[WantedApp], containers: Sequence[Container]) -> None:
        in_use: set[Release] = {(app.org, app.name, app.release) for app in apps}
        for each in containers:
            org, _, name = each.app.partition("/")
            in_use.add((org, name, each.release))
        for release in [each for each in self.digests if each not in in_use]:
            del self.digests[release]
        kept = set(self.digests.values())
        for digest in [each for each in self.sources if each not in kept]:
            del self.sources[digest]

    def _report(self, app: WantedApp, state: str, why: str) -> None:
        if state == "failed":
            logger.warning("%s release %d failed: %s", label_of(app), app.release, why)
        self.reports.append(
            RunnerReport.model_validate(
                {"org": app.org, "name": app.name, "host": app.host, "state": state, "why": why[-LONGEST_WHY:]}
            )
        )


def sources_app(runner: Runner) -> Starlette:
    """The one endpoint a pod of this env calls: its release's sources, by their digest."""

    async def served(request: Request) -> Response:
        found = runner.sources.get(str(request.path_params["sha256"]))
        if found is None:
            return Response(status_code=404)
        return Response(found, media_type="application/gzip")

    return Starlette(routes=[Route("/sources/{sha256}", served)])


async def run_runner(settings: Settings) -> int:
    """Keep the env's hosted apps running until told to stop."""
    if settings.runner_key is None:
        raise ConfigurationError(NO_KEY)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for each in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(each, stop.set)
    headers = {"Authorization": f"Bearer {settings.runner_key.get_secret_value()}"}
    async with (
        httpx.AsyncClient(base_url=settings.gateway_url, headers=headers, timeout=30.0) as gateway,
        AsyncExitStack() as stack,
    ):
        if settings.runner_engine == "processes":
            runner = Runner(hosts=Processes(settings.runner_home), gateway=gateway, address=settings.gateway_url)
        else:
            runner = await _on_the_cluster(settings, gateway, stack)
        await beating(runner, socket.gethostname().split(".")[0], stop)
        await runner.close()
    return 0


# A beat that did nothing is said and the next comes: the runner that ended on an answer it could not
# read would leave every hosted app of its env unmanaged until it was restarted.
async def beating(runner: Runner, name: str, stop: asyncio.Event) -> None:
    """Beat every few seconds until told to stop."""
    while not stop.is_set():
        with survived("the runner's beat"):
            await runner.reconcile(await runner.beat(name), time.time())
        try:
            await asyncio.wait_for(stop.wait(), BEAT_S)
        except TimeoutError:
            continue


# A pod fetches its release from the runner by digest: the cluster's runner serves the sources.
async def _on_the_cluster(settings: Settings, gateway: httpx.AsyncClient, stack: AsyncExitStack) -> Runner:
    engine = Engine(
        image=settings.runner_image,
        runtime_class=settings.runner_runtime_class,
        namespace=settings.runner_namespace,
        sources_url=settings.runner_sources_url,
    )
    kube = await stack.enter_async_context(in_cluster(engine).http)
    runner = Runner(hosts=Cluster(http=kube, engine=engine), gateway=gateway, address=settings.gateway_url)
    server = uvicorn.Server(
        uvicorn.Config(sources_app(runner), host=settings.runner_listen, port=settings.runner_port, log_level="warning")
    )
    serving = asyncio.create_task(server.serve())

    async def stopped() -> None:
        server.should_exit = True
        await serving

    stack.push_async_callback(stopped)
    return runner


def _tail(output: str) -> str:
    lines = output.strip().splitlines()
    return "\n".join(lines[-LAST_LINES:]) if lines else PRINTED_NOTHING
