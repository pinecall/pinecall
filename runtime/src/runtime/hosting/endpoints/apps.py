"""An org's hosted apps: listed, stopped, started, their logs read and followed, let go."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from runtime.accounts.auth import TheKeyCache
from runtime.handles import TheClosing, TheSessions, TheSignal
from runtime.hosting import schemas
from runtime.hosting.auth import TheApp
from runtime.hosting.service import apps, logs
from runtime.kit import sse
from runtime.live.auth import AppKey
from runtime.postgres import Session

router = APIRouter()

RETRY_MS = 1000


@router.get("/v1/hosted")
async def list_hosted_apps(actor: AppKey, session: Session) -> schemas.HostedAppList:
    """The apps the box hosts for the org in this env, by name."""
    standing = await apps.list_standing(session, actor.env, actor.org)
    return schemas.HostedAppList(apps=[schemas.HostedAppRow.of(app) for app in standing])


@router.post("/v1/hosted/{name}/stop", status_code=204)
async def stop_hosted_app(app: TheApp, actor: AppKey, signal: TheSignal, session: Session) -> None:
    """Stop running the app: its process drains, and its releases and token stay."""
    await apps.stop_app(session, signal, app, by=apps.name_asker(actor))


@router.post("/v1/hosted/{name}/start", status_code=204)
async def start_hosted_app(app: TheApp, signal: TheSignal, session: Session) -> None:
    """Run a stopped app again, its newest release."""
    await apps.start_app(session, signal, app)


# As a stream the lines come as each beat of the runner brings them, for as long as it is open.
@router.get("/v1/hosted/{name}/logs", response_model=None)
async def app_logs(
    app: TheApp, request: Request, sessions: TheSessions, signal: TheSignal, closing: TheClosing, session: Session
) -> schemas.AppLogsResponse | StreamingResponse:
    """The last lines of the app's process, and the runner told to send them again."""
    first = await logs.ask_for_logs(session, app)
    if not sse.wants_sse(request):
        return schemas.AppLogsResponse.of(first)
    return sse.stream(sse.pace(_frames(logs.follow_logs(sessions, signal, app, first)), closing=closing))


@router.delete("/v1/hosted/{name}", status_code=204)
async def delete_hosted_app(app: TheApp, cache: TheKeyCache, signal: TheSignal, session: Session) -> None:
    """Stop hosting the app: its releases go, and its token is revoked."""
    await apps.delete_app(session, cache, signal, app)


async def _frames(followed: AsyncIterator[logs.Logs]) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for lines in followed:
        yield sse.frame(schemas.AppLogsResponse.of(lines).model_dump_json(), event="app.logs")
