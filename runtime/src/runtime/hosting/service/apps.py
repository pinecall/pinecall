"""An app the box hosts for an org: how it stands, and its being opened, stopped, started and let go."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.enums import SERVER_SCOPES, AppKind, Env
from runtime.exceptions import NotFound
from runtime.hosting.repository import HostedAppRepository, StandingRow
from runtime.hosting.service import hostnames, secrets
from runtime.kit.commit import run_after_commit
from runtime.kit.crypto import Vault, fingerprint
from runtime.signal import Signal

LABEL = "hosted app {name}"
# How long after a person asks for an app's logs the runner is told to send them.
LOGS_FOR_S = 60.0
# Said on this channel, to every gateway, when an org's apps changed in an env: the gateways that hold
# the apps with no process of their own read them again. The name is the one the release before says it by.
APPS_CHANGED = "studio"

NOT_HOSTED = "the box hosts no app called {name} for this org in {env}"


@dataclass(frozen=True, slots=True)
class App:
    """Which app: the org it is hosted for, the env it runs in, and its name."""

    org: str
    env: Env
    name: str


# One value for every reader: a person's list reads it, the runner's answer reads it, the meter reads it.
@dataclass(frozen=True, slots=True)
class Standing:
    """A hosted app as the box holds it now: its newest release, what serves it, and what failed."""

    org: str
    name: str
    kind: AppKind
    created_by: str
    created_at: datetime
    # None before the first release; its sha256 and its host are None with it.
    release: int | None
    sha256: str | None
    # The name the newest release's process runs under: one release under one set of secrets.
    host: str | None
    # The release serving now and the host that last went live: it serves until the one wanted registers.
    live_release: int | None
    live_host: str | None
    # The newest release's host was reported failed, and why: the runner leaves it alone.
    failed: bool
    failed_why: str | None
    # A person stopped it: nothing runs, and its releases and token stay.
    stopped: bool
    logs_wanted: bool
    # Whether a process of the org says it runs on the newest release's host: said by whoever asks the sockets.
    registered: bool = False

    @property
    def is_wanted(self) -> bool:
        """Whether a runner is to have it running: not stopped, released, and a process of its own."""
        return not self.stopped and self.release is not None and self.kind.has_process


class Process(Protocol):
    """One process of an org's as its app socket says it."""

    @property
    def host(self) -> str | None:
        """The machine it said it runs on."""
        ...


class Processes(Protocol):
    """The app sockets open on every gateway, as the live side keeps them."""

    def apps_of(self, org: str, env: Env) -> Sequence[Process]:
        """The org's sockets in the env."""
        ...


async def list_standing(session: AsyncSession, env: Env, org: str | None = None) -> list[Standing]:
    """The apps the box hosts in the env, one org's or every org's, by org and name, stopped ones too."""
    rows = await HostedAppRepository(session).list_standing(env, org, logs_for_s=LOGS_FOR_S)
    return [_standing_of(row, env) for row in rows]


def hosts_of(processes: Processes, org: str, env: Env) -> frozenset[str]:
    """What each of the org's processes in the env says it runs on."""
    return frozenset(process.host for process in processes.apps_of(org, env) if process.host is not None)


# Every org's: what the env's runner is told to have running. A stopped app is left out, and a
# runner stops what it is not told to run; one with no release yet has nothing to run.
async def list_wanted(session: AsyncSession, processes: Processes, env: Env) -> list[Standing]:
    """Every app the env's runner is to have running, each saying whether its newest release registered."""
    wanted = [standing for standing in await list_standing(session, env) if standing.is_wanted]
    hosts = {org: hosts_of(processes, org, env) for org in {standing.org for standing in wanted}}
    return [replace(standing, registered=standing.host in hosts[standing.org]) for standing in wanted]


async def find_kind(session: AsyncSession, app: App) -> AppKind | None:
    """What the app is; None for an app the box does not host."""
    found = await HostedAppRepository(session).find(app.org, app.env, app.name)
    return None if found is None else found.kind


# The token is the org's and the env's, a server's: what `pinecall start` would be given by hand.
async def open_app(session: AsyncSession, vault: Vault, cache: accounts.KeyCache, app: App, *, created_by: str) -> None:
    """Start hosting an app of code: a server's token minted for its process, kept sealed."""
    kind = AppKind.code
    issue = accounts.Issue(
        org=app.org, env=app.env, scopes=SERVER_SCOPES, label=LABEL.format(name=app.name), created_by=created_by
    )
    secret = (await accounts.issue_key(session, issue)).secret
    marked, sealed = fingerprint(secret), vault.seal(secret)
    if not await _open(session, app, kind, created_by=created_by, key_fingerprint=marked, sealed_key=sealed):
        await accounts.revoke_fingerprint(session, cache, marked)


# No token is minted: no process of its own would run on it.
async def open_held_app(session: AsyncSession, app: App, kind: AppKind, *, created_by: str) -> None:
    """Start hosting an app the gateway holds itself, with no process of its own."""
    await _open(session, app, kind, created_by=created_by)


async def stop_app(session: AsyncSession, signal: Signal, app: App, *, by: str) -> None:
    """Stop running the app: the runner drains it, and its releases and token stay."""
    if not await HostedAppRepository(session).stop(app.org, app.env, app.name, by=by):
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    tell_changed(session, signal, app)


# A person's start forgives a host the runner gave up on: the newest release is tried again.
async def start_app(session: AsyncSession, signal: Signal, app: App) -> None:
    """Run a stopped app again, its newest release."""
    if not await HostedAppRepository(session).start(app.org, app.env, app.name):
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    tell_changed(session, signal, app)


async def delete_app(session: AsyncSession, cache: accounts.KeyCache, signal: Signal, app: App) -> None:
    """Stop hosting the app: its releases go, and its token opens nothing from the next request."""
    repository = HostedAppRepository(session)
    found = await repository.find(app.org, app.env, app.name)
    if found is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    await repository.delete(found)
    if found.key_fingerprint:
        await accounts.revoke_fingerprint(session, cache, found.key_fingerprint)
    tell_changed(session, signal, app)


# The box's own names win over an org's secret of the same name, which `secrets.Secret` refuses to
# be given. A box with no name says no address, and its runner hands its apps the one it dials itself.
async def environment_for(session: AsyncSession, vault: Vault, address: str | None, app: App) -> dict[str, str]:
    """What the app's process is started with: the org's secrets, its token, the gateway's address."""
    found = await HostedAppRepository(session).find(app.org, app.env, app.name)
    if found is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    opened = await secrets.environment_of(session, vault, app.org, app.env)
    named = {} if address is None else {"PINECALL_URL": address}
    return {**opened, "PINECALL_KEY": vault.open(found.sealed_key), **named}


# After the commit: the gateways that hear it read the rows this request wrote.
def tell_changed(session: AsyncSession, signal: Signal, app: App) -> None:
    """Tell every gateway, once the transaction commits, that the org's apps changed in the env."""
    said = f"{app.org}|{app.env.value}".encode()
    run_after_commit(session, lambda: signal.publish(APPS_CHANGED, said))


async def _open(
    session: AsyncSession, app: App, kind: AppKind, *, created_by: str, key_fingerprint: str = "", sealed_key: str = ""
) -> bool:
    return await HostedAppRepository(session).open(
        app.org,
        app.env,
        app.name,
        kind=kind,
        key_fingerprint=key_fingerprint,
        sealed_key=sealed_key,
        created_by=created_by,
    )


def _standing_of(row: StandingRow, env: Env) -> Standing:
    host = None
    if row.release is not None and row.sha256 is not None:
        host = hostnames.host_of(row.org, env, row.name, row.release, row.sha256, row.secrets)
    failed = host is not None and row.failed_host == host
    return Standing(
        org=row.org,
        name=row.name,
        kind=row.kind,
        created_by=row.created_by,
        created_at=row.created_at,
        release=row.release,
        sha256=row.sha256,
        host=host,
        # An app with no process of its own serves its newest release: no runner reports it.
        live_release=row.live_release if row.kind.has_process else row.release,
        live_host=row.live_host,
        failed=failed,
        failed_why=row.failed_why if failed else None,
        stopped=row.stopped,
        logs_wanted=row.logs_wanted,
    )
