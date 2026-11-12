"""A release of a hosted app: its sources checked, kept as the next number, deployed and rolled back."""

import asyncio
import hashlib
import io
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.billing import service as billing
from runtime.calls.log import Feeds
from runtime.enums import AppKind
from runtime.exceptions import NotFound, ValidationError
from runtime.hosting.models import HostedRelease
from runtime.hosting.repository import HostedAppRepository, ReleaseRepository
from runtime.hosting.service import apps, pages
from runtime.hosting.service.apps import NOT_HOSTED, App
from runtime.kit.commit import run_after_commit
from runtime.kit.crypto import Vault
from runtime.kit.text import parse_slug
from runtime.signal import Signal
from runtime.wire.feed import ReleaseChanged

# The ceilings of one upload: what travels, what it unpacks to, and how many files.
LARGEST_SOURCE = 10 * 1024 * 1024
LARGEST_UNPACKED = 100 * 1024 * 1024
MOST_FILES = 5000
# A host name is 63 characters at most, and an app's name is part of it whole.
LONGEST_NAME = 40
# Each release is its whole tarball: an app keeps its newest ten, and the one its runner serves
# while a newer one starts, never more.
KEPT_RELEASES = 10
ROLLED_BACK = "rollback to release {release}"

TOO_BIG = "a release's sources are {limit} MB at most packed"
TOO_LONG_A_NAME = "an app's name is {limit} characters at most, and {name} is {length}"
NOT_A_TARBALL = "a release is a gzipped tarball of the project's sources, and this is not one"
UNPACKS_TOO_BIG = "a release unpacks to {limit} MB at most, and this one passes it"
TOO_MANY_FILES = "a release holds {limit} files at most: leave node_modules and build output out"
NOT_A_FILE = "{path} is a link or a device: a release holds files and folders only"
LEAVES_THE_PROJECT = "{path} leaves the project's folder: every path of a release stays inside it"
NOT_CODE = "{name} is a Studio agent: it is edited in the console's Studio, never uploaded as sources"
NO_RELEASE = "{name} has no release {release}"


@dataclass(frozen=True, slots=True)
class Source:
    """One upload, checked: the tarball as it came, and its sha256."""

    data: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class Upload:
    """What a deploy sends: the tarball, a note, and its page's folder and agent when it has one."""

    data: bytes
    note: str = ""
    page_dir: str | None = None
    page_agent: str | None = None


@dataclass(frozen=True, slots=True)
class Released:
    """A release as a person reads it: its row, and where its page is served when it has one."""

    release: HostedRelease
    page_url: str | None


def check_name(name: str) -> str:
    """The name as an app's: a slug short enough to be part of a host name."""
    if len(parse_slug(name)) > LONGEST_NAME:
        raise ValidationError(TOO_LONG_A_NAME.format(limit=LONGEST_NAME, name=name, length=len(name)))
    return name


# Read here, before it is kept, so whoever unpacks a release later unpacks nothing but files
# and folders under the project's own folder. It unpacks: called in a thread.
def check_source(data: bytes) -> Source:
    """The upload as a release's sources; refused for anything but a safe tarball."""
    if len(data) > LARGEST_SOURCE:
        raise ValidationError(TOO_BIG.format(limit=LARGEST_SOURCE >> 20))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tarball:
            _check_members(tarball)
    except (tarfile.TarError, OSError, EOFError) as unreadable:
        raise ValidationError(NOT_A_TARBALL) from unreadable
    return Source(data=data, sha256=hashlib.sha256(data).hexdigest())


# An app's first release is what makes it: counted against the org's quota, and given the token its
# process will run on. Said to whoever follows the org once it is stored: a reader the news sends to
# the release reads it there.
async def deploy_release(
    session: AsyncSession,
    vault: Vault,
    cache: accounts.KeyCache,
    feeds: Feeds,
    pages_domain: str | None,
    app: App,
    upload: Upload,
    *,
    by: Actor,
) -> Released:
    """The project's sources as the app's next release, its page with them when it has one."""
    kind = await apps.find_kind(session, app)
    if kind is not None and kind is not AppKind.code:
        raise ValidationError(NOT_CODE.format(name=app.name))
    source = await asyncio.to_thread(check_source, upload.data)
    label = pages.label_page(await accounts.slug_of(session, app.org), app)
    page = await asyncio.to_thread(pages.check_page, source.data, upload.page_dir, upload.page_agent, label)
    author = apps.name_asker(by)
    if kind is None:
        hosting = len(await apps.list_standing(session, app.env, app.org))
        await billing.admit_hosted_app(session, app.org, app.env, hosting=hosting)
        await apps.open_app(session, vault, cache, app, AppKind.code, created_by=author)
    kept = await keep_release(session, app, source, author=author, note=upload.note.strip(), page=page)
    _announce(session, feeds, by, kept)
    return Released(kept, pages.url_of(label, pages_domain) if page is not None else None)


# The earlier release goes again whole: its sources, and its page with them.
async def roll_back_release(
    session: AsyncSession, feeds: Feeds, signal: Signal, pages_domain: str | None, app: App, release: int, *, by: Actor
) -> Released:
    """An earlier release kept again as the app's next release."""
    earlier = await _get(session, app, release)
    page = None
    if earlier.page_dir is not None and earlier.page_agent is not None:
        page = pages.Page(dir=earlier.page_dir, agent=earlier.page_agent)
    source = Source(data=bytes(earlier.source), sha256=earlier.sha256)
    note = ROLLED_BACK.format(release=release)
    kept = await keep_release(session, app, source, author=apps.name_asker(by), note=note, page=page)
    apps.tell_changed(session, signal, app)
    _announce(session, feeds, by, kept)
    return (await _read(session, pages_domain, app, [kept]))[0]


async def keep_release(
    session: AsyncSession, app: App, source: Source, *, author: str, note: str, page: pages.Page | None = None
) -> HostedRelease:
    """Keep the upload as the next release, the oldest past ten let go; NotFound if not hosted."""
    locked = await HostedAppRepository(session).lock(app.org, app.env, app.name)
    if locked is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    releases = ReleaseRepository(session)
    kept = await releases.keep(
        app.org,
        app.env,
        app.name,
        source=source.data,
        sha256=source.sha256,
        author=author,
        note=note,
        page_dir=None if page is None else page.dir,
        page_agent=None if page is None else page.agent,
    )
    await releases.prune(app.org, app.env, app.name, below=kept.release - KEPT_RELEASES, live=locked.live_release)
    return kept


async def list_releases(session: AsyncSession, pages_domain: str | None, app: App) -> list[Released]:
    """The app's releases, newest first; NotFound for an app the box does not host."""
    if await apps.find_kind(session, app) is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    kept = await ReleaseRepository(session).list_of_app(app.org, app.env, app.name)
    return await _read(session, pages_domain, app, kept)


# Checked when it was kept: what comes back is a release's sources as they are.
async def source_of(session: AsyncSession, app: App, release: int) -> Source:
    """The tarball one release was uploaded as; NotFound for a release nobody sent."""
    found = await _get(session, app, release)
    return Source(data=bytes(found.source), sha256=found.sha256)


async def _get(session: AsyncSession, app: App, release: int) -> HostedRelease:
    found = await ReleaseRepository(session).find(app.org, app.env, app.name, release)
    if found is None:
        raise NotFound(NO_RELEASE.format(name=app.name, release=release))
    return found


async def _read(
    session: AsyncSession, pages_domain: str | None, app: App, kept: Sequence[HostedRelease]
) -> list[Released]:
    served = pages.url_of(pages.label_page(await accounts.slug_of(session, app.org), app), pages_domain)
    return [Released(release, served if release.page_dir is not None else None) for release in kept]


def _announce(session: AsyncSession, feeds: Feeds, by: Actor, kept: HostedRelease) -> None:
    news = ReleaseChanged(app=kept.name, release=kept.release)
    run_after_commit(session, lambda: feeds.announce(by.scope, "release.changed", news))


def _check_members(tarball: tarfile.TarFile) -> None:
    unpacked = 0
    for files, member in enumerate(tarball, start=1):
        path = member.name
        if not (member.isfile() or member.isdir()):
            raise ValidationError(NOT_A_FILE.format(path=path))
        if path.startswith("/") or ".." in path.split("/"):
            raise ValidationError(LEAVES_THE_PROJECT.format(path=path))
        unpacked += member.size
        if files > MOST_FILES:
            raise ValidationError(TOO_MANY_FILES.format(limit=MOST_FILES))
        if unpacked > LARGEST_UNPACKED:
            raise ValidationError(UNPACKS_TOO_BIG.format(limit=LARGEST_UNPACKED >> 20))
