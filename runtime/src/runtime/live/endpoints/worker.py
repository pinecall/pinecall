"""The worker's endpoints on its call: open it, write it, run its tools, hear its commands, seal it."""

import asyncio
import base64
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from runtime.calls.context import read_context
from runtime.compliance.service import recordings
from runtime.enums import KeyScope
from runtime.exceptions import Conflict, PinecallError
from runtime.handles import TheClosing, TheVault
from runtime.judging.service import judge_model
from runtime.kit import sse
from runtime.kit.websockets import refuse_socket
from runtime.live.auth import (
    AnyonesServedCall,
    TheAppends,
    TheCodes,
    TheLive,
    TheServedCall,
    WorkerKey,
    get_socket_actor,
)
from runtime.live.service import codes, ending, entries, lookups, openings, seal, tools
from runtime.postgres import Session
from runtime.wire.base import Command, Entry
from runtime.wire.commands import CallClaim
from runtime.wire.events import ToolCall
from runtime.wire.parts import ToolResult
from runtime.wire.worker import (
    AppendEntriesRefused,
    AppendEntriesRequest,
    AppendEntriesResponse,
    AppendEntryRequest,
    JudgingSettings,
    LookupRequest,
    LookupResponse,
    OpenCallRequest,
    OpenCallResponse,
    RecordingKeyResponse,
    RememberResponse,
    SealCallRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

UNOPENED_KEY = "the key of call {call}'s recording is sealed under a key the vault no longer lists"


@router.post("/v1/calls")
async def open_call(body: OpenCallRequest, actor: WorkerKey, live: TheLive, session: Session) -> OpenCallResponse:
    """Open a call's log, serve it to its agent's socket, say its minutes and its first words."""
    opened = await openings.open_call(session, live, actor, _arrival_of(body))
    return OpenCallResponse(
        seconds_left=None if opened.ceiling is None else opened.ceiling.seconds,
        minutes=None if opened.ceiling is None else opened.ceiling.minutes,
        disclosure=opened.disclosure,
        recording_notice=opened.recording_notice,
        history=opened.history,
    )


@router.post("/v1/calls/{call}/reopened", status_code=204)
async def reopen_call(call: str, body: OpenCallRequest, actor: WorkerKey, live: TheLive, session: Session) -> None:
    """Serve again a call the gateway forgot."""
    await openings.reopen_call(session, live, actor, call, _arrival_of(body))


# The entry comes back with its seq: only the gateway numbers a log.
@router.post("/v1/calls/{call}/events")
async def append_entry(body: AppendEntryRequest, served: TheServedCall, live: TheLive, appends: TheAppends) -> Entry:
    """Write one entry of a call this gateway serves."""
    return await entries.append_entry(served, appends, live.health, body.type, body.data, ephemeral=body.ephemeral)


# Taken whole or refused whole; the answer to a retry of the last batch is the seqs it was given.
@router.post("/v1/calls/{call}/entries")
async def append_entries(
    body: AppendEntriesRequest, served: TheServedCall, live: TheLive, appends: TheAppends
) -> AppendEntriesResponse:
    """Write a worker's batch of a call this gateway serves, once and in order."""
    written = await entries.append_entries(live.calls, served, appends, live.health, body.entries, after=body.after)
    return AppendEntriesResponse(entries=written)


# A request per batch cost the gateway its routing, its headers and its key each time; on the
# socket a batch is one frame in and one out, and the log's answer to a retry is the same as the
# batch endpoint's. A refusal is a frame too, and the socket stays: a refused batch never ends a call.
@router.websocket("/v1/calls/{call}/entries")
async def write_entries(websocket: WebSocket, call: str, live: TheLive, appends: TheAppends) -> None:
    """A worker's batches of a call, on one socket for its life, each answered with its seqs."""
    try:
        actor = get_socket_actor(websocket, KeyScope.app, KeyScope.fleet)
        served = await entries.get_written_call(live, actor, call)
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                batch = AppendEntriesRequest.parse_json(raw, "entries")
                written = await entries.append_entries(
                    live.calls, served, appends, live.health, batch.entries, after=batch.after
                )
            except PinecallError as refused:
                await websocket.send_json(AppendEntriesRefused(refused=str(refused), status=refused.status).dump())
                continue
            await websocket.send_text(AppendEntriesResponse(entries=written).dump_json())
    except WebSocketDisconnect:
        logger.debug("call %s: its worker's socket closed", call)


@router.post("/v1/calls/{call}/sealed", status_code=204)
async def seal_call(body: SealCallRequest, served: TheServedCall, live: TheLive) -> None:
    """Price the call, write its summary and score, and seal its log."""
    sealing = ending.Sealing(
        usage=tuple(body.usage), outcome=body.outcome, recording=body.recording, lent=tuple(body.lent)
    )
    await seal.seal_call(live, served, sealing)


# What the session of a worker's call heard of the app: its end hook ran, what it wrote was sent.
@router.post("/v1/calls/{call}/done", status_code=204)
async def release_seal(served: TheServedCall) -> None:
    """The app's end hook ran: the seal that waits for it goes on."""
    served.hooked.set()


@router.post("/v1/calls/{call}/tools")
async def run_tool(
    agent: Annotated[str, Query()], tool_call: ToolCall, served: TheServedCall, live: TheLive
) -> ToolResult:
    """Run a worker's tool call through the app that holds its agent, and answer its result."""
    return await tools.run_tool(live.calls, live.sockets, live.holders, served, agent, tool_call)


# The worker seals the call's recording with it before storing it; asked again, the same key.
@router.post("/v1/calls/{call}/recording/key")
async def mint_recording_key(served: TheServedCall, vault: TheVault, session: Session) -> RecordingKeyResponse:
    """The key the call's recording is sealed under, made once for the call."""
    found = await recordings.mint_recording_key(session, vault, served.scope.org, served.call)
    if found is None:
        raise Conflict(UNOPENED_KEY.format(call=served.call))
    return RecordingKeyResponse(key=base64.urlsafe_b64encode(found).decode())


# No id: commands have no seq, and a worker that loses the stream asks again.
@router.get("/v1/calls/{call}/commands")
async def stream_commands(served: TheServedCall, live: TheLive, closing: TheClosing) -> StreamingResponse:
    """The app's commands for the call, in order, until it is sealed."""
    await live.calls.wait_until_heard(served.call)
    return sse.stream(sse.pace(_frames(served.commands), closing=closing))


# What the worker reads is whether to judge and what a judge may spend; the model is the gateway's to
# pick when it judges, and this answer never named it.
@router.get("/v1/calls/{call}/judging")
async def call_judging(served: TheServedCall, session: Session) -> JudgingSettings:
    """Whether the call's org judges its calls at hang-up, and the ceiling a judge may spend."""
    judging = await judge_model.judging_of(session, served.scope.org)
    return JudgingSettings(on=judging.on, ceiling_usd=judging.ceiling_usd)


# The gateway writes memory.ops and docs.sources on the log itself: the worker has no database. No
# session is asked for: a lookup holds no connection while the embedder answers.
@router.post("/v1/calls/{call}/lookup")
async def look_up(body: LookupRequest, served: AnyonesServedCall, live: TheLive) -> LookupResponse:
    """Recall or search for a call served here, answered as the model reads it."""
    found = await lookups.look_up(live, served, body.tool, body.input, body.speech_id)
    return LookupResponse(output=found.output, took_ms=found.took_ms)


@router.post("/v1/calls/{call}/remember")
async def remember(served: TheServedCall, live: TheLive) -> RememberResponse:
    """Write what the call taught into its contact's memory now, as the seal would."""
    written = await ending.remember_now(live, served)
    return RememberResponse(ops=written.facts, took_ms=written.took_ms)


# A code nobody issued is a 404, and an ordinary one: the caller may be dialling an extension.
@router.post("/v1/calls/{call}/claim", status_code=204)
async def claim_keyed_code(call_claim: CallClaim, served: TheServedCall, the_codes: TheCodes, session: Session) -> None:
    """The caller keyed a page's code: tie the call to it."""
    await codes.claim_keyed_code(session, the_codes, served, call_claim.code)


def _arrival_of(body: OpenCallRequest) -> openings.Arrival:
    return openings.Arrival(
        agent=body.agent,
        context=read_context(body.context.model_dump(mode="json")),
        app=body.app,
        carrier_account=body.carrier_account,
        test_values=body.test_values,
    )


async def _frames(waiting: asyncio.Queue[Command | None]) -> AsyncIterator[str]:
    while (command := await waiting.get()) is not None:
        yield sse.frame(command.dump_json(), event=command.type)
