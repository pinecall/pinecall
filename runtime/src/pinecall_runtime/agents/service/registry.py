"""Who holds each agent: the app sockets registered on every gateway, per scope, and the line."""

import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import members
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.schemas import ScopeHolder
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.kit.shared_state import Assigned, SharedState, newest
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.redis import Signal
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.commands import AgentRegister
from pinecall_runtime.wire.events import (
    AgentConfigured,
    AgentDetached,
    AgentDraining,
    AgentRegistered,
)

# Minted, never id(websocket): CPython reuses addresses, and the id travels back as `?app=`.
type SocketId = str
# A slug is one org's: the scope names the org, the env and whose copy it is.
type Held = tuple[Scope, str]
type Stop = Callable[[str], Awaitable[None]]

SOCKET_PREFIX = "app_"
HELD_CHANNEL = "held"


# What the registry needs of the call log, said here: `calls.Logs` is the one that has it, and
# `calls` reads the registry, so the registry names the shape rather than the module.
class AgentLog(Protocol):
    """One agent's log, as the registry writes it."""

    async def append(self, kind: str, data: JsonObject | None = None, *, ephemeral: bool | None = None) -> Entry:
        """One entry on the log, numbered."""
        ...


class AgentLogStore(Protocol):
    """The store an agent's log is claimed in."""

    async def owner(self, agent: str) -> str | None:
        """The org that claimed the agent's log, or None."""
        ...

    async def claim(self, call: str | None, agent: str, org: str) -> None:
        """Claim the log for the org; the first claim stands."""
        ...


class AgentLogs(Protocol):
    """The logs the registry writes an agent's registrations to."""

    @property
    def store(self) -> AgentLogStore:
        """Where the agent's log is claimed."""
        ...

    def agent(self, slug: str) -> AgentLog:
        """The agent's own log."""
        ...


class NotRegistered(ValidationError):
    """The agent is not registered on this socket."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"agent {slug} is not registered on this socket: register it first")


class AnotherOrgs(ValidationError):
    """A slug is one org's."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"agent {slug} belongs to another org: a slug is one org's. Rename the agent's folder, or hold "
            "it with a key of the org it belongs to"
        )


class NotHolding(ValidationError):
    """Nobody of this scope holds the agent with an app that answers an unclaimed call."""

    def __init__(self, slug: str, env: Env) -> None:
        super().__init__(f"agent {slug} is not held in {env} by an app of yours that answers an unclaimed call")


class NoApp(NotFound):
    """No socket holds the agent."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"no app holds agent {slug}: `pinecall start` holds it from a terminal, "
            "`pinecall deploy` runs it on Pinecall"
        )


class NotThatApp(Conflict):
    """The socket named does not hold the agent."""

    def __init__(self, app: SocketId, slug: str) -> None:
        super().__init__(f"app {app} does not hold agent {slug}")


class NobodyTakes(Conflict):
    """The agent is held, by sockets that take no unclaimed call: consoles, or draining apps."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"agent {slug} is held by consoles alone, or by apps that are draining: nothing takes an unclaimed call"
        )


class NoDevAnswerer(Conflict):
    """The agent is held, by no socket that answers the console's dev verbs."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"agent {slug} is held, but by no process that answers the console: run `pinecall start` beside it"
        )


@dataclass(frozen=True, slots=True)
class Registration:
    """One agent as one app socket holds it."""

    slug: str
    scope: Scope
    owner: SocketId
    config: AgentConfig
    sdk: str | None = None
    # False for a console: it takes only the calls that name it.
    takes_unclaimed: bool = True
    # True for the CLI's companion: the console's dev verbs go to it.
    answers_dev: bool = False
    # When it was claimed, on any gateway, so the newest holder is known across all of them.
    claimed: float = 0.0
    # Set by agent.drain: its tools still answer, it takes no new call.
    draining: bool = False

    @property
    def held_as(self) -> Held:
        """The registry's key for this agent in its scope."""
        return (self.scope, self.slug)


@dataclass(frozen=True, slots=True)
class Share:
    """What one gateway holds: its sockets' agents, and the lines and phones it set."""

    registrations: tuple[Registration, ...] = ()
    lines: tuple[Assigned, ...] = ()
    phones: tuple[Assigned, ...] = ()


@dataclass(frozen=True, slots=True)
class ConnectedApp:
    """One connected app socket, as the org's list of apps shows it."""

    app: SocketId
    scope: Scope
    address: str | None
    connected_at: float
    stop: Stop
    host: str | None = None


_SHARE: TypeAdapter[Share] = TypeAdapter(Share)


def new_socket_id() -> SocketId:
    """A new id for an app socket."""
    return f"{SOCKET_PREFIX}{uuid4().hex[:12]}"


def orgs_own(scope: Scope) -> Scope:
    """The org's own scope in the env."""
    return replace(scope, holder=THE_ORGS_OWN)


# The person's address names a developer's own scope in the console's lists of holders.
async def named_holder(session: AsyncSession, scope: Scope) -> ScopeHolder | None:
    """Who holds the scope, by member id and email; None for the org's own."""
    if not scope.holder:
        return None
    try:
        member = await members.get_member(session, scope.org, scope.holder)
    except NotFound:
        return ScopeHolder(holder=scope.holder, name=None)
    return ScopeHolder(holder=scope.holder, name=member.email)


# Durable facts are in the log; this is which sockets are open now, on every gateway of the box:
# each says its own share on the signal and reads the merged view. The line is where a ring lands.
class AgentRegistry:
    """The agents the app sockets hold, per scope, the line of each, and the developers' phones."""

    def __init__(self, signal: Signal, logs: AgentLogs) -> None:
        self.logs = logs
        self._mine: dict[Held, list[Registration]] = {}
        self._mine_lines: dict[tuple[str, str], Assigned] = {}
        self._mine_phones: dict[tuple[str, str], Assigned] = {}
        self.holders: dict[Held, list[Registration]] = {}
        self.lines: dict[tuple[str, str], str] = {}
        self.phones: dict[tuple[str, str], str] = {}
        self.owned: dict[SocketId, set[Held]] = {}
        self._shared = SharedState(signal, HELD_CHANNEL, _SHARE, Share(), self._merge)
        self._last_claim = 0.0

    async def start(self) -> None:
        """Hear the other gateways' sockets, and say this one's."""
        await self._shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self._shared.close()

    # ── reading ──

    def holder_of(self, scope: Scope, slug: str) -> Registration | None:
        """The newest holder in this scope, else in the org's own."""
        return self._newest((scope, slug)) or self._newest((orgs_own(scope), slug))

    def serving(self, scope: Scope, slug: str, app: SocketId | None) -> Registration | None:
        """The socket a call opened in this scope goes to: the one named, else the newest taker."""
        if app is not None:
            found = self.on_socket(app, scope.env, slug)
            return found if found is not None and found.scope.org == scope.org else None
        return self._taker((scope, slug)) or self._taker((orgs_own(scope), slug))

    def answering_dev(self, scope: Scope, slug: str) -> Registration | None:
        """The socket the console's dev verbs go to: the newest that answers them, scope first."""
        return self._answerer((scope, slug)) or self._answerer((orgs_own(scope), slug))

    def taking_a_ring(self, scope: Scope, slug: str, caller: str | None) -> Registration | None:
        """The socket a ring at the agent lands in: the caller's own scope first, then the line."""
        if caller is not None and (holder := self.phones.get((scope.env, caller))) is not None:
            theirs = self._taker((replace(scope, holder=holder), slug))
            if theirs is not None:
                return theirs
        holder = self.lines.get((scope.env, slug))
        return None if holder is None else self._taker((replace(scope, holder=holder), slug))

    def on_socket(self, app: SocketId, env: Env, slug: str) -> Registration | None:
        """The agent as this socket holds it in this env."""
        for found in self.owned.get(app, ()):
            if found[0].env == env and found[1] == slug:
                return next((item for item in self.holders.get(found, ()) if item.owner == app), None)
        return None

    def owned_by(self, app: SocketId) -> list[Registration]:
        """Every agent one socket holds, in claim order."""
        found = (item for name in self.owned.get(app, ()) for item in self.holders.get(name, ()))
        return sorted((h for h in found if h.owner == app), key=lambda item: item.claimed)

    def holding(self, scope: Scope, *, every_scope: bool) -> list[Registration]:
        """The org's held agents in the env, as this reader sees them: one row per slug, or per scope."""
        seen: dict[str | Held, Registration] = {}
        for (owner, slug), held in self.holders.items():
            if owner.org != scope.org or owner.env != scope.env or not held:
                continue
            mine = owner.holder in (THE_ORGS_OWN, scope.holder)
            if not every_scope and not mine:
                continue
            under: str | Held = (owner, slug) if every_scope else slug
            if under not in seen or owner.holder == scope.holder:
                seen[under] = held[-1]
        return list(seen.values())

    def slugs_of(self, org: str) -> frozenset[str]:
        """Every slug the org holds, in any env and scope: the agents quota counts these."""
        return frozenset(slug for (owner, slug), kept in self.holders.items() if owner.org == org and kept)

    async def is_known(self, org: str, slug: str) -> bool:
        """Whether the agent is the org's: held now, or its own log claimed by the org when it first was."""
        if self.is_held(org, slug):
            return True
        return await self.logs.store.owner(slug) == org

    def is_held(self, org: str, slug: str) -> bool:
        """Whether a process holds the agent in the org now, in either env."""
        return any(scope.org == org and name == slug and kept for (scope, name), kept in self.holders.items())

    def declared(self, slug: str) -> AgentConfig | None:
        """The agent's declared config, production's first."""
        found = sorted(
            (kept[-1] for (_, name), kept in self.holders.items() if name == slug and kept),
            key=lambda item: (item.scope.env is not Env.production, -item.claimed),
        )
        return found[0].config if found else None

    # ── the line ──

    def line_of(self, env: Env, slug: str) -> str | None:
        """The scope holding the agent's line; None when nobody does."""
        return self.lines.get((env, slug))

    def take_the_line(self, scope: Scope, slug: str) -> None:
        """Give the agent's line to this scope, which must hold an app that answers a ring."""
        if self._taker((scope, slug)) is None:
            raise NotHolding(slug, scope.env)
        self._assign(self._mine_lines, scope.env, slug, scope.holder)

    def drop_the_line(self, scope: Scope, slug: str) -> bool:
        """Let the line go, to the newest other scope that could take it."""
        if self.lines.get((scope.env, slug)) != scope.holder:
            return False
        self._assign(self._mine_lines, scope.env, slug, None)
        self._next_takes_the_line(scope, slug, leaving=scope.holder)
        return True

    def waiting_for_the_line(self, scope: Scope, slug: str) -> list[Registration]:
        """Every scope of the org that could take the line, newest first."""
        taking = [
            item
            for (owner, name) in self.holders
            if name == slug and owner.org == scope.org and owner.env == scope.env
            if (item := self._taker((owner, name))) is not None
        ]
        return sorted(taking, key=lambda item: item.claimed, reverse=True)

    # ── the developers' phones ──

    def calls_from(self, env: Env, number: str, holder: str) -> None:
        """Send rings from this phone to this person's scope; the last one said wins."""
        self._assign(self._mine_phones, env, number, holder)

    def forget_calls_from(self, env: Env, holder: str) -> list[str]:
        """Forget every phone of this person, and say which."""
        gone = sorted(n for (env_, n), owner in self.phones.items() if env_ == env and owner == holder)
        for number in gone:
            self._assign(self._mine_phones, env, number, None)
        return gone

    def phone_of(self, env: Env, number: str) -> str | None:
        """Whose own phone the number is in the env, or None."""
        return self.phones.get((env, number.strip()))

    def phones_of(self, env: Env, holder: str) -> list[str]:
        """The phones this person rings from."""
        return sorted(n for (env_, n), owner in self.phones.items() if env_ == env and owner == holder)

    # ── claiming ──

    async def register(self, owner: SocketId, scope: Scope, slug: str, wanted: AgentRegister) -> Entry:
        """This socket holds the agent from now on; agent.registered is written on its log."""
        owner_org = await self.logs.store.owner(slug)
        if owner_org is not None and owner_org != scope.org:
            raise AnotherOrgs(slug)
        await self.logs.store.claim(None, slug, scope.org)
        # A call that arrives before agent.configure still runs on what the agent declared.
        registration = self.on_socket(owner, scope.env, slug) or self.holder_of(scope, slug)
        config = registration.config if registration is not None else AgentConfig(slug=slug)
        self._replace(
            Registration(
                slug=slug,
                scope=scope,
                owner=owner,
                config=config,
                sdk=wanted.sdk,
                takes_unclaimed=wanted.takes_unclaimed,
                answers_dev=wanted.answers_dev,
            )
        )
        data = AgentRegistered(routes=[], app=owner, sdk=wanted.sdk, env=scope.env)
        return await self._write(scope.env, slug, "agent.registered", data)

    async def configure(
        self, owner: SocketId, env: Env, slug: str, config: AgentConfig, changed: Sequence[str]
    ) -> Entry:
        """The declaration this socket sent; agent.configured names what changed."""
        found = self.on_socket(owner, env, slug)
        if found is None:
            raise NotRegistered(slug)
        self._replace(replace(found, config=config))
        return await self._write(env, slug, "agent.configured", AgentConfigured(changed=list(changed)))

    def drain(self, owner: SocketId, env: Env, slug: str) -> None:
        """Mark the socket as draining the agent: its tools still answer, it takes no new call."""
        found = self.on_socket(owner, env, slug)
        if found is None:
            raise NotRegistered(slug)
        self._replace(replace(found, draining=True))

    async def drained(self, owner: SocketId, env: Env, slug: str, *, handed: int, parked: int) -> Entry:
        """agent.draining, once the socket's calls moved."""
        data = AgentDraining(app=owner, env=env, handed=handed, parked=parked)
        return await self._write(env, slug, "agent.draining", data)

    async def release(self, owner: SocketId) -> None:
        """A socket closed: its agents let go, the line handed on, agent.detached for each."""
        theirs = [key for key, kept in self._mine.items() if any(i.owner == owner for i in kept)]
        for found in theirs:
            kept = [item for item in self._mine[found] if item.owner != owner]
            if kept:
                self._mine[found] = kept
            else:
                del self._mine[found]
            self._merge()
            left = self.holders.get(found, [])
            scope, slug = found
            if self.lines.get((scope.env, slug)) == scope.holder and not left:
                self._assign(self._mine_lines, scope.env, slug, None)
                self._next_takes_the_line(scope, slug)
            await self._write(scope.env, slug, "agent.detached", AgentDetached(app=owner, env=scope.env, left=not left))
        self._say()

    # ── private ──

    def _replace(self, registration: Registration) -> None:
        self._last_claim = max(time.time(), self._last_claim + 1e-6)
        claim = replace(registration, claimed=self._last_claim)
        held = self._mine.setdefault(claim.held_as, [])
        at = next((n for n, item in enumerate(held) if item.owner == claim.owner), None)
        if at is None:
            held.append(claim)
        else:
            held[at] = claim
        self._merge()
        # The first scope able to take a ring gets the line; later ones claim it.
        if claim.takes_unclaimed and not claim.draining and (claim.scope.env, claim.slug) not in self.lines:
            self._assign(self._mine_lines, claim.scope.env, claim.slug, claim.scope.holder)
        self._say()

    def _assign(self, table: dict[tuple[str, str], Assigned], env: Env, key: str, holder: str | None) -> None:
        table[(env, key)] = Assigned(env, key, holder, time.time())
        self._merge()
        self._say()

    def _say(self) -> None:
        self._shared.put(
            Share(
                registrations=tuple(item for kept in self._mine.values() for item in kept),
                lines=tuple(self._mine_lines.values()),
                phones=tuple(self._mine_phones.values()),
            )
        )

    def _merge(self) -> None:
        theirs = [heard.share for heard in self._shared.theirs.values()]
        holders: dict[Held, list[Registration]] = {k: list(v) for k, v in self._mine.items()}
        for share in theirs:
            for item in share.registrations:
                holders.setdefault(item.held_as, []).append(item)
        owned: dict[SocketId, set[Held]] = {}
        for key, kept in holders.items():
            kept.sort(key=lambda item: item.claimed)
            for item in kept:
                owned.setdefault(item.owner, set()).add(key)
        self.holders, self.owned = holders, owned
        self.lines = newest(self._mine_lines, (s for share in theirs for s in share.lines))
        self.phones = newest(self._mine_phones, (s for share in theirs for s in share.phones))

    def _newest(self, held: Held) -> Registration | None:
        holding = self.holders.get(held)
        return holding[-1] if holding else None

    def _taker(self, held: Held) -> Registration | None:
        return next((i for i in reversed(self.holders.get(held, ())) if i.takes_unclaimed and not i.draining), None)

    def _answerer(self, held: Held) -> Registration | None:
        return next((i for i in reversed(self.holders.get(held, ())) if i.answers_dev and not i.draining), None)

    def _next_takes_the_line(self, scope: Scope, slug: str, *, leaving: str | None = None) -> None:
        waiting = [i for i in self.waiting_for_the_line(scope, slug) if i.scope.holder != leaving]
        if waiting:
            self._assign(self._mine_lines, scope.env, slug, waiting[0].scope.holder)

    # A laptop restarts often: in the sandbox these entries are forgettable, or they flood the log.
    async def _write(
        self, env: Env, slug: str, kind: str, event: AgentRegistered | AgentConfigured | AgentDraining | AgentDetached
    ) -> Entry:
        forgettable = None if env is Env.production else True
        return await self.logs.agent(slug).append(kind, event.dump(), ephemeral=forgettable)
