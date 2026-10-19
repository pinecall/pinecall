"""Studio's endpoints: an org's agents built in the console, saved, tried, deployed and exported."""

from fastapi import APIRouter, Request, Response

from pinecall_runtime import __version__
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Forbidden
from pinecall_runtime.hosting.auth import AppKey
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.postgres import Session
from pinecall_runtime.studio import schemas, service
from pinecall_runtime.studio.service.agents import FIRST

router = APIRouter()

ZIP = "application/zip"
NOT_IN_PRODUCTION = "a deploy writes production: it takes a person who may act there, signed in"


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


def _holder(request: Request) -> service.Holder:
    holder: service.Holder = request.app.state.studio
    return holder


@router.get("/v1/studio/agents")
async def list_studio_agents(actor: AppKey, session: Session) -> schemas.StudioAgentList:
    """The org's Studio agents in this env, by name, each its newest release."""
    return schemas.StudioAgentList(agents=await service.list_agents(session, actor.org, actor.env))


@router.post("/v1/studio/agents")
async def make_studio_agent(
    body: schemas.NewAgentRequest, actor: AppKey, serving: TheServing, handles: TheHandles, session: Session
) -> schemas.StudioAgent:
    """Make an agent in Studio: a hosted app the gateway holds, its first release the definition."""
    made = await service.create_agent(
        session,
        actor.org,
        actor.env,
        body.name,
        body.definition or FIRST,
        held=serving.registry.is_held(actor.org, body.name),
        by=_asked_by(actor),
        note=body.note,
    )
    await session.commit()
    service.changed(handles.signal, actor.org, actor.env)
    return made


@router.get("/v1/studio/agents/{name}")
async def read_studio_agent(name: str, actor: AppKey, session: Session) -> schemas.StudioAgent:
    """The agent's newest release and its definition."""
    return await service.read_agent(session, actor.org, actor.env, name)


@router.put("/v1/studio/agents/{name}")
async def save_studio_agent(
    name: str, body: schemas.SaveRequest, actor: AppKey, handles: TheHandles, session: Session
) -> schemas.StudioAgent:
    """The definition kept as the agent's next release, over the release it was read at."""
    saved = await service.save_agent(
        session,
        actor.org,
        actor.env,
        name,
        body.definition,
        based_on=body.based_on,
        by=_asked_by(actor),
        note=body.note,
    )
    await session.commit()
    service.changed(handles.signal, actor.org, actor.env)
    return saved


@router.post("/v1/studio/agents/{name}/deploy")
async def deploy_studio_agent(
    name: str, body: schemas.DeployRequest, actor: AppKey, handles: TheHandles, session: Session
) -> schemas.StudioAgent:
    """The sandbox's release kept as production's next: the agent answers there from the next call."""
    if actor.person is None or not actor.person.opens_production:
        raise Forbidden(NOT_IN_PRODUCTION)
    deployed = await service.deploy_agent(
        session, actor.org, actor.env, name, release=body.release, by=_asked_by(actor), note=body.note
    )
    await session.commit()
    service.changed(handles.signal, actor.org, Env.production)
    return deployed


@router.post("/v1/studio/agents/{name}/try")
async def try_studio_tool(
    name: str, body: schemas.TryRequest, request: Request, actor: AppKey, handles: TheHandles, session: Session
) -> schemas.TryResponse:
    """One tool's request sent once, as a call would send it; what came back."""
    definition = body.definition or (await service.read_agent(session, actor.org, actor.env, name)).definition
    holder = _holder(request)
    return await service.try_tool(
        session,
        handles.vault,
        holder.http,
        actor.org,
        actor.env,
        definition,
        body.tool,
        body.arguments,
        holder.resolver,
    )


@router.get("/v1/studio/agents/{name}/code")
async def studio_agent_code(name: str, actor: AppKey, session: Session) -> Response:
    """The agent as a TypeScript project of the framework's, zipped: the class `pinecall deploy` runs."""
    standing = await service.read_agent(session, actor.org, actor.env, name)
    zipped = service.project_of(name, standing.release, standing.definition, f"^{__version__}")
    disposition = f'attachment; filename="{name}.zip"'
    return Response(zipped, media_type=ZIP, headers={"content-disposition": disposition})
