"""The app socket on the wire: a WebSocket accepted, its frames handed to the protocol, its inbox heard."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.socket import NOT_JSON, AppSocket
from pinecall_runtime.calls.service.threads import Threads
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.exceptions import PinecallError, Unauthorized
from pinecall_runtime.kit.auth import Actor, check_scopes
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.websockets import close_reason, refuse_socket

logger = logging.getLogger(__name__)

router = APIRouter()

TAKES_A_KEY = "this endpoint takes an API key"


@router.websocket("/v1/apps")
async def apps_socket(websocket: WebSocket) -> None:
    """An app holds its agents here, answers their tools, and sends their calls' commands."""
    actor: Actor | None = getattr(websocket.state, "actor", None)
    try:
        if actor is None:
            raise Unauthorized(TAKES_A_KEY)
        check_scopes(actor, (KeyScope.app,))
    except PinecallError as refused:
        await refuse_socket(websocket, str(refused))
        return
    await websocket.accept()
    serving: Serving = websocket.app.state.serving
    threads: Threads = websocket.app.state.threads

    async def send(frame: JsonObject) -> None:
        await websocket.send_json(frame)

    async def close(why: str) -> None:
        await websocket.close(reason=close_reason(why))

    client = websocket.client
    socket = AppSocket(serving, threads, actor, send, close, None if client is None else client.host)
    socket.connect()
    inbox = asyncio.create_task(socket.listen())
    try:
        while True:
            try:
                raw = await websocket.receive_json()
            except ValueError:
                await socket.refuse("", "bad_shape", NOT_JSON, None)
                continue
            await socket.take(raw)
    except WebSocketDisconnect:
        logger.info("app %s went away", socket.id)
    finally:
        inbox.cancel()
        await asyncio.gather(inbox, return_exceptions=True)
        await socket.gone()
