"""The hosting endpoints: an org's hosted apps, their releases and secrets, and the runner's."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from pinecall_runtime.accounts.auth import KeyCacheDep
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.hosting import schemas, service
from pinecall_runtime.hosting.auth import AppKey, RunnerKey, TheOperator
from pinecall_runtime.kit import sse
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.handles import Handles, TheHandles
from pinecall_runtime.kit.http import capped_body
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.studio import service as studio
from pinecall_runtime.wire.feed import ReleaseChanged

router = APIRouter()

GZIP = "application/gzip"
ROLLED_BACK = "rollback to release {release}"
NO_NAME = "this box has no PINECALL_DOMAIN: a hosted app has no gateway address to dial"
RETRY_MS = 1000


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


def _app(actor: Actor, name: str) -> service.App:
    return service.App(org=actor.org, env=actor.env, name=name)


# Committed first: the gateways that hear it read the rows this request wrote.
async def _studio_changed(session: Session, handles: Handles, actor: Actor) -> None:
    await session.commit()
    studio.changed(handles.signal, actor.org, actor.env)


# ── the org's hosted apps ──


@router.get("/v1/hosted")
async def list_hosted_apps(actor: AppKey, session: Session) -> schemas.HostedAppList:
    """The apps the box hosts for the org in this env, by name."""
    listed = await service.list_apps(session, actor.org, actor.env)
    return schemas.HostedAppList(apps=[schemas.HostedAppRow.of(app) for app in listed])


# The body is the tarball, no multipart; the note rides the query. An app's first release is
# what makes it: counted against the org's quota, and given the token its process will run on.
@router.post("/v1/hosted/{name}/releases")
async def upload_release(
    name: str,
    request: Request,
    actor: AppKey,
    serving: TheServing,
    handles: TheHandles,
    session: Session,
    note: Annotated[str, Query(max_length=200)] = "",
) -> schemas.ReleaseRow:
    """The project's sources as the app's next release."""
    app = _app(actor, service.checked_name(name))
    await service.check_code(session, app)
    source = await asyncio.to_thread(
        service.checked_source, await capped_body(request, service.LARGEST_SOURCE, "a release")
    )
    author = _asked_by(actor)
    if not await service.is_hosted(session, app):
        hosted = len(await service.list_apps(session, actor.org, actor.env))
        await billing.admit_hosted_app(session, actor.org, actor.env, hosting=hosted)
        await service.open_app(session, handles.vault, app, created_by=author)
    kept = await service.keep_release(session, app, source, author=author, note=note.strip())
    serving.logs.announce(actor.scope, "release.changed", ReleaseChanged(app=app.name, release=kept.release))
    return schemas.ReleaseRow.of(kept)


@router.get("/v1/hosted/{name}/releases")
async def list_releases(name: str, actor: AppKey, session: Session) -> schemas.ReleaseList:
    """The app's releases, newest first."""
    kept = await service.releases_of(session, _app(actor, name))
    return schemas.ReleaseList(releases=[schemas.ReleaseRow.of(release) for release in kept])


@router.get("/v1/hosted/{name}/releases/{release}/source")
async def release_source(name: str, release: int, actor: AppKey, session: Session) -> Response:
    """The tarball one release was uploaded as."""
    source = await service.source_of(session, _app(actor, name), release)
    return Response(source.data, media_type=GZIP)


@router.post("/v1/hosted/{name}/stop", status_code=204)
async def stop_hosted_app(name: str, actor: AppKey, handles: TheHandles, session: Session) -> None:
    """Stop running the app: its process drains, and its releases and token stay."""
    await service.stop_app(session, _app(actor, name), by=_asked_by(actor))
    await _studio_changed(session, handles, actor)


@router.post("/v1/hosted/{name}/start", status_code=204)
async def start_hosted_app(name: str, actor: AppKey, handles: TheHandles, session: Session) -> None:
    """Run a stopped app again, its newest release."""
    await service.start_app(session, _app(actor, name))
    await _studio_changed(session, handles, actor)


@router.post("/v1/hosted/{name}/rollback")
async def roll_back_release(
    name: str,
    body: schemas.RollbackRequest,
    actor: AppKey,
    serving: TheServing,
    handles: TheHandles,
    session: Session,
) -> schemas.ReleaseRow:
    """An earlier release's sources kept again as the app's next release."""
    app = _app(actor, name)
    source = await service.source_of(session, app, body.release)
    kept = await service.keep_release(
        session, app, source, author=_asked_by(actor), note=ROLLED_BACK.format(release=body.release)
    )
    serving.logs.announce(actor.scope, "release.changed", ReleaseChanged(app=app.name, release=kept.release))
    await _studio_changed(session, handles, actor)
    return schemas.ReleaseRow.of(kept)


# The runner sends them on its next beat: a first ask answers what it sent last, or nothing. As a
# stream the lines come as each beat brings them, for as long as it is open.
@router.get("/v1/hosted/{name}/logs", response_model=None)
async def app_logs(
    name: str, request: Request, actor: AppKey, handles: TheHandles, session: Session
) -> schemas.AppLogsResponse | StreamingResponse:
    """The last lines of the app's process, and the runner told to send them again."""
    app = _app(actor, name)
    first = _logs_of(name, await service.ask_for_logs(session, app))
    if sse.wants_sse(request):
        return sse.streamed(sse.paced(_logs_followed(handles, app, first), closing=request.app.state.closing))
    return first


@router.get("/v1/hosted/usage")
async def hosted_usage(
    actor: AppKey, session: Session, month: Annotated[str | None, Query()] = None
) -> schemas.ServedPage:
    """The time the org's apps served here per UTC day, in one month: this one by default."""
    since, until = service.month_of(month)
    rows = await service.served(session, since, until, org=actor.org, env=actor.env)
    return service.served_page(since, until, rows)


@router.delete("/v1/hosted/{name}", status_code=204)
async def drop_hosted_app(name: str, actor: AppKey, handles: TheHandles, session: Session, cache: KeyCacheDep) -> None:
    """Stop hosting the app: its releases go, and its token is revoked."""
    stopped = await service.delete_app(session, _app(actor, name))
    if stopped:
        cache.forget(fingerprint_=stopped)
    await _studio_changed(session, handles, actor)


# ── the org's secrets ──


@router.get("/v1/secrets")
async def list_secrets(actor: AppKey, session: Session) -> schemas.SecretList:
    """The org's secrets in this env, by name; never a value."""
    return await _secrets(session, actor)


@router.put("/v1/secrets/{name}")
async def put_secret(
    name: str, body: schemas.PutSecretRequest, actor: AppKey, handles: TheHandles, session: Session
) -> schemas.SecretList:
    """Keep one secret, sealed, replacing the value it had; the org's list after it."""
    secret = service.Secret(env=actor.env, name=name, value=body.value)
    await service.put_secret(session, handles.vault, actor.org, secret, by=_asked_by(actor))
    return await _secrets(session, actor)


@router.delete("/v1/secrets/{name}")
async def drop_secret(name: str, actor: AppKey, session: Session) -> schemas.SecretList:
    """Forget one secret; the org's list after it, 404 for a name nobody set."""
    await service.delete_secret(session, actor.org, actor.env, name)
    return await _secrets(session, actor)


# ── the operator's ──


@router.get("/v1/ops/hosted-usage")
async def box_hosted_usage(
    _actor: TheOperator, session: Session, month: Annotated[str | None, Query()] = None
) -> schemas.ServedPage:
    """The time every org's apps served, both envs, per UTC day, one month: what bills them."""
    since, until = service.month_of(month)
    with box_wide():
        rows = await service.served(session, since, until)
    return service.served_page(since, until, rows)


# ── the runner's ──


# In this order: what the runner says is kept first, so what it is answered already counts it.
@router.post("/v1/runner/heartbeat")
async def runner_heartbeat(
    body: schemas.RunnerHeartbeatRequest, actor: RunnerKey, serving: TheServing, handles: TheHandles, session: Session
) -> schemas.RunnerHeartbeatResponse:
    """The runner's reports and logs kept, the time served counted, and what it is to run."""
    env = actor.env
    with box_wide():
        for report in body.reports:
            app = service.App(org=report.org, env=env, name=report.name)
            if report.state == "live":
                await service.record_live(session, app, report.host, runner=body.runner)
            else:
                await service.record_failed(session, app, report.host, why=report.why, runner=body.runner)
            changed = ReleaseChanged(app=report.name, release=service.release_of(report.host) or 0)
            serving.logs.announce(Scope(report.org, env), "release.changed", changed)
        for logs in body.logs:
            app = service.App(org=logs.org, env=env, name=logs.name)
            await service.keep_logs(session, app, host=logs.host, lines=logs.lines)
            handles.signal.publish(service.LOGS_CHANNEL.format(org=app.org, env=app.env.value, name=app.name), b"")
        wanted = await service.hosted_in(session, env)
        hosts = {app.org: _hosts_of(serving, app.org, env) for app in wanted}
        serving_now = [
            (app.org, app.name) for app in wanted if any(service.is_a_host_of(app.name, h) for h in hosts[app.org])
        ]
        # A Studio agent serves wherever a gateway holds it: it is counted while it runs, as an app is.
        serving_now += await service.studio_serving(session, env)
        await service.count_serving(session, env, serving_now, datetime.now(UTC))
    return schemas.RunnerHeartbeatResponse(
        env=env,
        apps=[
            schemas.WantedApp(
                org=app.org,
                name=app.name,
                release=app.release,
                sha256=app.sha256,
                host=app.host,
                registered=app.host in hosts[app.org],
                failed=app.failed,
                logs_wanted=app.logs_wanted,
                live_host=app.live_host,
            )
            for app in wanted
        ],
    )


@router.get("/v1/runner/apps/{org}/{name}/releases/{release}/source")
async def runner_source(org: str, name: str, release: int, actor: RunnerKey, session: Session) -> Response:
    """The tarball of one release of any org's app in the runner's env."""
    with box_wide():
        source = await service.source_of(session, service.App(org=org, env=actor.env, name=name), release)
    return Response(source.data, media_type=GZIP)


# The box's own names win over an org's secret of the same name: the endpoint refuses those names.
@router.get("/v1/runner/apps/{org}/{name}/environment")
async def runner_environment(
    org: str, name: str, actor: RunnerKey, handles: TheHandles, session: Session
) -> schemas.AppEnvironment:
    """What the app's process is started with: the org's secrets, its token, the gateway."""
    address = handles.settings.address
    if address is None:
        raise ServiceUnavailable(NO_NAME)
    with box_wide():
        secrets = await service.environment_of(session, handles.vault, org, actor.env)
        token = await service.key_of(session, handles.vault, service.App(org=org, env=actor.env, name=name))
    return schemas.AppEnvironment(environment={**secrets, "PINECALL_KEY": token, "PINECALL_URL": address})


async def _secrets(session: Session, actor: Actor) -> schemas.SecretList:
    listed = await service.list_secrets(session, actor.org, actor.env)
    return schemas.SecretList(secrets=[schemas.SecretRow.of(secret) for secret in listed])


def _logs_of(name: str, logs: service.Logs) -> schemas.AppLogsResponse:
    return schemas.AppLogsResponse(name=name, host=logs.host, lines=logs.lines, at=logs.at)


# Each time the runner's lines for the app are kept, on any gateway, they are sent; asked again
# each time, so the runner keeps sending for as long as the stream is open.
async def _logs_followed(handles: Handles, app: service.App, first: schemas.AppLogsResponse) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    listening = await handles.signal.subscribe(
        service.LOGS_CHANNEL.format(org=app.org, env=app.env.value, name=app.name)
    )
    try:
        yield sse.frame(first.model_dump_json(), event="app.logs")
        async for _ in listening:
            async with handles.sessions.begin() as session:
                logs = await service.ask_for_logs(session, app)
            yield sse.frame(_logs_of(app.name, logs).model_dump_json(), event="app.logs")
    finally:
        listening.close()


# What each of the org's processes in the env says it runs on: an app serves while one of them
# is a host of its own, whichever release, and that time is what the org is billed for.
def _hosts_of(serving: calls.Serving, org: str, env: Env) -> frozenset[str]:
    return frozenset(app.host for app in serving.live.apps_of(org, env) if app.host is not None)
