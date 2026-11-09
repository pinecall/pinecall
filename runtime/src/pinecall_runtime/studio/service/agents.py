"""A Studio agent as its doors reach it: made, saved over the release read, tried, deployed, listed."""

import hashlib
from collections.abc import Mapping
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.agents.declaration import AgentConfig, Lexicon
from pinecall_runtime.agents.service import declared, settings
from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from pinecall_runtime.hosting import service as hosting
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers import service as providers
from pinecall_runtime.studio.schemas import Definition, StudioAgent, TryResponse
from pinecall_runtime.studio.service import definition as defined
from pinecall_runtime.studio.service import fetch

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
DEPLOYED = "deployed from the sandbox's release {release}"


class ReleaseMoved(Conflict):
    """Someone saved a newer release than the one this save was based on."""

    def __init__(self, newest: int) -> None:
        super().__init__(f"this agent is at release {newest} now, not the one you read: read it again, then save")


async def list_agents(session: AsyncSession, org: str, env: Env) -> list[StudioAgent]:
    """The org's Studio agents in the env, by name, each its newest release."""
    found: list[StudioAgent] = []
    for app in await hosting.list_apps(session, org, env):
        if app.kind == hosting.STUDIO and app.release is not None:
            found.append(await read_agent(session, org, env, app.name))
    return found


async def read_agent(session: AsyncSession, org: str, env: Env, name: str) -> StudioAgent:
    """The agent's newest release and its definition."""
    app = hosting.App(org=org, env=env, name=name)
    kind = await hosting.kind_of(session, app)
    if kind is None:
        raise NotFound(NO_AGENT.format(name=name, env=env.value))
    if kind != hosting.STUDIO:
        raise ValidationError(NOT_STUDIO.format(name=name))
    releases = await hosting.releases_of(session, app)
    if not releases:
        raise NotFound(NO_AGENT.format(name=name, env=env.value))
    newest = releases[0]
    source = await hosting.source_of(session, app, newest.release)
    stopped = next((item.stopped for item in await hosting.list_apps(session, org, env) if item.name == name), False)
    return StudioAgent(
        name=name,
        env=env,
        release=newest.release,
        definition=defined.parsed(source.data),
        author=newest.author,
        note=newest.note,
        saved_at=newest.created_at,
        stopped=stopped,
    )


async def secret_names(session: AsyncSession, org: str, env: Env) -> set[str]:
    """The names of the org's secrets in the env: what a definition may name in a header."""
    return {row.name for row in await hosting.list_secrets(session, org, env)}


# A Studio agent is a hosted app: the org's quota of them counts it, the first release makes it.
async def create_agent(
    session: AsyncSession,
    org: str,
    env: Env,
    name: str,
    definition: Definition,
    *,
    held: bool,
    another_orgs: bool,
    by: str,
    note: str,
) -> StudioAgent:
    """Make the agent and keep its first release; refused for a name an app of the org has, or another org's agent."""
    app = hosting.App(org=org, env=env, name=hosting.checked_name(name))
    if await hosting.kind_of(session, app) is not None:
        raise Conflict(TAKEN.format(name=name))
    # Made all the same, the holder could never register it: it would be hosted and answer nothing.
    if another_orgs:
        raise Conflict(ANOTHER_ORGS.format(name=name))
    if held:
        raise Conflict(HELD_BY_CODE.format(name=name))
    defined.check(definition, await secret_names(session, org, env), env)
    await _open(session, app, by=by)
    await _keep(session, app, definition, by=by, note=note)
    return await read_agent(session, org, env, name)


async def save_agent(
    session: AsyncSession,
    org: str,
    env: Env,
    name: str,
    definition: Definition,
    *,
    based_on: int | None,
    by: str,
    note: str,
) -> StudioAgent:
    """Keep the definition as the agent's next release, over the release it was read at."""
    standing = await read_agent(session, org, env, name)
    if based_on is not None and based_on != standing.release:
        raise ReleaseMoved(standing.release)
    defined.check(definition, await secret_names(session, org, env), env)
    if definition != standing.definition:
        await _keep(session, hosting.App(org=org, env=env, name=name), definition, by=by, note=note)
    return await read_agent(session, org, env, name)


# Production's own secrets are what it is checked against: a key named in the sandbox may be
# missing there, and the deploy is refused before a call finds out. Its settings go first, so what
# a vendor refuses leaves nothing kept: release and settings land in one transaction or not at all.
async def deploy_agent(
    session: AsyncSession, vault: Vault, actor: Actor, name: str, *, release: int | None, by: str, note: str
) -> StudioAgent:
    """The sandbox's release, its newest unless named, kept as production's next, the deployer's settings with it."""
    org, env = actor.org, actor.env
    if env is not Env.sandbox:
        raise ValidationError(DEPLOYS_FROM_THE_SANDBOX)
    sandbox = hosting.App(org=org, env=Env.sandbox, name=name)
    standing = await read_agent(session, org, Env.sandbox, name)
    chosen = standing.definition
    if release is not None and release != standing.release:
        chosen = defined.parsed((await hosting.source_of(session, sandbox, release)).data)
    defined.check(chosen, await secret_names(session, org, Env.production), Env.production)
    production = hosting.App(org=org, env=Env.production, name=name)
    kind = await hosting.kind_of(session, production)
    if kind is None:
        await _open(session, production, by=by)
    elif kind != hosting.STUDIO:
        raise Conflict(TAKEN.format(name=name))
    deployed = release or standing.release
    await _carry_settings(session, vault, actor, name, chosen, deployed)
    shown = note or DEPLOYED.format(release=deployed)
    await _keep(session, production, chosen, by=by, note=shown)
    return await read_agent(session, org, Env.production, name)


async def try_tool(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    org: str,
    env: Env,
    definition: Definition,
    name: str,
    arguments: Mapping[str, Any],
    resolver: fetch.Resolve,
) -> TryResponse:
    """Send one tool's request once, as a call would, and say what came back."""
    tool = next((item for item in definition.tools if item.name == name), None)
    if tool is None:
        raise NotFound(NO_TOOL.format(name=name))
    defined.check(definition, await secret_names(session, org, env), env)
    secrets = await hosting.environment_of(session, vault, org, env)
    values = {"call": {"from": "+15550100", "to": "+15550199", "channel": "web"}, "metadata": {}, "secrets": secrets}
    request = fetch.request_of(tool, arguments, values)
    answer = await fetch.send(http, request, name=tool.name, timeout_s=tool.timeout_s, resolver=resolver)
    return TryResponse(status=answer.status, body=answer.body, error=answer.error, duration_ms=answer.duration_ms)


# The deployer's settings, their level over the team's, become production's and the team's. Only a
# knob they set moves: one they leave unset keeps the value it has there, and one the definition
# declares is its own, so it is not carried. An empty sandbox writes no version and clears nothing.
async def _carry_settings(
    session: AsyncSession, vault: Vault, actor: Actor, name: str, chosen: Definition, release: int
) -> None:
    theirs = await settings.current_settings(session, keys.scope_of_request(actor), name)
    declaration = declared.with_app_fields(AgentConfig(slug=name), defined.declaration(chosen), first=True)
    carried = {
        knob: value
        for knob, value in settings.dump_tuning(theirs.tuning).items()
        if settings.DECLARED_AS.get(knob, knob) not in declaration.fixed
    }
    written = settings.Written(author=actor.name, note=DEPLOYED.format(release=release))
    for where in (Scope(actor.org, Env.production), Scope(actor.org, Env.sandbox)):
        standing = await settings.current_settings(session, where, name)
        if carried:
            wanted = settings.parse_tuning({**settings.dump_tuning(standing.tuning), **carried})
            keyring = await providers.keys_of(session, vault, where)
            await settings.write_tuning(
                session, where, name, wanted, written, actor=actor, declared=declaration, vault_keyring=keyring
            )
        await _carry_lexicon(session, where, name, standing.lexicon, theirs.lexicon, written)


# A word is the lexicon's knob: one the sandbox says or hears is carried, one only the target has stays.
async def _carry_lexicon(
    session: AsyncSession, where: Scope, name: str, there: Lexicon, theirs: Lexicon, written: settings.Written
) -> None:
    wanted = Lexicon(said={**there.said, **theirs.said}, heard=tuple(dict.fromkeys((*there.heard, *theirs.heard))))
    if wanted != there:
        await settings.put_lexicon(session, where, name, wanted, written)


async def _open(session: AsyncSession, app: hosting.App, *, by: str) -> None:
    hosted = len(await hosting.list_apps(session, app.org, app.env))
    await billing.admit_hosted_app(session, app.org, app.env, hosting=hosted)
    await hosting.open_studio(session, app, created_by=by)


async def _keep(session: AsyncSession, app: hosting.App, definition: Definition, *, by: str, note: str) -> None:
    data = defined.dumped(definition)
    source = hosting.Source(data=data, sha256=hashlib.sha256(data).hexdigest())
    await hosting.keep_release(session, app, source, author=by, note=note.strip())
