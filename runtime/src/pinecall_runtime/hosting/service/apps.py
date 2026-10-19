"""What the box hosts for an org: an app with the token its process runs on, and its releases."""

import hashlib
import io
import re
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.hosting.models import HostedRelease
from pinecall_runtime.hosting.repository import AppStanding, HostedAppRepository, ReleaseRepository
from pinecall_runtime.kit.crypto import Vault, fingerprint
from pinecall_runtime.kit.text import parse_slug

# The ceilings of one upload: what travels, what it unpacks to, and how many files.
LARGEST_SOURCE = 10 * 1024 * 1024
LARGEST_UNPACKED = 100 * 1024 * 1024
MOST_FILES = 5000
# A host name is 63 characters at most, and an app's name is part of it whole.
LONGEST_NAME = 40
STAMP = 8
LABEL = "hosted app {name}"
# The two kinds of hosted app: code the runner starts, and a Studio agent the gateway holds.
CODE = "code"
STUDIO = "studio"

TOO_BIG = "a release's sources are {limit} MB at most packed"
TOO_LONG_A_NAME = "an app's name is {limit} characters at most, and {name} is {length}"
NOT_A_TARBALL = "a release is a gzipped tarball of the project's sources, and this is not one"
UNPACKS_TOO_BIG = "a release unpacks to {limit} MB at most, and this one passes it"
TOO_MANY_FILES = "a release holds {limit} files at most: leave node_modules and build output out"
NOT_A_FILE = "{path} is a link or a device: a release holds files and folders only"
LEAVES_THE_PROJECT = "{path} leaves the project's folder: every path of a release stays inside it"
NOT_HOSTED = "the box hosts no app called {name} for this org in {env}"
NOT_CODE = "{name} is a Studio agent: it is edited in the console's Studio, never uploaded as sources"
NO_RELEASE = "{name} has no release {release}"

# <name>-r<release>-<stamp>: the release is read back off it, so a report names nothing else.
A_HOST = re.compile(rf"^(?P<name>[a-z0-9-]+)-r(?P<release>[1-9][0-9]*)-[0-9a-f]{{{STAMP}}}$")


@dataclass(frozen=True, slots=True)
class App:
    """Which app: the org it is hosted for, the env it runs in, and its name."""

    org: str
    env: Env
    name: str


@dataclass(frozen=True, slots=True)
class AppStatus:
    """A hosted app as the runner left it: its newest release, what serves it, and what failed."""

    org: str
    name: str
    created_by: str
    created_at: datetime
    # None before the first release; the rest of the newest release is None with it.
    release: int | None
    sha256: str | None
    # The name the release's process runs under: one release under one set of secrets.
    host: str | None
    live_release: int | None
    # Why the wanted host failed to build or start; None when it did not, or was never tried.
    failed_why: str | None
    # A person stopped it: the runner is not told to run it, and its releases stay.
    stopped: bool = False
    kind: str = CODE


@dataclass(frozen=True, slots=True)
class Runnable:
    """An app a runner is to run: its newest release, the host it runs under, and what serves."""

    org: str
    name: str
    release: int
    sha256: str
    host: str
    # The host was reported failed: the runner leaves it alone.
    failed: bool
    logs_wanted: bool
    live_host: str | None


@dataclass(frozen=True, slots=True)
class StudioRelease:
    """A Studio agent the gateway holds: whose, its name, and its newest release's definition."""

    org: str
    name: str
    release: int
    definition: bytes


@dataclass(frozen=True, slots=True)
class Source:
    """One upload, checked: the tarball as it came, and its sha256."""

    data: bytes
    sha256: str


def checked_name(name: str) -> str:
    """The name as an app's: a slug short enough to be part of a host name."""
    if len(parse_slug(name)) > LONGEST_NAME:
        raise ValidationError(TOO_LONG_A_NAME.format(limit=LONGEST_NAME, name=name, length=len(name)))
    return name


# What the process calls its machine, which is what the gateway's list of processes shows, and the
# name of its container on a machine every org's apps share: the stamp is of the org, the env and
# the app too, so two orgs' apps of one name and one source never meet, and of the org's secrets,
# so a changed secret is a new host.
def host_of(app: App, release: int, sha256: str, secrets: str) -> str:
    """The host name one release of the app runs under, with the org's secrets as they are."""
    stamped = f"{app.org}:{app.env.value}:{app.name}:{release}:{sha256}:{secrets}"
    return f"{app.name}-r{release}-{hashlib.sha256(stamped.encode()).hexdigest()[:STAMP]}"


def is_a_host_of(name: str, host: str) -> bool:
    """Whether the host is one a release of the app runs under, whichever release."""
    named = A_HOST.match(host)
    return named is not None and named["name"] == name


def release_of(host: str) -> int | None:
    """The release a host runs, read off its name; None for a name that is no host's."""
    named = A_HOST.match(host)
    return None if named is None else int(named["release"])


# Read here, before it is kept, so whoever unpacks a release later unpacks nothing but files
# and folders under the project's own folder.
def checked_source(data: bytes) -> Source:
    """The upload as a release's sources; refused for anything but a safe tarball."""
    if len(data) > LARGEST_SOURCE:
        raise ValidationError(TOO_BIG.format(limit=LARGEST_SOURCE >> 20))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tarball:
            _check_members(tarball)
    except (tarfile.TarError, OSError, EOFError) as unreadable:
        raise ValidationError(NOT_A_TARBALL) from unreadable
    return Source(data=data, sha256=hashlib.sha256(data).hexdigest())


async def list_apps(session: AsyncSession, org: str, env: Env) -> list[AppStatus]:
    """The apps the box hosts for the org in the env, by name, stopped ones too."""
    return [_status(standing) for standing in await HostedAppRepository(session).standing(env, org)]


# Every org's: what the env's runner is told to have running. A stopped app is left out, and a
# runner stops what it is not told to run; one with no release yet has nothing to run.
async def hosted_in(session: AsyncSession, env: Env) -> list[Runnable]:
    """Every app the box runs in the env, by org and name."""
    return [
        _runnable(standing)
        for standing in await HostedAppRepository(session).standing(env, None)
        if standing.app.is_running and standing.release is not None and standing.app.kind == CODE
    ]


# What the gateway holds itself: no runner starts a Studio agent, and a stopped one is not held.
async def studio_in(session: AsyncSession, env: Env, org: str | None = None) -> list[StudioRelease]:
    """Every Studio agent running in the env, one org's or every org's, its newest definition."""
    releases = ReleaseRepository(session)
    held: list[StudioRelease] = []
    for standing in await HostedAppRepository(session).standing(env, org):
        app = standing.app
        if app.kind != STUDIO or not app.is_running or standing.release is None:
            continue
        found = await releases.get(app.org, env, app.name, standing.release)
        if found is not None:
            held.append(StudioRelease(org=app.org, name=app.name, release=standing.release, definition=found.source))
    return held


async def studio_serving(session: AsyncSession, env: Env) -> list[tuple[str, str]]:
    """Every Studio agent running in the env, as an (org, name): what the meter counts as serving."""
    return [
        (standing.app.org, standing.app.name)
        for standing in await HostedAppRepository(session).standing(env, None)
        if standing.app.kind == STUDIO and standing.app.is_running and standing.release is not None
    ]


async def check_code(session: AsyncSession, app: App) -> None:
    """Refuse sources for a Studio agent: its releases are definitions the console writes."""
    if await kind_of(session, app) == STUDIO:
        raise ValidationError(NOT_CODE.format(name=app.name))


async def kind_of(session: AsyncSession, app: App) -> str | None:
    """`code` or `studio`; None for an app the box does not host."""
    found = await HostedAppRepository(session).get(app.org, app.env, app.name)
    return None if found is None else found.kind


async def open_studio(session: AsyncSession, app: App, *, created_by: str) -> None:
    """Start hosting a Studio agent: a hosted app with no token, since no process of its own runs it."""
    await HostedAppRepository(session).open(
        app.org, app.env, app.name, key_fingerprint="", sealed_key="", created_by=created_by, kind=STUDIO
    )


async def is_hosted(session: AsyncSession, app: App) -> bool:
    """Whether the box already hosts the app."""
    return await HostedAppRepository(session).get(app.org, app.env, app.name) is not None


# The token is the org's and the env's, a server's: what `pinecall start` would be given by hand.
async def open_app(session: AsyncSession, vault: Vault, app: App, *, created_by: str) -> None:
    """Start hosting the app: a server's token minted for its process, kept sealed."""
    issue = keys.Issue(
        org=app.org, env=app.env, scopes=keys.SERVER_SCOPES, label=LABEL.format(name=app.name), created_by=created_by
    )
    _, secret = await keys.issue_key(session, issue)
    opened = await HostedAppRepository(session).open(
        app.org,
        app.env,
        app.name,
        key_fingerprint=fingerprint(secret),
        sealed_key=vault.seal(secret),
        created_by=created_by,
    )
    if not opened:
        await keys.revoke_fingerprint(session, fingerprint(secret))


async def keep_release(session: AsyncSession, app: App, source: Source, *, author: str, note: str) -> HostedRelease:
    """Keep the upload as the next release, the oldest past ten let go; NotFound if not hosted."""
    locked = await HostedAppRepository(session).get_locked(app.org, app.env, app.name)
    if locked is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    releases = ReleaseRepository(session)
    kept = await releases.keep(
        app.org, app.env, app.name, source=source.data, sha256=source.sha256, author=author, note=note
    )
    await releases.prune(app.org, app.env, app.name, newest=kept.release, live=locked.live_release)
    return kept


async def releases_of(session: AsyncSession, app: App) -> Sequence[HostedRelease]:
    """The app's releases, newest first; NotFound for an app the box does not host."""
    if not await is_hosted(session, app):
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    return await ReleaseRepository(session).of_app(app.org, app.env, app.name)


# Checked when it was kept: what comes back is a release's sources as they are.
async def source_of(session: AsyncSession, app: App, release: int) -> Source:
    """The tarball one release was uploaded as; NotFound for a release nobody sent."""
    found = await ReleaseRepository(session).get(app.org, app.env, app.name, release)
    if found is None:
        raise NotFound(NO_RELEASE.format(name=app.name, release=release))
    return Source(data=bytes(found.source), sha256=found.sha256)


async def key_of(session: AsyncSession, vault: Vault, app: App) -> str:
    """The server's token the app's process runs on, opened; NotFound for an app not hosted."""
    found = await HostedAppRepository(session).get(app.org, app.env, app.name)
    if found is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    return vault.open(found.sealed_key)


# A report names its host, and a host names its release: one about a release since replaced is
# kept as what it is, and says nothing of the release wanted now.
async def record_live(session: AsyncSession, app: App, host: str, *, runner: str) -> None:
    """Record that the host serves the app now, and with it the release it runs."""
    await HostedAppRepository(session).went_live(
        app.org, app.env, app.name, release=release_of(host), host=host, runner=runner
    )


async def record_failed(session: AsyncSession, app: App, host: str, *, why: str, runner: str) -> None:
    """Record that the host did not build, start or stay up, and why."""
    await HostedAppRepository(session).failed(app.org, app.env, app.name, host=host, why=why, runner=runner)


async def delete_app(session: AsyncSession, app: App) -> str:
    """Stop hosting the app: its releases go, and its token opens nothing from the next request."""
    repository = HostedAppRepository(session)
    found = await repository.get(app.org, app.env, app.name)
    if found is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    await repository.delete(found)
    if found.key_fingerprint:
        await keys.revoke_fingerprint(session, found.key_fingerprint)
    return found.key_fingerprint


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


def _status(standing: AppStanding) -> AppStatus:
    app = standing.app
    host = _host(standing)
    return AppStatus(
        org=app.org,
        name=app.name,
        created_by=app.created_by,
        created_at=app.created_at,
        release=standing.release,
        sha256=standing.sha256,
        host=host,
        # A Studio agent's newest release is the one held: no runner reports it.
        live_release=standing.release if app.kind == STUDIO else app.live_release,
        failed_why=app.failed_why if host is not None and app.failed_host == host else None,
        stopped=app.stopped_at is not None,
        kind=app.kind,
    )


def _runnable(standing: AppStanding) -> Runnable:
    app, host = standing.app, _host(standing)
    return Runnable(
        org=app.org,
        name=app.name,
        release=standing.release or 0,
        sha256=standing.sha256 or "",
        host=host or "",
        failed=app.failed_host == host,
        logs_wanted=standing.logs_wanted,
        live_host=app.live_host,
    )


def _host(standing: AppStanding) -> str | None:
    if standing.release is None or standing.sha256 is None:
        return None
    app = App(standing.app.org, standing.app.env, standing.app.name)
    return host_of(app, standing.release, standing.sha256, standing.secrets)
