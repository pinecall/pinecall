"""A written call over a WebSocket: a message in, every entry of the call out, a close code for how it ended."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected, WebSocketState

from runtime.calls.log import Subscription
from runtime.enums import KeyScope
from runtime.exceptions import PinecallError
from runtime.kit.text import Json
from runtime.kit.websockets import close_reason, code_of, refuse_socket
from runtime.live import schemas
from runtime.live.auth import TheLive, TheSimulations, get_socket_actor
from runtime.live.parts import LiveParts
from runtime.live.service import written
from runtime.session import service as session

router = APIRouter()

OVER = "the call ended: {reason}"
# What uvicorn closes with on a stop; a caller never sends it, so the call is left for the next
# process to take up.
SERVICE_RESTART = 1012
# RFC 6455 §7.4.1: the code of a close that ends nothing wrong.
NORMAL_CLOSURE = 1000
# What a socket raises when its caller is gone, by whichever side found out: a send to a caller who
# disappeared raises the first (code 1006), a close under a socket already closed the second.
GONE = (WebSocketDisconnect, WebSocketDisconnected)


# The org's key, never a room token (`pinecall chat`, `test`, `simulate`). Both tasks are collected
# before the route returns: until 2026-11 one that died on a caller who had gone left a "Task
# exception was never retrieved" behind.
@router.websocket("/v1/chat")
async def chat(websocket: WebSocket, live: TheLive, simulations: TheSimulations) -> None:
    """One text call: {text} frames in, every entry of the call out."""
    try:
        actor = get_socket_actor(websocket, KeyScope.talk)
        query = schemas.ChatQuery.read(dict(websocket.query_params), "a chat's query")
        opened = await written.open_chat(live, simulations, actor, _ask_of(query))
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()
    running = opened.running
    heard = await written.follow_chat(live, running)
    # The call can end from the desk or by the model: the socket is closed under the caller.
    tasks = [asyncio.create_task(_close_when_over(websocket, running))]
    if heard is not None:
        tasks.append(asyncio.create_task(_send(websocket, heard)))
    try:
        if not opened.resumed:
            await running.start()
        await _take_turns(websocket, live, running)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if heard is not None:
            heard.close()


def _ask_of(query: schemas.ChatQuery) -> written.ChatAsk:
    return written.ChatAsk(
        agent=query.agent,
        app=query.app,
        call=query.call,
        persona=query.persona or None,
        played_by=query.read_played_by(),
        contact=query.contact,
        caller=query.caller,
        state=query.read_state(),
    )


async def _close_when_over(websocket: WebSocket, running: session.Session) -> None:
    await running.over.wait()
    reason, _ = running.ended or ("error", "platform")
    await _close(websocket, OVER.format(reason=reason))


# A call ends from two sides at once (the caller's hangup, and the desk's or the model's end that
# `_close_when_over` hears) and each would close the socket: the second close finds it closed.
async def _close(websocket: WebSocket, reason: str, code: int = NORMAL_CLOSURE) -> None:
    if websocket.application_state is not WebSocketState.CONNECTED:
        return
    with contextlib.suppress(*GONE):
        await websocket.close(code=code, reason=close_reason(reason))


# A failed send flips the application state; a receive after it raises RuntimeError, so the
# state is asked before each receive.
async def _take_turns(websocket: WebSocket, live: LiveParts, running: session.Session) -> None:
    try:
        while websocket.application_state is WebSocketState.CONNECTED:
            frame = await websocket.receive_json()
            if _hangs_up(frame):
                # Ended before the socket closes, so the caller hears the call is over before it
                # stops whatever served it.
                await session.end(running, "caller_hung_up", "caller")
                await _close(websocket, OVER.format(reason="caller_hung_up"))
                return
            text = _text_of(frame)
            if not text:
                continue
            refused = await written.hear(live, running, text)
            if refused is not None:
                await _close(websocket, str(refused), code_of(refused))
                return
            # The agent hung up on this turn: the caller hears the call is over, as when they hang up.
            if running.closed:
                await _close(websocket, OVER.format(reason=running.ended[0] if running.ended else "agent_hung_up"))
                return
    except WebSocketDisconnect as gone:
        if gone.code != SERVICE_RESTART and not running.closed:
            await session.end(running, "caller_hung_up", "caller")
        return
    # A send that found the caller gone closed the socket under the loop, with no close to hear.
    if not running.closed:
        await session.end(running, "caller_hung_up", "caller")


async def _send(websocket: WebSocket, heard: Subscription) -> None:
    # The socket closes under the sender when the call ends: what was left to send is not sent.
    with contextlib.suppress(*GONE):
        async for entry in heard:
            await websocket.send_json(entry.dump())


def _hangs_up(data: Json) -> bool:
    return isinstance(data, dict) and data.get("hangup") is True


def _text_of(data: Json) -> str:
    if not isinstance(data, dict):
        return ""
    said = data.get("text")
    return said if isinstance(said, str) else ""
