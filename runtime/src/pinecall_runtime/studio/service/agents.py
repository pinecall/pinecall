"""A Studio agent as its doors reach it: made, saved over the release read, tried, deployed, listed."""

import hashlib
from collections.abc import Mapping
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from pinecall_runtime.hosting import service as hosting
from pinecall_runtime.kit.crypto import Vault
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
NO_TOOL = "this agent has no tool called {name}"
DEPLOYS_FROM_THE_SANDBOX = "an agent is deployed from the sandbox: ask with the sandbox, and it lands in production"


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
    session: AsyncSession, org: str, env: Env, name: str, definition: Definition, *, held: bool, by: str, note: str
) -> StudioAgent:
    """Make the agent and keep its first release; refused for a name an app of the org has."""
    app = hosting.App(org=org, env=env, name=hosting.checked_name(name))
    if await hosting.kind_of(session, app) is not None:
        raise Conflict(TAKEN.format(name=name))
    if held:
        raise Conflict(HELD_BY_CODE.format(name=name))
    defined.check(definition, await secret_names(session, org, env))
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
    defined.check(definition, await secret_names(session, org, env))
    if definition != standing.definition:
        await _keep(session, hosting.App(org=org, env=env, name=name), definition, by=by, note=note)
    return await read_agent(session, org, env, name)


# Production's own secrets are what it is checked against: a key named in the sandbox may be
# missing there, and the deploy is refused before a call finds out.
async def deploy_agent(
    session: AsyncSession, org: str, env: Env, name: str, *, release: int | None, by: str, note: str
) -> StudioAgent:
    """The sandbox's release, its newest unless named, kept as production's next."""
    if env is not Env.sandbox:
        raise ValidationError(DEPLOYS_FROM_THE_SANDBOX)
    sandbox = hosting.App(org=org, env=Env.sandbox, name=name)
    standing = await read_agent(session, org, Env.sandbox, name)
    chosen = standing.definition
    if release is not None and release != standing.release:
        chosen = defined.parsed((await hosting.source_of(session, sandbox, release)).data)
    defined.check(chosen, await secret_names(session, org, Env.production))
    production = hosting.App(org=org, env=Env.production, name=name)
    kind = await hosting.kind_of(session, production)
    if kind is None:
        await _open(session, production, by=by)
    elif kind != hosting.STUDIO:
        raise Conflict(TAKEN.format(name=name))
    shown = note or f"deployed from the sandbox's release {release or standing.release}"
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
    defined.check(definition, await secret_names(session, org, env))
    secrets = await hosting.environment_of(session, vault, org, env)
    values = {"call": {"from": "+15550100", "to": "+15550199", "channel": "web"}, "metadata": {}, "secrets": secrets}
    request = fetch.request_of(tool, arguments, values)
    answer = await fetch.send(http, request, name=tool.name, timeout_s=tool.timeout_s, resolver=resolver)
    return TryResponse(status=answer.status, body=answer.body, error=answer.error, duration_ms=answer.duration_ms)


async def _open(session: AsyncSession, app: hosting.App, *, by: str) -> None:
    hosted = len(await hosting.list_apps(session, app.org, app.env))
    await billing.admit_hosted_app(session, app.org, app.env, hosting=hosted)
    await hosting.open_studio(session, app, created_by=by)


async def _keep(session: AsyncSession, app: hosting.App, definition: Definition, *, by: str, note: str) -> None:
    data = defined.dumped(definition)
    source = hosting.Source(data=data, sha256=hashlib.sha256(data).hexdigest())
    await hosting.keep_release(session, app, source, author=by, note=note.strip())
