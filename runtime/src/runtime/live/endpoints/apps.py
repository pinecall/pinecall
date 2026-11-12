"""The apps: an app's own socket and its frames, the org's list of them, one stopped, an agent killed or moved."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from runtime.accounts.auth import TheNamedOrg
from runtime.agents.auth import KnownAgent
from runtime.enums import KeyScope
from runtime.exceptions import PinecallError
from runtime.handles import TheServers, TheVault
from runtime.kit.loops import survive
from runtime.kit.text import JsonObject
from runtime.kit.websockets import close_reason, refuse_socket
from runtime.live import schemas
from runtime.live.auth import AppKey, CallsKey, TheCodes, TheLive, TheWhatsappThreads, get_socket_actor
from runtime.live.service import apps
from runtime.live.service.socket import NOT_JSON, AppSocket
from runtime.postgres import Session, TheBoxSession

logger = logging.getLogger(__name__)

router = APIRouter()


# The protocol never sees a WebSocket: it is lent the two things the transport does for it, a frame
# down and the close. Its life (its inbox heard, its calls handed on when it goes) is the socket's own.
@router.websocket("/v1/apps")
async def serve_app(websocket: WebSocket, live: TheLive, threads: TheWhatsappThreads, codes: TheCodes) -> None:
    """An app holds its agents here, answers their tools, and sends their calls' commands."""
    try:
        actor = get_socket_actor(websocket, KeyScope.app)
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()

    async def send(frame: JsonObject) -> None:
        await websocket.send_json(frame)

    async def close(why: str) -> None:
        await websocket.close(reason=close_reason(why))

    address = None if websocket.client is None else websocket.client.host
    socket = AppSocket(live, threads, codes.claim_heard, actor, send, close, address)
    try:
        async with socket.open():
            while True:
                try:
                    raw = await websocket.receive_json()
                except ValueError:
                    await socket.refuse("", "bad_shape", NOT_JSON, None)
                    continue
                # A frame that could not be applied is said with the socket, and the next is read: the
                # socket that closed on it would park every call it holds.
                with survive("a frame of an app socket", socket.id, unless=(WebSocketDisconnect,)):
                    await socket.take(raw)
    except WebSocketDisconnect:
        logger.info("app %s went away", socket.id)


# ── the org's apps and agents, as a person or a server of the org reaches them ──


@router.get("/v1/apps")
async def list_apps(actor: CallsKey, live: TheLive, session: Session) -> schemas.AppList:
    """The app sockets of the org in the env this key may see, oldest first."""
    return schemas.AppList.of({"apps": await apps.list_apps(session, live.sockets, live.holders, actor)})


@router.post("/v1/apps/{app}/stop")
async def stop_app(app: str, actor: AppKey, live: TheLive) -> schemas.StopAppResponse:
    """Tell the app it was stopped, and close its socket, on whichever gateway holds it."""
    await apps.stop_app(live.sockets, actor, app)
    return schemas.StopAppResponse(app=app, stopped=True)


@router.get("/v1/agents")
async def list_agents(actor: CallsKey, live: TheLive, session: Session) -> schemas.AgentList:
    """The org's held agents in the env: one row per slug, one per scope for a team reader."""
    return schemas.AgentList.of({"agents": await apps.list_agents(session, live.holders, actor)})


@router.post("/v1/agents/{slug}/kill")
async def kill_agent(slug: KnownAgent, actor: AppKey, live: TheLive) -> schemas.KilledAgent:
    """Let go of the agent in every app that holds it in the env, whoever's; an admin's."""
    return schemas.KilledAgent.of(await apps.kill_agent_as_admin(live.sockets, live.holders, actor, slug))


@router.post("/v1/ops/orgs/{named}/agents/{slug}/kill")
async def kill_agent_of_org(slug: str, org: TheNamedOrg, live: TheLive) -> schemas.KilledAgent:
    """Let go of the agent in every app of the org that holds it, in either env."""
    return schemas.KilledAgent.of(await apps.kill_agent_of_org(live.sockets, live.holders, org.id, org.slug, slug))


@router.put("/v1/ops/orgs/{named}/agents")
async def move_agent(
    org: TheNamedOrg,
    body: schemas.MoveAgentRequest,
    live: TheLive,
    vault: TheVault,
    servers: TheServers,
    session: TheBoxSession,
) -> schemas.AgentMoved:
    """An agent's logs and numbers moved into this org; refused while somebody holds it."""
    moved = await apps.move_agent(session, live.holders, vault, servers, org.id, org.slug, body.agent)
    return schemas.AgentMoved.of(moved)
