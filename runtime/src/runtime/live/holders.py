"""Who holds each agent: the app sockets registered on every gateway, per scope, the line of each, the phones."""

import dataclasses
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents.declaration import Declaration
from runtime.calls import service as calls
from runtime.calls.log import Logs, Store
from runtime.enums import Env
from runtime.exceptions import Conflict, NotFound, ValidationError
from runtime.live.peers import HELD_CHANNEL
from runtime.live.sockets import SocketId
from runtime.shared_state import Assigned, SharedState, newest
from runtime.signal import Signal
from runtime.wire.base import Entry
from runtime.wire.commands import AgentRegister
from runtime.wire.events import AgentConfigured, AgentDetached, AgentDraining, AgentRegistered
from runtime.wire.signal import Assignment, HeldShare, Registered

# A slug is one org's: the scope names the org, the env and whose copy it is.
type Held = tuple[Scope, str]

SOCKET_PREFIX = "app_"


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


# What the agent's class declares is read from its row (`agents.agent_of`), never from here: a
# registration says who holds the agent and what that process takes.
@dataclass(frozen=True, slots=True)
class Registration:
    """One agent as one app socket holds it."""

    slug: str
    scope: Scope
    owner: SocketId
    sdk: str | None = None
    # False for a console: it takes only the calls that name it.
    takes_unclaimed: bool = True
    # True for the CLI's companion: the console's dev verbs go to it.
    answers_dev: bool = False
    # True for an SDK that sends call.done once a call's end hook ran: a seal waits for it.
    says_done: bool = False
    # When it was claimed, on any gateway, so the newest holder is known across all of them.
    claimed: float = 0.0
    # Set by agent.drain: its tools still answer, it takes no new call.
    draining: bool = False

    @property
    def held_as(self) -> Held:
        """The registry's key for this agent in its scope."""
        return (self.scope, self.slug)


def new_socket_id() -> SocketId:
    """A new id for an app socket."""
    return f"{SOCKET_PREFIX}{uuid4().hex[:12]}"


def orgs_own(scope: Scope) -> Scope:
    """The org's own scope in the env."""
    return replace(scope, holder=THE_ORGS_OWN)


# Durable facts are in the log; this is which sockets are open now, on every gateway of the box:
# each says its own share on the signal and reads the merged view. The line is where a ring lands.
class Holders:
    """The agents the app sockets hold, per scope, the line of each, and the developers' phones."""

    def __init__(self, signal: Signal, logs: Logs, store: Store) -> None:
        self._logs = logs
        self._store = store
        self._mine: dict[Held, list[Registration]] = {}
        # What each agent held here declares, as it is told to the others: said with every beat,
        # written once when its socket declares it.
        self._said: dict[tuple[Held, SocketId], dict[str, Any]] = {}
        self._mine_lines: dict[tuple[str, str], Assigned] = {}
        self._mine_phones: dict[tuple[str, str], Assigned] = {}
        self._holders: dict[Held, list[Registration]] = {}
        self._lines: dict[tuple[str, str], str] = {}
        self._phones: dict[tuple[str, str], str] = {}
        self._held_by: dict[SocketId, set[Held]] = {}
        self._shared = SharedState(
            signal,
            HELD_CHANNEL,
            load=HeldShare.model_validate,
            dump=_dump_share,
            empty=HeldShare(),
            on_change=self._merge,
        )
        self._last_claim = 0.0

    async def start(self) -> None:
        """Hear the other gateways' sockets, and say this one's."""
        await self._shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self._shared.close()

    # ── reading ──

    def find_holder(self, scope: Scope, slug: str) -> Registration | None:
        """The newest holder in this scope, else in the org's own."""
        return self._newest((scope, slug)) or self._newest((orgs_own(scope), slug))

    def get_holder(self, scope: Scope, slug: str) -> Registration:
        """Whoever holds the agent in the scope, else in the org's own; refused when no app does."""
        found = self.find_holder(scope, slug)
        if found is None:
            raise NoApp(slug)
        return found

    def find_serving(self, scope: Scope, slug: str, app: SocketId | None = None) -> Registration | None:
        """The socket a call opened in this scope goes to: the one named, else the newest taker."""
        if app is not None:
            found = self.find_on_socket(app, scope.env, slug)
            return found if found is not None and found.scope.org == scope.org else None
        return self._taker((scope, slug)) or self._taker((orgs_own(scope), slug))

    def find_dev_answerer(self, scope: Scope, slug: str) -> Registration | None:
        """The socket the console's dev verbs go to: the newest that answers them, scope first."""
        return self._answerer((scope, slug)) or self._answerer((orgs_own(scope), slug))

    def find_ring_taker(self, scope: Scope, slug: str, caller: str | None) -> Registration | None:
        """The socket a ring at the agent lands in: the caller's own scope first, then the line."""
        if caller is not None and (holder := self._phones.get((scope.env, caller))) is not None:
            theirs = self._taker((replace(scope, holder=holder), slug))
            if theirs is not None:
                return theirs
        holder = self._lines.get((scope.env, slug))
        return None if holder is None else self._taker((replace(scope, holder=holder), slug))

    def find_ring_holder(self, scope: Scope, slug: str, caller: str | None) -> str | None:
        """The holder whose copy a ring at the agent lands in ("" the org's own); None when no app takes it."""
        taking = self.find_ring_taker(scope, slug, caller)
        return None if taking is None else taking.scope.holder

    def find_on_socket(self, app: SocketId, env: Env, slug: str) -> Registration | None:
        """The agent as this socket holds it in this env."""
        for found in self._held_by.get(app, ()):
            if found[0].env == env and found[1] == slug:
                return next((item for item in self._holders.get(found, ()) if item.owner == app), None)
        return None

    def list_of_socket(self, app: SocketId) -> list[Registration]:
        """Every agent one socket holds, in claim order."""
        found = (item for name in self._held_by.get(app, ()) for item in self._holders.get(name, ()))
        return sorted((held for held in found if held.owner == app), key=lambda item: item.claimed)

    def list_holding(self, scope: Scope, *, every_scope: bool) -> list[Registration]:
        """The org's held agents in the env, as this reader sees them: one row per slug, or per scope."""
        seen: dict[str | Held, Registration] = {}
        for (owner, slug), held in self._holders.items():
            if owner.org != scope.org or owner.env != scope.env or not held:
                continue
            mine = owner.holder in (THE_ORGS_OWN, scope.holder)
            if not every_scope and not mine:
                continue
            under: str | Held = (owner, slug) if every_scope else slug
            if under not in seen or owner.holder == scope.holder:
                seen[under] = held[-1]
        return list(seen.values())

    def list_held(self, org: str, env: Env) -> frozenset[str]:
        """The agents a process holds in the org's env now, in any scope of it."""
        return frozenset(
            slug for (owner, slug), kept in self._holders.items() if owner.org == org and owner.env == env and kept
        )

    def list_taking_unclaimed(self, org: str, env: Env) -> frozenset[str]:
        """Of the agents held in the org's env, the ones a process takes a call nobody claimed for."""
        return frozenset(
            slug
            for (owner, slug), kept in self._holders.items()
            if owner.org == org and owner.env == env and any(held.takes_unclaimed for held in kept)
        )

    def slugs_of(self, org: str) -> frozenset[str]:
        """Every slug the org holds, in any env and scope: the agents quota counts these."""
        return frozenset(slug for (owner, slug), kept in self._holders.items() if owner.org == org and kept)

    def sockets_holding(self, org: str, env: Env, slug: str) -> frozenset[SocketId]:
        """Every socket that holds the agent in the org's env, in any scope, on any gateway."""
        return frozenset(
            item.owner
            for (owner, name), kept in self._holders.items()
            if owner.org == org and owner.env == env and name == slug
            for item in kept
        )

    def is_held_as(self, scope: Scope, slug: str, sdk: str) -> bool:
        """Whether a process of that kind holds the agent in the scope, or in the org's own."""
        return any(
            held.sdk == sdk for under in (scope, orgs_own(scope)) for held in self._holders.get((under, slug), ())
        )

    async def is_known(self, org: str, slug: str) -> bool:
        """Whether the agent is the org's: held now, or its own log claimed by the org when it first was."""
        if self.is_held(org, slug):
            return True
        return await self._store.owner(slug) == org

    def is_held(self, org: str, slug: str) -> bool:
        """Whether a process holds the agent in the org now, in either env."""
        return any(scope.org == org and name == slug and kept for (scope, name), kept in self._holders.items())

    # ── the line ──

    def line_of(self, env: Env, slug: str) -> str | None:
        """The scope holding the agent's line; None when nobody does."""
        return self._lines.get((env, slug))

    def take_line(self, scope: Scope, slug: str) -> None:
        """Give the agent's line to this scope, which must hold an app that answers a ring."""
        if self._taker((scope, slug)) is None:
            raise NotHolding(slug, scope.env)
        self._assign(self._mine_lines, scope.env, slug, scope.holder)

    def drop_line(self, scope: Scope, slug: str) -> bool:
        """Let the line go, to the newest other scope that could take it."""
        if self._lines.get((scope.env, slug)) != scope.holder:
            return False
        self._assign(self._mine_lines, scope.env, slug, None)
        self._hand_line_on(scope, slug, leaving=scope.holder)
        return True

    def list_waiting_for_line(self, scope: Scope, slug: str) -> list[Registration]:
        """Every scope of the org that could take the line, newest first."""
        taking = [
            item
            for (owner, name) in self._holders
            if name == slug and owner.org == scope.org and owner.env == scope.env
            if (item := self._taker((owner, name))) is not None
        ]
        return sorted(taking, key=lambda item: item.claimed, reverse=True)

    # ── the developers' phones ──

    # Each is a column of its member too (`members.test_phone`), which the lifespan says again at
    # start. Kept here as well until the release before 2026-11 is gone: its gateways read a ring's
    # holder out of this share (agents-6).
    def route_phone(self, env: Env, number: str, holder: str) -> None:
        """Send rings from this phone to this person's scope: their one phone, in place of the one before."""
        self.forget_phones(env, holder)
        self._assign(self._mine_phones, env, number, holder)

    def forget_phones(self, env: Env, holder: str) -> list[str]:
        """Forget every phone of this person, and say which."""
        for number in (gone := self.phones_of(env, holder)):
            self._assign(self._mine_phones, env, number, None)
        return gone

    def phones_of(self, env: Env, holder: str) -> list[str]:
        """The phones this person rings from."""
        return sorted(number for (env_, number), owner in self._phones.items() if env_ == env and owner == holder)

    # ── claiming ──

    # Whose the agent is was settled by whoever registers it, in its transaction (the log claimed, and
    # then asked whose it is): here the socket is put among the holders at once, with no wait before it,
    # so the stock its caller held to count the org's agents is counted with this one in.
    async def register(
        self, owner: SocketId, scope: Scope, slug: str, wanted: AgentRegister, declaration: Declaration
    ) -> Entry:
        """This socket holds the agent from now on; agent.registered, with the routes it answers, on its log."""
        self._put(
            Registration(
                slug=slug,
                scope=scope,
                owner=owner,
                # What the app said it is, as it said it: its SDK, and which calls and verbs it takes.
                sdk=wanted.sdk,
                takes_unclaimed=wanted.takes_unclaimed,
                answers_dev=wanted.answers_dev,
                says_done=wanted.says_done,
            ),
            declaration,
        )
        data = AgentRegistered(routes=list(wanted.routes), app=owner, sdk=wanted.sdk, env=scope.env)
        return await self._write(scope.env, slug, "agent.registered", data)

    async def configure(
        self, owner: SocketId, env: Env, slug: str, declaration: Declaration, changed: Sequence[str]
    ) -> Entry:
        """The declaration this socket sent; agent.configured names what changed."""
        found = self.find_on_socket(owner, env, slug)
        if found is None:
            raise NotRegistered(slug)
        self._put(found, declaration)
        return await self._write(env, slug, "agent.configured", AgentConfigured(changed=list(changed)))

    def drain(self, owner: SocketId, env: Env, slug: str) -> None:
        """Mark the socket as draining the agent: its tools still answer, it takes no new call."""
        found = self.find_on_socket(owner, env, slug)
        if found is None:
            raise NotRegistered(slug)
        self._put(replace(found, draining=True), None)

    async def write_draining(self, owner: SocketId, env: Env, slug: str, *, handed: int, parked: int) -> Entry:
        """agent.draining, once the socket's calls moved."""
        data = AgentDraining(app=owner, env=env, handed=handed, parked=parked)
        return await self._write(env, slug, "agent.draining", data)

    async def release(self, owner: SocketId) -> None:
        """A socket closed: its agents let go, the line handed on, agent.detached for each."""
        for found in [key for key, kept in self._mine.items() if any(item.owner == owner for item in kept)]:
            await self._let_go(owner, found)
        self._say()

    async def let_go_of(self, owner: SocketId, env: Env, slug: str) -> bool:
        """One agent let go by a socket that keeps the others; False when the socket did not hold it."""
        found = self.find_on_socket(owner, env, slug)
        if found is None or found.held_as not in self._mine:
            return False
        await self._let_go(owner, found.held_as)
        self._say()
        return True

    # ── private ──

    async def _let_go(self, owner: SocketId, found: Held) -> None:
        kept = [item for item in self._mine[found] if item.owner != owner]
        if kept:
            self._mine[found] = kept
        else:
            del self._mine[found]
        self._said.pop((found, owner), None)
        self._merge()
        left = self._holders.get(found, [])
        scope, slug = found
        if self._lines.get((scope.env, slug)) == scope.holder and not left:
            self._assign(self._mine_lines, scope.env, slug, None)
            self._hand_line_on(scope, slug)
        await self._write(scope.env, slug, "agent.detached", AgentDetached(app=owner, env=scope.env, left=not left))

    # `declaration` None keeps what the socket said of the agent before.
    def _put(self, registration: Registration, declaration: Declaration | None) -> None:
        self._last_claim = max(time.time(), self._last_claim + 1e-6)
        claim = replace(registration, claimed=self._last_claim)
        held = self._mine.setdefault(claim.held_as, [])
        at = next((n for n, item in enumerate(held) if item.owner == claim.owner), None)
        if at is None:
            held.append(claim)
        else:
            held[at] = claim
        if declaration is not None:
            self._said[(claim.held_as, claim.owner)] = calls.dump_declaration(declaration)
        self._merge()
        # The first scope able to take a ring gets the line; later ones claim it.
        if claim.takes_unclaimed and not claim.draining and (claim.scope.env, claim.slug) not in self._lines:
            self._assign(self._mine_lines, claim.scope.env, claim.slug, claim.scope.holder)
        self._say()

    def _assign(self, table: dict[tuple[str, str], Assigned], env: Env, key: str, holder: str | None) -> None:
        table[(env, key)] = Assigned(env, key, holder, time.time())
        self._merge()
        self._say()

    def _say(self) -> None:
        self._shared.put(
            HeldShare(
                registrations=tuple(
                    _tell(item, self._said.get((item.held_as, item.owner)))
                    for kept in self._mine.values()
                    for item in kept
                ),
                lines=tuple(Assignment.model_validate(one) for one in self._mine_lines.values()),
                phones=tuple(Assignment.model_validate(one) for one in self._mine_phones.values()),
            )
        )

    def _merge(self) -> None:
        theirs = [heard.share for heard in self._shared.theirs.values()]
        holders: dict[Held, list[Registration]] = {key: list(kept) for key, kept in self._mine.items()}
        for share in theirs:
            for told in share.registrations:
                item = _read(told)
                holders.setdefault(item.held_as, []).append(item)
        held_by: dict[SocketId, set[Held]] = {}
        for key, kept in holders.items():
            kept.sort(key=lambda item: item.claimed)
            for item in kept:
                held_by.setdefault(item.owner, set()).add(key)
        self._holders, self._held_by = holders, held_by
        self._lines = newest(self._mine_lines, (_read_assigned(one) for share in theirs for one in share.lines))
        self._phones = newest(self._mine_phones, (_read_assigned(one) for share in theirs for one in share.phones))

    def _newest(self, held: Held) -> Registration | None:
        holding = self._holders.get(held)
        return holding[-1] if holding else None

    def _taker(self, held: Held) -> Registration | None:
        return next(
            (item for item in reversed(self._holders.get(held, ())) if item.takes_unclaimed and not item.draining), None
        )

    def _answerer(self, held: Held) -> Registration | None:
        return next(
            (item for item in reversed(self._holders.get(held, ())) if item.answers_dev and not item.draining), None
        )

    def _hand_line_on(self, scope: Scope, slug: str, *, leaving: str | None = None) -> None:
        waiting = [item for item in self.list_waiting_for_line(scope, slug) if item.scope.holder != leaving]
        if waiting:
            self._assign(self._mine_lines, scope.env, slug, waiting[0].scope.holder)

    # A laptop restarts often: in the sandbox these entries are forgettable, or they flood the log.
    async def _write(
        self, env: Env, slug: str, kind: str, event: AgentRegistered | AgentConfigured | AgentDraining | AgentDetached
    ) -> Entry:
        forgettable = None if env is Env.production else True
        return await self._logs.agent(slug).append(kind, event.dump(), ephemeral=forgettable)


# A gateway of the release before 2026-11 requires the declaration of every registration it hears, and
# builds its calls on it: one that declared nothing yet is told as the bare agent.
def _tell(item: Registration, said: Mapping[str, Any] | None) -> Registered:
    config = dict(said) if said is not None else calls.dump_declaration(Declaration(slug=item.slug))
    return Registered.model_validate({**dataclasses.asdict(item), "config": config})


def _read(told: Registered) -> Registration:
    scope = Scope(told.scope.org, told.scope.env, told.scope.holder)
    return Registration(scope=scope, **told.model_dump(exclude={"scope", "config"}))


def _read_assigned(told: Assignment) -> Assigned:
    return Assigned(told.env, told.key, told.holder, told.at)


def _dump_share(share: HeldShare) -> object:
    return share.model_dump(mode="json")
