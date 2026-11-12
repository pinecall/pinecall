"""The env's runner: its heartbeat, a release's sources, and what an app's process is started with."""

from fastapi import APIRouter, Response

from runtime.alerts.auth import TheAlerting
from runtime.calls.auth import TheFeeds
from runtime.handles import TheSettings, TheSignal, TheVault
from runtime.hosting.auth import RunnerKey, TheProcesses, TheRunnersApp
from runtime.hosting.service import apps, beats, releases
from runtime.postgres import TheBoxSession
from runtime.wire.runner import AppEnvironment, RunnerHeartbeatRequest, RunnerHeartbeatResponse, WantedApp

router = APIRouter()

GZIP = "application/gzip"


@router.post("/v1/runner/heartbeat")
async def runner_heartbeat(
    body: RunnerHeartbeatRequest,
    actor: RunnerKey,
    alerting: TheAlerting,
    feeds: TheFeeds,
    signal: TheSignal,
    processes: TheProcesses,
    session: TheBoxSession,
) -> RunnerHeartbeatResponse:
    """The runner's reports and logs kept, and every app of its env it is to have running."""
    wanted = await beats.hear_beat(session, alerting, feeds, signal, processes, actor.env, body)
    told = [WantedApp.model_validate(app, from_attributes=True) for app in wanted]
    return RunnerHeartbeatResponse(env=actor.env, apps=told)


@router.get("/v1/runner/apps/{org}/{name}/releases/{release}/source")
async def runner_source(app: TheRunnersApp, release: int, session: TheBoxSession) -> Response:
    """The tarball of one release of any org's app in the runner's env."""
    return Response((await releases.source_of(session, app, release)).data, media_type=GZIP)


@router.get("/v1/runner/apps/{org}/{name}/environment")
async def runner_environment(
    app: TheRunnersApp, vault: TheVault, settings: TheSettings, session: TheBoxSession
) -> AppEnvironment:
    """What the app's process is started with: the org's secrets, its token, the gateway."""
    return AppEnvironment(environment=await apps.environment_for(session, vault, settings.address, app))
