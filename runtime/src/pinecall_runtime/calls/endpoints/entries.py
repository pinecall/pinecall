"""A worker's batches of a call on one socket for its life, each answered with the seqs it got."""

import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import serving_of
from pinecall_runtime.calls.service.live import Served
from pinecall_runtime.calls.service.serving import Serving, check_kind, count_append, get_served
from pinecall_runtime.enums import KeyScope
from pinecall_runtime.exceptions import PinecallError, Unauthorized
from pinecall_runtime.kit.auth import Actor, check_scopes
from pinecall_runtime.kit.websockets import refuse_socket

logger = logging.getLogger(__name__)

router = APIRouter()


# A request per batch cost the gateway its routing, its headers and its key each time; on the
# socket a batch is one frame in and one out, and the log's answer to a retry is the same as the
# batch endpoint's. A refusal is a frame too, and the socket stays: a refused batch never ends a call.
@router.websocket("/v1/calls/{call}/entries")
async def entries_socket(websocket: WebSocket, call: str) -> None:
    """A worker's batches of a call, on one socket for its life, each answered with its seqs."""
    serving = serving_of(websocket)
    actor: Actor | None = getattr(websocket.state, "actor", None)
    try:
        if actor is None:
            raise Unauthorized("this endpoint takes an API key")
        check_scopes(actor, (KeyScope.app, KeyScope.fleet))
        async with serving.handles.sessions.begin() as session:
            served = await get_served(session, serving, actor, call)
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            await _answer(websocket, serving, served, call, raw)
    except WebSocketDisconnect:
        logger.debug("call %s: its worker's socket closed", call)


async def _answer(websocket: WebSocket, serving: Serving, served: Served, call: str, raw: str) -> None:
    try:
        body = schemas.AppendEntriesRequest.parse_json(raw, "entries")
        for item in body.entries:
            check_kind(item.type)
        serving.live.in_use(call, time.monotonic())
        began = time.perf_counter()
        entries = await served.log.append_many(body.entries, after=body.after)
        count_append(serving.counters, time.perf_counter() - began, entries)
    except PinecallError as refused:
        await websocket.send_json(schemas.AppendEntriesRefused(refused=str(refused), status=refused.status).dump())
        return
    await websocket.send_text(schemas.AppendEntriesResponse(entries=entries).dump_json())
