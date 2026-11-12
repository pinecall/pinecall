"""Studio's endpoints: an org's agents built in the console, saved, tried, deployed and exported."""

from importlib import metadata

from fastapi import APIRouter, Response

from runtime.agents.auth import TheOwners
from runtime.handles import TheSessions, TheSignal, TheVault
from runtime.live.auth import AppKey
from runtime.postgres import Session
from runtime.studio import schemas
from runtime.studio.auth import TheHolder, TheHolders
from runtime.studio.service import agents, export

router = APIRouter()

ZIP = "application/zip"
# The framework an exported project asks for: the one released with this runtime.
FRAMEWORK = f"^{metadata.version('pinecall-runtime')}"


@router.get("/v1/studio/agents")
async def list_studio_agents(actor: AppKey, session: Session) -> schemas.StudioAgentList:
    """The org's Studio agents in this env, by name, each its newest release."""
    listed = await agents.list_agents(session, actor.org, actor.env)
    return schemas.StudioAgentList(agents=[schemas.StudioAgent.of(agent) for agent in listed])


@router.post("/v1/studio/agents")
async def create_studio_agent(
    body: schemas.NewAgentRequest,
    actor: AppKey,
    signal: TheSignal,
    owners: TheOwners,
    holders: TheHolders,
    session: Session,
) -> schemas.StudioAgent:
    """Make an agent in Studio: a hosted app the gateway holds, its first release the definition."""
    made = await agents.create_agent(session, signal, owners, holders, actor, body.name, body.definition, body.note)
    return schemas.StudioAgent.of(made)


@router.get("/v1/studio/agents/{name}")
async def read_studio_agent(name: str, actor: AppKey, session: Session) -> schemas.StudioAgent:
    """The agent's newest release and its definition."""
    return schemas.StudioAgent.of(await agents.read_agent(session, actor.org, actor.env, name))


@router.put("/v1/studio/agents/{name}")
async def save_studio_agent(
    name: str, body: schemas.SaveRequest, actor: AppKey, signal: TheSignal, session: Session
) -> schemas.StudioAgent:
    """The definition kept as the agent's next release, over the release it was read at."""
    saved = await agents.save_agent(
        session, signal, actor, name, body.definition, based_on=body.based_on, note=body.note
    )
    return schemas.StudioAgent.of(saved)


# No session of the request's: the vendors the settings move to are asked between two transactions.
@router.post("/v1/studio/agents/{name}/deploy")
async def deploy_studio_agent(
    name: str, body: schemas.DeployRequest, actor: AppKey, sessions: TheSessions, vault: TheVault, signal: TheSignal
) -> schemas.StudioAgent:
    """The sandbox's release kept as production's next: the agent answers there from the next call."""
    deployed = await agents.deploy_agent(sessions, vault, signal, actor, name, release=body.release, note=body.note)
    return schemas.StudioAgent.of(deployed)


@router.post("/v1/studio/agents/{name}/try")
async def try_studio_tool(
    name: str, body: schemas.TryRequest, actor: AppKey, holder: TheHolder, vault: TheVault, session: Session
) -> schemas.TryResponse:
    """One tool's request sent once, as a call would send it; what came back."""
    definition = body.definition or (await agents.read_agent(session, actor.org, actor.env, name)).definition
    answered = await agents.try_tool(session, vault, holder.fetcher, actor, definition, body.tool, body.arguments)
    return schemas.TryResponse.of(answered)


@router.get("/v1/studio/agents/{name}/code")
async def export_studio_agent(name: str, actor: AppKey, session: Session) -> Response:
    """The agent as a TypeScript project of the framework's, zipped: the class `pinecall deploy` runs."""
    standing = await agents.read_agent(session, actor.org, actor.env, name)
    zipped = export.zip_project(name, standing.release, standing.definition, FRAMEWORK)
    return Response(zipped, media_type=ZIP, headers={"content-disposition": f'attachment; filename="{name}.zip"'})
