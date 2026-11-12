"""The apps an org has connected and the agents they hold: listed, stopped, killed; and one opened in this process."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.calls import service as calls
from runtime.enums import Channel, Env, KeyScope
from runtime.exceptions import Conflict, Forbidden, NotFound
from runtime.kit.crypto import Vault
from runtime.live.holders import Holders
from runtime.live.parts import LiveParts
from runtime.live.service import socket
from runtime.live.service.socket import AppSocket, ClaimCode, Close, SendFrame
from runtime.live.service.whatsapp import Threads
from runtime.live.sockets import SocketId, Sockets
from runtime.livekit import Servers
from runtime.scoping import box_wide
from runtime.telephony import service as telephony

KILLED_BY = "{slug} was killed by {name}"
OPERATOR_KILLED = "{slug} was killed by this box's operator"
STOPPED_BY = "stopped by {name}"
ON_THE_WEB: frozenset[Channel] = frozenset({Channel.web})


@dataclass(frozen=True, slots=True)
class Holder:
    """A scope by its member id and email; both None for the org's own."""

    holder: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class App:
    """One connected app socket and what it holds."""

    app: SocketId
    agents: list[str]
    env: Env
    host: str | None
    address: str | None
    sdk: str | None
    holder: Holder | None
    connected_at: float


@dataclass(frozen=True, slots=True)
class HeldAgent:
    """An agent some socket of the org holds, the channels it answers, whose scope, and what it is."""

    slug: str
    channels: list[Channel]
    holder: Holder | None
    kind: str


@dataclass(frozen=True, slots=True)
class Killed:
    """An agent killed: the envs it was held in, and the app sockets that let go of it."""

    agent: str
    envs: list[Env]
    apps: list[SocketId]


@dataclass(frozen=True, slots=True)
class Moved:
    """An agent moved into an org: how many logs came, which numbers came, which stayed where they were."""

    agent: str
    org: str
    logs: int
    numbers: list[str]
    stayed: list[str]


def sees_every_holder(actor: Actor) -> bool:
    """Whether the key reads every holder's agents in its org and env: a team key that holds agents."""
    return {KeyScope.team, KeyScope.app} <= actor.scopes


# The person's address names a developer's own scope in the console's lists of holders.
async def holder_of(session: AsyncSession, scope: Scope) -> Holder | None:
    """Who holds the scope, by member id and email; None for the org's own."""
    if not scope.holder:
        return None
    try:
        member = await accounts.get_member(session, scope.org, scope.holder)
    except NotFound:
        return Holder(holder=scope.holder, name=None)
    return Holder(holder=scope.holder, name=member.person.email)


async def list_apps(session: AsyncSession, sockets: Sockets, holders: Holders, actor: Actor) -> list[App]:
    """The app sockets of the org in the env this key may see, oldest first."""
    every = sees_every_holder(actor)
    listed: list[App] = []
    for row in sockets.apps_of(actor.org, actor.env):
        if not every and row.scope.holder not in ("", actor.holder):
            continue
        held = holders.list_of_socket(row.app)
        listed.append(
            App(
                app=row.app,
                agents=[item.slug for item in held],
                env=row.scope.env,
                host=row.host,
                address=row.address,
                sdk=next((item.sdk for item in held if item.sdk is not None), None),
                holder=await holder_of(session, Scope(row.scope.org, row.scope.env, row.scope.holder)),
                connected_at=row.connected_at,
            )
        )
    return listed


# One 404 for every reason (another org, env or scope, gone): nothing leaks.
async def stop_app(sockets: Sockets, actor: Actor, app: SocketId) -> None:
    """Tell the app it was stopped, and close its socket, on whichever gateway holds it."""
    found = next((row for row in sockets.apps_of(actor.org, actor.env) if row.app == app), None)
    if found is None or (not sees_every_holder(actor) and found.scope.holder not in ("", actor.holder)):
        raise NotFound(f"no app {app} is connected to this box that this key may stop")
    await sockets.stop(app, STOPPED_BY.format(name=actor.name))


# Nothing is erased: its settings, calls and logs stay, and an app that declares it again holds it
# again. The apps keep their other agents.
async def kill_agent_as_admin(sockets: Sockets, holders: Holders, actor: Actor, slug: str) -> Killed:
    """Let go of the agent in every app that holds it in the env, whoever's; an admin's."""
    if not sees_every_holder(actor):
        # Every holder's process is cut, so it is an admin's: a key that opens both team and app.
        raise Forbidden(
            "killing an agent is an admin's: it cuts every holder's app, and this key does not open team and app"
        )
    why = KILLED_BY.format(slug=slug, name=actor.name)
    killed = await socket.kill_agent(sockets, holders, actor.org, actor.env, slug, why)
    if not killed:
        raise NotFound(f"no app holds {slug} in {actor.env}: there is nothing to kill")
    return Killed(agent=slug, envs=[actor.env], apps=killed)


# The operator's kill reaches both envs of the org: what an admin of it would do in each.
async def kill_agent_of_org(sockets: Sockets, holders: Holders, org: str, named: str, slug: str) -> Killed:
    """Let go of the agent in every app of the org that holds it, in either env."""
    why = OPERATOR_KILLED.format(slug=slug)
    envs: list[Env] = []
    apps: list[SocketId] = []
    for env in Env:
        killed = await socket.kill_agent(sockets, holders, org, env, slug, why)
        envs += [env] if killed else []
        apps += killed
    if not apps:
        raise NotFound(f"no app of {named} holds {slug}: there is nothing to kill")
    return Killed(agent=slug, envs=envs, apps=apps)


# The way back from an agent registered with the wrong org's key: its logs and its numbers move.
# The operator's, since an org able to pull a slug could take another org's agent.
async def move_agent(
    session: AsyncSession, holders: Holders, vault: Vault, servers: Servers, org: str, named: str, slug: str
) -> Moved:
    """An agent's logs and numbers moved into the org; refused while somebody holds it."""
    if holders.is_held_by_anyone(slug):
        raise Conflict(f"agent {slug} is held right now: stop it, move it, and start it again")
    with box_wide():
        logs = await calls.move_logs(session, slug, org)
    if logs == 0:
        raise NotFound(f"no agent named {slug} has ever written a log here")
    numbers, stayed = await telephony.move_routes_with_agent(session, vault, servers, slug, org)
    return Moved(agent=slug, org=named, logs=logs, numbers=numbers, stayed=stayed)


async def list_agents(session: AsyncSession, holders: Holders, actor: Actor) -> list[HeldAgent]:
    """The org's held agents in the env: one row per slug, one per scope for a team reader."""
    answering: dict[str, set[Channel]] = {}
    for route in await telephony.list_routes(session, actor.org, actor.env):
        answering.setdefault(route.agent, set()).add(route.channel)
    return [
        HeldAgent(
            slug=held.slug,
            channels=sorted(answering.get(held.slug, set()) | ON_THE_WEB),
            holder=await holder_of(session, held.scope),
            kind=agents.kind_of(held.sdk),
        )
        for held in holders.list_holding(actor.scope, every_scope=sees_every_holder(actor))
    ]


# ── for a domain above the live side ──


# What a domain above this one opens an app socket of its own with (`studio`, whose agents the gateway
# holds itself): its frames never leave the process, and nothing else tells the socket from an SDK's.
# `LiveParts` stays inside it.
class AppSockets:
    """An app socket opened inside this process, by a domain that holds agents itself."""

    def __init__(self, live: LiveParts, threads: Threads, claim_code: ClaimCode) -> None:
        self._live = live
        self._threads = threads
        self._claim_code = claim_code

    def make(self, actor: Actor, send: SendFrame, close: Close, host: str) -> AppSocket:
        """A socket for the actor: what the gateway sends it goes to `send`; `host` is where it says it runs."""
        return AppSocket(self._live, self._threads, self._claim_code, actor, send, close, host)
