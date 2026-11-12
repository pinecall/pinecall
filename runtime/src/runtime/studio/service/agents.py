"""A Studio agent as its endpoints reach it: listed, read, made, saved over the release read, deployed, a tool tried."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Agent as DeclaredAgent
from runtime.agents.declaration import Declaration
from runtime.agents.settings import Lexicon, dump_settings
from runtime.billing import service as billing
from runtime.enums import AppKind, Env
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.hosting import service as hosting
from runtime.kit.crypto import Vault
from runtime.signal import Signal
from runtime.studio.repository import Kept, StudioAgentRepository
from runtime.studio.service import declaring, fetch, values
from runtime.studio.service import definition as definitions
from runtime.wire.studio import Definition

# What a new agent starts as when the console names nothing else.
FIRST = Definition(
    instructions=(
        "You answer the phone for the business. Be brief and friendly: everything you say is read aloud. "
        "Ask one question at a time."
    ),
    greeting=None,
)
NOT_STUDIO = "{name} is code, not a Studio agent: `pinecall deploy` uploads it, and its class is what to edit"
NO_AGENT = "there is no Studio agent called {name} in {env}"
HELD_BY_CODE = "{name} is held by an app of yours already: a slug is one agent, so give this one another name"
TAKEN = "{name} is the name of a hosted app already: give this agent another name"
ANOTHER_ORGS = "{name} is another organization's agent already: a name is one org's, so give this agent another"
NO_TOOL = "this agent has no tool called {name}"
DEPLOYS_FROM_THE_SANDBOX = "an agent is deployed from the sandbox: ask with the sandbox, and it lands in production"
NOT_IN_PRODUCTION = "a deploy writes production: it takes a person who may act there, signed in"
DEPLOYED = "deployed from the sandbox's release {release}"


class ReleaseMoved(Conflict):
    """Someone saved a newer release than the one this save was based on."""

    def __init__(self, newest: int) -> None:
        super().__init__(f"this agent is at release {newest} now, not the one you read: read it again, then save")


@dataclass(frozen=True, slots=True)
class StudioAgent:
    """One Studio agent in one env: its newest release, its definition, who saved it, and when."""

    name: str
    env: Env
    release: int
    definition: Definition
    author: str
    note: str
    saved_at: datetime
    stopped: bool


class Owners(Protocol):
    """Who each agent belongs to, as the calls' logs keep it."""

    async def owner(self, agent: str) -> str | None:
        """The org that claimed the agent's log, or None while nobody did."""
        ...


class Holders(Protocol):
    """The apps holding each agent now, as the live side keeps them."""

    def is_held(self, org: str, slug: str) -> bool:
        """Whether a process holds the agent in the org now, in either env."""
        ...


@dataclass(frozen=True, slots=True)
class _Carried:
    """The settings a deploy carries into one scope, planned: what is kept there with the release."""

    where: Scope
    plan: agents.SettingsPlan | None
    lexicon: Lexicon | None


async def list_agents(session: AsyncSession, org: str, env: Env) -> list[StudioAgent]:
    """The org's Studio agents in the env, by name, each its newest release."""
    kept = await StudioAgentRepository(session).list_newest(env, org=org)
    return [_read(agent, env) for agent in kept]


async def read_agent(session: AsyncSession, org: str, env: Env, name: str) -> StudioAgent:
    """The agent's newest release and its definition."""
    kept = await StudioAgentRepository(session).list_newest(env, org=org, name=name)
    if kept:
        return _read(kept[0], env)
    kind = await hosting.find_kind(session, hosting.App(org=org, env=env, name=name))
    if kind is not None and kind is not AppKind.studio:
        raise ValidationError(NOT_STUDIO.format(name=name))
    raise NotFound(NO_AGENT.format(name=name, env=env.value))


# A Studio agent is a hosted app: the org's quota of them counts it, the first release makes it. Made
# all the same under another org's name, or one an app of the org holds, the holder could never register
# it: it would be hosted and answer nothing.
async def create_agent(
    session: AsyncSession,
    signal: Signal,
    owners: Owners,
    holders: Holders,
    actor: Actor,
    name: str,
    definition: Definition | None,
    note: str,
) -> StudioAgent:
    """Make the agent and keep its first release; refused for a name an app of the org has, or another org's agent."""
    app = hosting.App(org=actor.org, env=actor.env, name=hosting.check_name(name))
    if await hosting.find_kind(session, app) is not None:
        raise Conflict(TAKEN.format(name=name))
    owner = await owners.owner(name)
    if owner is not None and owner != actor.org:
        raise Conflict(ANOTHER_ORGS.format(name=name))
    if holders.is_held(actor.org, name):
        raise Conflict(HELD_BY_CODE.format(name=name))
    first = definition or FIRST
    definitions.check(first, await _list_secret_names(session, app.org, app.env), app.env)
    by = actor.asked_by
    await _open(session, app, by=by)
    await _keep(session, signal, app, first, by=by, note=note)
    return await read_agent(session, app.org, app.env, name)


async def save_agent(
    session: AsyncSession,
    signal: Signal,
    actor: Actor,
    name: str,
    definition: Definition,
    *,
    based_on: int | None,
    note: str,
) -> StudioAgent:
    """Keep the definition as the agent's next release, over the release it was read at."""
    org, env = actor.org, actor.env
    standing = await read_agent(session, org, env, name)
    if based_on is not None and based_on != standing.release:
        raise ReleaseMoved(standing.release)
    definitions.check(definition, await _list_secret_names(session, org, env), env)
    if definition != standing.definition:
        app = hosting.App(org=org, env=env, name=name)
        await _keep(session, signal, app, definition, by=actor.asked_by, note=note)
    return await read_agent(session, org, env, name)


# Production's own secrets are what it is checked against: a key named in the sandbox may be missing
# there, and the deploy is refused before a call finds out. In three steps, and no connection held
# across the middle one: what is read and planned, the vendors the settings move to asked, and then the
# release and the settings kept in one transaction or not at all, so what a vendor refuses leaves
# nothing kept.
async def deploy_agent(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    signal: Signal,
    actor: Actor,
    name: str,
    *,
    release: int | None,
    note: str,
) -> StudioAgent:
    """The sandbox's release, its newest unless named, kept as production's next, the deployer's settings with it."""
    if actor.person is None or not actor.person.opens_production:
        raise Forbidden(NOT_IN_PRODUCTION)
    if actor.env is not Env.sandbox:
        raise ValidationError(DEPLOYS_FROM_THE_SANDBOX)
    production = hosting.App(org=actor.org, env=Env.production, name=name)
    async with sessions.begin() as session:
        chosen, deployed = await _choose(session, actor.org, name, release)
        definitions.check(chosen, await _list_secret_names(session, actor.org, Env.production), Env.production)
        kind = await hosting.find_kind(session, production)
        if kind is not None and kind is not AppKind.studio:
            raise Conflict(TAKEN.format(name=name))
        carried = await _plan_carry(session, vault, actor, name, chosen)
    for one in carried:
        await agents.try_settings(one.plan)
    by = actor.asked_by
    shown = DEPLOYED.format(release=deployed)
    written = agents.Written(author=actor.name, note=shown)
    async with sessions.begin() as session:
        if await hosting.find_kind(session, production) is None:
            await _open(session, production, by=by)
        for one in carried:
            await agents.keep_settings(session, one.where, name, one.plan, written)
            if one.lexicon is not None:
                await agents.put_lexicon(session, one.where, name, one.lexicon, written, team=True)
        await _keep(session, signal, production, chosen, by=by, note=note or shown)
        return await read_agent(session, actor.org, Env.production, name)


async def try_tool(
    session: AsyncSession,
    vault: Vault,
    fetcher: fetch.Fetcher,
    actor: Actor,
    definition: Definition,
    name: str,
    arguments: Mapping[str, Any],
) -> fetch.Answer:
    """Send one tool's request once, as a call would, and say what came back."""
    tool = next((item for item in definition.tools if item.name == name), None)
    if tool is None:
        raise NotFound(NO_TOOL.format(name=name))
    definitions.check(definition, await _list_secret_names(session, actor.org, actor.env), actor.env)
    secrets = await hosting.environment_of(session, vault, actor.org, actor.env)
    filled = {**values.sample_values(datetime.now(UTC).date().isoformat()), "secrets": secrets}
    request = fetch.fill_request(tool, arguments, filled)
    return await fetch.send(fetcher, request, name=tool.name, timeout_s=tool.timeout_s)


async def _choose(session: AsyncSession, org: str, name: str, release: int | None) -> tuple[Definition, int]:
    standing = await read_agent(session, org, Env.sandbox, name)
    if release is None or release == standing.release:
        return standing.definition, standing.release
    sandbox = hosting.App(org=org, env=Env.sandbox, name=name)
    return definitions.parse((await hosting.source_of(session, sandbox, release)).data), release


# The deployer's settings, their level over the team's, become production's and the team's. Only a
# setting they set moves: one they leave unset keeps the value it has there, and one the definition
# declares is its own, so it is not carried. An empty sandbox writes no version and clears nothing.
# The class the write is checked against is the definition deployed, not the one production still holds.
async def _plan_carry(
    session: AsyncSession, vault: Vault, actor: Actor, name: str, chosen: Definition
) -> list[_Carried]:
    theirs = await agents.current_settings(session, accounts.scope_of_request(actor), name)
    declaration = agents.apply_declaration(Declaration(slug=name), declaring.declare(chosen), first=True)
    carried = {
        field: value
        for field, value in dump_settings(theirs.settings).items()
        if agents.NAME_IN_DECLARATION.get(field, field) not in declaration.fixed
    }
    planned: list[_Carried] = []
    for where in (Scope(actor.org, Env.production), Scope(actor.org, Env.sandbox)):
        standing = await agents.current_settings(session, where, name)
        plan = None
        if carried:
            wanted = agents.parse_settings({**dump_settings(standing.settings), **carried})
            plan = await agents.plan_settings(
                session, vault, actor, where, name, wanted, agent=DeclaredAgent(name, declaration)
            )
        planned.append(_Carried(where, plan, _carry_lexicon(standing.lexicon, theirs.lexicon)))
    return planned


# A word is the lexicon's own setting: one the sandbox says or hears is carried, one only the target has stays.
def _carry_lexicon(there: Lexicon, theirs: Lexicon) -> Lexicon | None:
    wanted = Lexicon(said={**there.said, **theirs.said}, heard=tuple(dict.fromkeys((*there.heard, *theirs.heard))))
    return None if wanted == there else wanted


async def _list_secret_names(session: AsyncSession, org: str, env: Env) -> set[str]:
    return {row.name for row in await hosting.list_secrets(session, org, env)}


async def _open(session: AsyncSession, app: hosting.App, *, by: str) -> None:
    hosted = len(await hosting.list_standing(session, app.env, app.org))
    await billing.admit_hosted_app(session, app.org, app.env, hosting=hosted)
    await hosting.open_held_app(session, app, AppKind.studio, created_by=by)


# Said to every gateway once it is stored: each holds the agent again as this release says.
async def _keep(
    session: AsyncSession, signal: Signal, app: hosting.App, definition: Definition, *, by: str, note: str
) -> None:
    data = definitions.dump(definition)
    source = hosting.Source(data=data, sha256=hashlib.sha256(data).hexdigest())
    await hosting.keep_release(session, app, source, author=by, note=note.strip())
    hosting.tell_changed(session, signal, app)


def _read(kept: Kept, env: Env) -> StudioAgent:
    return StudioAgent(
        name=kept.name,
        env=env,
        release=kept.release,
        definition=definitions.parse(kept.definition),
        author=kept.author,
        note=kept.note,
        saved_at=kept.saved_at,
        stopped=kept.stopped,
    )
