"""The hosting endpoints: an org's hosted apps, their releases and secrets, and the runner's."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from pinecall_runtime.accounts.auth import Client, KeyCacheDep, TurnstileDep
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.calls.schemas import IssueCodeRequest, IssueCodeResponse, MintTokenRequest, MintTokenResponse
from pinecall_runtime.calls.service import visitors
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.hosting import schemas, service
from pinecall_runtime.hosting.auth import AppKey, RunnerKey, TheOperator
from pinecall_runtime.kit import sse
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.handles import Handles, TheHandles
from pinecall_runtime.kit.http import capped_body
from pinecall_runtime.postgres import Session, box_wide, scope_to
from pinecall_runtime.studio import service as studio
from pinecall_runtime.wire.feed import AppFailed, ReleaseChanged

router = APIRouter()

GZIP = "application/gzip"
ROLLED_BACK = "rollback to release {release}"
RETRY_MS = 1000
NO_PAGE = "no page is served at this name"


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
    page_dir: Annotated[str | None, Query(max_length=200)] = None,
    page_agent: Annotated[str | None, Query(max_length=80)] = None,
) -> schemas.ReleaseRow:
    """The project's sources as the app's next release, its page's folder and agent with them when it has one."""
    app = _app(actor, service.checked_name(name))
    await service.check_code(session, app)
    source = await asyncio.to_thread(
        service.checked_source, await capped_body(request, service.LARGEST_SOURCE, "a release")
    )
    label = service.label_of(await orgs.slug_of(session, actor.org), app)
    page = await asyncio.to_thread(service.checked_page, source, page_dir, page_agent, label)
    author = _asked_by(actor)
    if not await service.is_hosted(session, app):
        hosted = len(await service.list_apps(session, actor.org, actor.env))
        await billing.admit_hosted_app(session, actor.org, actor.env, hosting=hosted)
        await service.open_app(session, handles.vault, app, created_by=author)
    kept = await service.keep_release(
        session,
        app,
        source,
        author=author,
        note=note.strip(),
        page_dir=None if page is None else page.dir,
        page_agent=None if page is None else page.agent,
    )
    # Said once it is stored: a reader the news sends to the release reads it there.
    await session.commit()
    serving.logs.announce(actor.scope, "release.changed", ReleaseChanged(app=app.name, release=kept.release))
    pages = handles.settings.pages_domain
    served = page is not None and pages is not None
    return schemas.ReleaseRow.of(kept).model_copy(update={"page_url": f"https://{label}.{pages}/" if served else None})


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
    await _studio_changed(session, handles, actor)
    serving.logs.announce(actor.scope, "release.changed", ReleaseChanged(app=app.name, release=kept.release))
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
    changed: list[tuple[Scope, ReleaseChanged]] = []
    with box_wide():
        for report in body.reports:
            app = service.App(org=report.org, env=env, name=report.name)
            release = service.release_of(report.host)
            if report.state == "live":
                await service.record_live(session, app, report.host, runner=body.runner)
            elif await service.record_failed(session, app, report.host, why=report.why, runner=body.runner):
                # The first report of this host failing is the org's alert; the next beats repeat nothing.
                failed = AppFailed(app=report.name, host=report.host, release=release, why=report.why)
                await alerts.raise_alert(session, serving, Scope(report.org, env), None, failed)
            changed.append((Scope(report.org, env), ReleaseChanged(app=report.name, release=release or 0)))
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
    # A release live or failed is said once the beat is stored: the console reads the release when told.
    await session.commit()
    for scope, news in changed:
        serving.logs.announce(scope, "release.changed", news)
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


# The box's own names win over an org's secret of the same name: the endpoint refuses those names. A
# box with no name says no address, and its runner hands its apps the one it dials itself.
@router.get("/v1/runner/apps/{org}/{name}/environment")
async def runner_environment(
    org: str, name: str, actor: RunnerKey, handles: TheHandles, session: Session
) -> schemas.AppEnvironment:
    """What the app's process is started with: the org's secrets, its token, the gateway."""
    address = handles.settings.address
    with box_wide():
        secrets = await service.environment_of(session, handles.vault, org, actor.env)
        token = await service.key_of(session, handles.vault, service.App(org=org, env=actor.env, name=name))
    named = {} if address is None else {"PINECALL_URL": address}
    return schemas.AppEnvironment(environment={**secrets, "PINECALL_KEY": token, **named})


# ── an app's page ──
#
# Served at the app's own name, never at the gateway's: `PageHosts` (kit/middleware.py) sends a
# request that came in by a page's name here, and each endpoint answers only the name it came in by,
# so a tenant's page is never a document of the console's origin.

PAGE_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}
# The page itself is read again on every visit; a built asset is kept a while.
THE_PAGE = {**PAGE_HEADERS, "Cache-Control": "no-store"}
AN_ASSET = {**PAGE_HEADERS, "Cache-Control": "public, max-age=300"}
# How many tickets and codes one address is given in a minute.
TICKETS_A_MINUTE = 6


async def _paged(host: str, request: Request, handles: Handles, session: Session) -> service.Paged:
    domain = handles.settings.pages_domain
    came_in_by = request.headers.get("host", "").split(":")[0].lower()
    named = None if domain is None else service.named_by(host, domain)
    if named is None or came_in_by != host.lower():
        raise NotFound(NO_PAGE)
    slug, name, env = named
    with box_wide():
        org = await orgs.find_org(session, slug)
        # Read as the box, ended here: what follows is read as the org whose page it is.
        await session.commit()
    if org is None or org.slug != slug:
        raise NotFound(NO_PAGE)
    scope_to(org.id)
    return await service.page_at(session, service.App(org=org.id, env=env, name=name))


def _visitor(paged: service.Paged) -> Actor:
    app = paged.app
    key_id = f"page:{app.org}:{app.env.value}:{app.name}"
    return Actor(key_id=key_id, org=app.org, env=app.env, scopes=frozenset({KeyScope.talk}), label="page")


async def _admitted(host: str, token: str | None, client: str, turnstile: TurnstileDep, handles: Handles) -> None:
    await AttemptThrottle(handles.sessions, TICKETS_A_MINUTE).check(f"{client} page", "calls from here")
    await turnstile.check(token, "page", client, on=host.lower())


@router.get("/v1/pages/{host}/pinecall/config")
async def page_config(host: str, request: Request, handles: TheHandles, session: Session) -> schemas.PageConfig:
    """What an app's page needs before it asks for a ticket: its agent, and the captcha's site key."""
    paged = await _paged(host, request, handles, session)
    return schemas.PageConfig(agent=paged.page.agent, turnstile=handles.settings.turnstile_site_key)


@router.post("/v1/pages/{host}/pinecall/token", status_code=201)
async def page_ticket(
    host: str,
    body: schemas.PageTicketRequest,
    request: Request,
    client: Client,
    turnstile: TurnstileDep,
    serving: TheServing,
    handles: TheHandles,
    session: Session,
) -> MintTokenResponse:
    """A seat in a new call with the page's agent, for a visitor who passed the captcha."""
    paged = await _paged(host, request, handles, session)
    await _admitted(host, body.turnstile, client, turnstile, handles)
    asked = MintTokenRequest(agent=paged.page.agent, scope=body.scope, resume=body.resume)
    return await visitors.mint_room_token(session, serving, _visitor(paged), asked)


@router.post("/v1/pages/{host}/pinecall/code", status_code=201)
async def page_code(
    host: str,
    body: schemas.PageCodeRequest,
    request: Request,
    client: Client,
    turnstile: TurnstileDep,
    serving: TheServing,
    handles: TheHandles,
    session: Session,
) -> IssueCodeResponse:
    """A code a visitor keys when they call the page's agent, so the page follows that call."""
    paged = await _paged(host, request, handles, session)
    await _admitted(host, body.turnstile, client, turnstile, handles)
    return await visitors.issue_code(session, serving, _visitor(paged), IssueCodeRequest(agent=paged.page.agent))


@router.get("/v1/pages/{host}/files/{path:path}")
async def page_file(host: str, path: str, request: Request, handles: TheHandles, session: Session) -> Response:
    """One file of an app's page, from the release that runs; a path that names no file is the page itself."""
    paged = await _paged(host, request, handles, session)
    found = await service.file_of(session, paged, path)
    return Response(found.body, media_type=found.media_type, headers=THE_PAGE if found.is_the_page else AN_ASSET)


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
