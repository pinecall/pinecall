"""The worker's endpoints on its call: open it, write it, run its tools, hear its commands, seal it."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from pinecall_runtime.agents import service as agents
from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import AnyonesServedCall, TheServedCall, TheServing, WorkerKey
from pinecall_runtime.calls.service import seal, worker
from pinecall_runtime.calls.service.serving import check_kind, claim_code, count_append, look_up
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit import sse
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.base import Command, Entry
from pinecall_runtime.wire.commands import CallClaim
from pinecall_runtime.wire.events import ToolCall
from pinecall_runtime.wire.parts import ToolResult

router = APIRouter()

NOBODY_ISSUED = "no code {code} waits for agent {agent}: nobody issued it, it expired, or a call took it"


@router.post("/v1/calls")
async def open_call(
    body: schemas.OpenCallRequest, actor: WorkerKey, serving: TheServing, session: Session
) -> schemas.OpenCallResponse:
    """Open a call's log, serve it to its agent's socket, say its minutes and its first words."""
    return await worker.open_call(session, serving, actor, body)


@router.post("/v1/calls/{call}/reopened", status_code=204)
async def reopen_call(
    call: str, body: schemas.OpenCallRequest, actor: WorkerKey, serving: TheServing, session: Session
) -> None:
    """Serve again a call the gateway forgot."""
    await worker.reopen_call(session, serving, actor, call, body)


# The entry comes back with its seq: only the gateway numbers a log.
@router.post("/v1/calls/{call}/events")
async def append_entry(body: schemas.AppendEntryRequest, served: TheServedCall, serving: TheServing) -> Entry:
    """Write one entry of a call this gateway serves."""
    check_kind(body.type)
    began = time.perf_counter()
    entry = await served.log.append(body.type, body.data, ephemeral=body.ephemeral)
    count_append(serving.counters, time.perf_counter() - began, [entry])
    return entry


# Taken whole or refused whole; the answer to a retry of the last batch is the seqs it was given.
@router.post("/v1/calls/{call}/entries")
async def append_entries(
    body: schemas.AppendEntriesRequest, served: TheServedCall, serving: TheServing
) -> schemas.AppendEntriesResponse:
    """Write a worker's batch of a call this gateway serves, once and in order."""
    for item in body.entries:
        check_kind(item.type)
    began = time.perf_counter()
    entries = await served.log.append_many(body.entries, after=body.after)
    count_append(serving.counters, time.perf_counter() - began, entries)
    return schemas.AppendEntriesResponse(entries=entries)


@router.post("/v1/calls/{call}/sealed", status_code=204)
async def seal_call(body: schemas.SealCallRequest, served: TheServedCall, serving: TheServing) -> None:
    """Price the call, write its summary and score, and seal its log."""
    await seal.seal(serving, served, body, lent=body.lent)


@router.post("/v1/calls/{call}/tools")
async def run_tool(
    agent: Annotated[str, Query()], tool_call: ToolCall, served: TheServedCall, serving: TheServing
) -> ToolResult:
    """Run a worker's tool call through the app that holds its agent, and answer its result."""
    return await worker.run_tool(serving, served, agent, tool_call)


@router.post("/v1/calls/{call}/recording/key")
async def recording_key(served: TheServedCall, serving: TheServing, session: Session) -> schemas.RecordingKeyResponse:
    """The key the call's recording is sealed under, made once for the call."""
    return await worker.recording_key_of(session, serving, served)


# No id: commands have no seq, and a worker that loses the stream asks again.
@router.get("/v1/calls/{call}/commands")
async def stream_commands(served: TheServedCall, serving: TheServing, request: Request) -> StreamingResponse:
    """The app's commands for the call, in order, until it is sealed."""
    await serving.live.commands_heard(served.call)
    return sse.streamed(sse.paced(_commanded(served.commands), closing=request.app.state.closing))


@router.get("/v1/calls/{call}/judging")
async def call_judging(served: TheServedCall, session: Session) -> agents.JudgingSettings:
    """Whether the call's org judges its calls at hang-up."""
    return await worker.judging_of(session, served)


# The gateway writes memory.ops and docs.sources on the log itself: the worker has no database.
@router.post("/v1/calls/{call}/lookup")
async def lookup(
    body: schemas.LookupRequest, served: AnyonesServedCall, serving: TheServing, session: Session
) -> schemas.LookupResponse:
    """Recall or search for a call served here, answered as the model reads it."""
    started = time.perf_counter()
    output = await look_up(session, serving, served, body)
    return schemas.LookupResponse(output=output, took_ms=(time.perf_counter() - started) * 1000)


@router.post("/v1/calls/{call}/remember")
async def remember(served: TheServedCall, serving: TheServing, session: Session) -> schemas.RememberResponse:
    """Write what the call taught into its contact's memory now, as the seal would."""
    started = time.perf_counter()
    written = await seal.remember(session, serving, served)
    ops = 0 if written is None else len(written.op.facts)
    return schemas.RememberResponse(ops=ops, took_ms=(time.perf_counter() - started) * 1000)


# A code nobody issued is a 404, and an ordinary one: the caller may be dialling an extension.
@router.post("/v1/calls/{call}/claim", status_code=204)
async def claim_keypad_code(
    call_claim: CallClaim, served: TheServedCall, serving: TheServing, session: Session
) -> None:
    """The caller keyed a page's code: tie the call to it."""
    if not await claim_code(session, serving.codes, served, call_claim.code, via="keypad"):
        raise NotFound(NOBODY_ISSUED.format(code=call_claim.code, agent=served.agent))


async def _commanded(waiting: asyncio.Queue[Command | None]) -> AsyncIterator[str]:
    while (command := await waiting.get()) is not None:
        yield sse.frame(command.dump_json(), event=command.type)
