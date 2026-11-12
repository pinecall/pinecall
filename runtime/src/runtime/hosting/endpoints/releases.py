"""An app's releases: deployed, listed, their sources read back, rolled back."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from runtime.accounts.auth import TheKeyCache
from runtime.calls.auth import TheFeeds
from runtime.handles import TheSettings, TheSignal, TheVault
from runtime.hosting import schemas
from runtime.hosting.auth import TheApp, TheNewApp
from runtime.hosting.service import releases
from runtime.kit.http import read_capped_body
from runtime.live.auth import AppKey
from runtime.postgres import Session

router = APIRouter()

GZIP = "application/gzip"


# The body is the tarball, no multipart; the note and the page ride the query.
@router.post("/v1/hosted/{name}/releases")
async def deploy_release(
    app: TheNewApp,
    request: Request,
    actor: AppKey,
    vault: TheVault,
    cache: TheKeyCache,
    feeds: TheFeeds,
    settings: TheSettings,
    session: Session,
    note: Annotated[str, Query(max_length=200)] = "",
    page_dir: Annotated[str | None, Query(max_length=200)] = None,
    page_agent: Annotated[str | None, Query(max_length=80)] = None,
) -> schemas.ReleaseRow:
    """The project's sources as the app's next release, its page's folder and agent with them when it has one."""
    data = await read_capped_body(request, releases.LARGEST_SOURCE, "a release")
    upload = releases.Upload(data=data, note=note, page_dir=page_dir, page_agent=page_agent)
    released = await releases.deploy_release(session, vault, cache, feeds, settings.pages_domain, app, upload, by=actor)
    return schemas.ReleaseRow.of_released(released)


@router.get("/v1/hosted/{name}/releases")
async def list_releases(app: TheApp, settings: TheSettings, session: Session) -> schemas.ReleaseList:
    """The app's releases, newest first."""
    return schemas.ReleaseList.of_released(await releases.list_releases(session, settings.pages_domain, app))


@router.get("/v1/hosted/{name}/releases/{release}/source")
async def release_source(app: TheApp, release: int, session: Session) -> Response:
    """The tarball one release was uploaded as."""
    return Response((await releases.source_of(session, app, release)).data, media_type=GZIP)


@router.post("/v1/hosted/{name}/rollback")
async def roll_back_release(
    app: TheApp,
    body: schemas.RollbackRequest,
    actor: AppKey,
    feeds: TheFeeds,
    signal: TheSignal,
    settings: TheSettings,
    session: Session,
) -> schemas.ReleaseRow:
    """An earlier release kept again as the app's next release, its page with it."""
    released = await releases.roll_back_release(
        session, feeds, signal, settings.pages_domain, app, body.release, by=actor
    )
    return schemas.ReleaseRow.of_released(released)
