"""What a reader reads of a call: its entries as a page or a stream, its state, the org's feed."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from pinecall_runtime.agents.auth import KnownAgent
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import prompts
from pinecall_runtime.agents.service.registry import NoApp
from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import (
    NOT_YOURS,
    CallReaderDep,
    Reader,
    ReaderDep,
    TheServing,
    check_readable,
    record_read,
)
from pinecall_runtime.calls.fanout import EVERYTHING, Filter
from pinecall_runtime.calls.readers import parse_filter, project_entry, project_state
from pinecall_runtime.calls.service import lists
from pinecall_runtime.enums import ReadKind
from pinecall_runtime.exceptions import Forbidden, NotFound
from pinecall_runtime.kit import sse
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import TERMINAL_EVENT, PromptChanged

router = APIRouter()

# Short: a reconnect resumes losslessly from Last-Event-ID.
RETRY_MS = 1000
NO_SUCH_CALL = "no call {call} in this key's org and env"
PROMPT_TAKES_A_KEY = "a call's prompt is read with a key: a token of the call reads its log, never its prompt"


@router.get("/v1/calls/{call}/events", response_model=None)
async def stream_events(
    call: str,
    reader: CallReaderDep,
    serving: TheServing,
    request: Request,
    session: Session,
    query: Annotated[schemas.LogQuery, Query()],
    last_event_id: Annotated[str | None, Header()] = None,
) -> Response | StreamingResponse | schemas.LogPage:
    """A call's entries above the cursor: a page, or a stream that ends with the call."""
    config = await check_readable(session, serving, reader, call)
    await record_read(session, reader, call, ReadKind.log)
    cursor = max(query.after, _seq_of(last_event_id))
    only = parse_filter(query.types, durable=query.durable)
    store = serving.logs.store
    over = await store.is_sealed(call)
    if over and cursor >= await store.latest_seq(call):
        return Response(status_code=204)
    if sse.wants_sse(request):
        entries = serving.logs.reading(call).stream(after=cursor, only=only)
        return sse.streamed(
            sse.paced(_projected(entries, reader, config, ends=True), closing=request.app.state.closing)
        )
    read = await store.since(call, after=cursor, limit=query.limit)
    return _page(read, only, reader, config, live=not over)


@router.get("/v1/agents/{slug}/calls", response_model=None)
async def stream_agent_events(
    slug: KnownAgent,
    reader: ReaderDep,
    serving: TheServing,
    request: Request,
    query: Annotated[schemas.LogQuery, Query()],
) -> StreamingResponse | schemas.LogPage:
    """An agent's own log: its registrations, its declarations, its errors. It never ends."""
    if reader.actor is None:
        raise Forbidden(NOT_YOURS)
    owner = await serving.logs.store.owner(slug)
    if owner is not None and owner != reader.actor.org:
        raise NoApp(slug)
    config = serving.registry.declared(slug)
    only = parse_filter(query.types, durable=query.durable)
    if sse.wants_sse(request):
        entries = serving.logs.agent(slug).stream(after=query.after, only=only)
        return sse.streamed(
            sse.paced(_projected(entries, reader, config, ends=False), closing=request.app.state.closing)
        )
    read = await serving.logs.store.since(f"@{slug}", after=query.after, limit=query.limit)
    return _page(read, only, reader, config, live=True)


@router.get("/v1/calls/{call}/state")
async def call_state(call: str, reader: CallReaderDep, serving: TheServing, session: Session) -> JsonObject:
    """The call's folded state as this reader may see it, and the seq a stream resumes from."""
    config = await check_readable(session, serving, reader, call)
    await record_read(session, reader, call, ReadKind.log)
    state = await serving.logs.reading(call).snapshot()
    if state.seq == 0:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    return {
        "state": project_state(state, reader.projection, config, reader.viewer),
        "last_seq": state.seq,
        "live": not await serving.logs.store.is_sealed(call),
    }


# A key's read alone, never a page's token: the prompt is the operator's and the app's words. It is a
# read of the call, and on the record as one.
@router.get("/v1/calls/{call}/prompt")
async def call_prompt(
    call: str, reader: ReaderDep, serving: TheServing, session: Session
) -> schemas.CallPromptResponse:
    """Every block of prompt the call was told, in order, each with its words when kept."""
    if reader.visit is not None:
        raise Forbidden(PROMPT_TAKES_A_KEY)
    await check_readable(session, serving, reader, call)
    kept = await lists.head_of_call(session, call)
    entries = await serving.logs.store.whole(call)
    if kept is None or kept.scope is None or not entries:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    await record_read(session, reader, call, ReadKind.log)
    changes = [
        (entry.seq, PromptChanged.model_validate(entry.data)) for entry in entries if entry.type == "prompt.changed"
    ]
    texts = await prompts.texts_of(session, kept.scope.org, {block.hash for _, block in changes})
    return schemas.CallPromptResponse(
        call=call,
        blocks=[
            schemas.PromptBlockRow(
                seq=seq, name=block.name, hash=block.hash, chars=block.chars, text=texts.get(block.hash)
            )
            for seq, block in changes
        ],
    )


# Live only, no cursor: every entry of the feed is also in a log, which is where to resume.
@router.get("/v1/events", response_model=None)
async def stream_org_events(
    reader: ReaderDep, serving: TheServing, request: Request, types: Annotated[str | None, Query()] = None
) -> StreamingResponse:
    """The org's calls and agents changing, as they change; `types=a.b,c.d` keeps those alone."""
    if reader.actor is None:
        raise Forbidden(NOT_YOURS)
    only = parse_filter(types, durable=False, strict=True)
    feed = await serving.logs.feed_reader(reader.actor.org, reader.actor.env)
    return sse.streamed(
        sse.paced(_projected(feed, reader, None, ends=False, only=only), closing=request.app.state.closing)
    )


def _page(
    read: list[Entry], only: Filter, reader: Reader, config: AgentConfig | None, *, live: bool
) -> schemas.LogPage:
    kept = (project_entry(item, reader.projection, config, reader.viewer) for item in read if only.passes(item))
    # `next` is the last seq read, not kept, so a page that kept nothing still moves the cursor.
    return schemas.LogPage(
        entries=[item for item in kept if item is not None], live=live, next=read[-1].seq if read else None
    )


async def _projected(
    entries: AsyncIterator[Entry], reader: Reader, config: AgentConfig | None, *, ends: bool, only: Filter = EVERYTHING
) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for entry in entries:
        if not only.passes(entry):
            continue
        data = project_entry(entry, reader.projection, config, reader.viewer)
        if data is not None:
            yield sse.frame(json.dumps(data, separators=(",", ":")), event=entry.type, id_=str(entry.seq))
        if ends and entry.type == TERMINAL_EVENT:
            return


def _seq_of(header: str | None) -> int:
    try:
        return max(int(header or 0), 0)
    except ValueError:
        return 0
