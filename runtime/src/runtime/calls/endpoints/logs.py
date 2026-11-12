"""A log over HTTP: a call's entries as a page or a stream, its state, its prompt; an agent's own log; the feeds."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from runtime.agents.auth import TheAgent
from runtime.auth import TheOperator
from runtime.calls import schemas
from runtime.calls.auth import ReadingKey, TheFeeds, TheLogs, ThePromptedCall, TheReadableCall
from runtime.calls.service import reading
from runtime.handles import TheClosing, TheSessions
from runtime.kit import sse
from runtime.postgres import Session

router = APIRouter()

# Short: a reconnect resumes losslessly from Last-Event-ID.
RETRY_MS = 1000


@router.get("/v1/calls/{call}/events", response_model=None)
async def stream_events(
    readable: TheReadableCall,
    logs: TheLogs,
    sessions: TheSessions,
    session: Session,
    request: Request,
    closing: TheClosing,
    query: Annotated[schemas.LogQuery, Query()],
    last_event_id: Annotated[str | None, Header()] = None,
) -> Response | schemas.LogPage:
    """A call's entries above the cursor: a page, or a stream that ends with the call."""
    asked = reading.Asked(max(query.after, _seq_of(last_event_id)), query.types, query.durable, query.limit)
    found = await reading.read_call(session, logs, sessions, readable, asked, follow=sse.wants_sse(request))
    return _answer(found, closing)


# The key is asked for first: a call's token is told it reads its own call alone, before anything
# is asked of the agent.
@router.get("/v1/agents/{slug}/calls", response_model=None)
async def stream_agent_events(
    _actor: ReadingKey,
    agent: TheAgent,
    logs: TheLogs,
    session: Session,
    request: Request,
    closing: TheClosing,
    query: Annotated[schemas.LogQuery, Query()],
    last_event_id: Annotated[str | None, Header()] = None,
) -> Response | schemas.LogPage:
    """An agent's own log: its registrations, what it declared, its errors. It never ends."""
    asked = reading.Asked(max(query.after, _seq_of(last_event_id)), query.types, query.durable, query.limit)
    found = await reading.read_agent_log(
        session, logs, agent.slug, agent.declaration, asked, follow=sse.wants_sse(request)
    )
    return _answer(found, closing)


@router.get("/v1/calls/{call}/state")
async def call_state(readable: TheReadableCall, logs: TheLogs, session: Session) -> schemas.CallState:
    """The call's folded state as this reader may see it, and the seq a stream resumes from."""
    return schemas.CallState.of(await reading.state_of(session, logs, readable))


# A key's read alone, never a page's token: the prompt is the operator's and the app's words. It is a
# read of the call, and on the record as one.
@router.get("/v1/calls/{call}/prompt")
async def call_prompt(readable: ThePromptedCall, session: Session) -> schemas.CallPromptResponse:
    """Every block of prompt the call was told, in order, each with its words when kept."""
    return schemas.CallPromptResponse.of(await reading.prompt_of(session, readable))


# Live only, no cursor: every entry of the feed is also in a log, which is where to resume.
@router.get("/v1/events", response_model=None)
async def stream_org_events(
    actor: ReadingKey, feeds: TheFeeds, closing: TheClosing, types: Annotated[str | None, Query()] = None
) -> StreamingResponse:
    """The org's calls and agents changing, as they change; `types=a.b,c.d` keeps those alone."""
    entries = await reading.follow_feed(feeds, actor.scope, types)
    return sse.stream(sse.pace(_frames(entries), closing=closing))


# Live only, no cursor: frame ids are per-log seqs that interleave, so a reconnect starts now.
@router.get("/v1/ops/events", response_model=None)
async def stream_box_events(_actor: TheOperator, feeds: TheFeeds, closing: TheClosing) -> StreamingResponse:
    """Every org's feed at once, each frame saying whose."""
    events = await reading.follow_box_feed(feeds)
    return sse.stream(sse.pace(_box_frames(events), closing=closing))


def _answer(
    found: reading.LogPage | AsyncIterator[reading.Projected] | None, closing: asyncio.Event
) -> Response | schemas.LogPage:
    if found is None:
        return Response(status_code=204)
    if isinstance(found, reading.LogPage):
        return schemas.LogPage.of(found)
    return sse.stream(sse.pace(_frames(found), closing=closing))


async def _frames(entries: AsyncIterator[reading.Projected]) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for one in entries:
        yield sse.frame(json.dumps(one.data, separators=(",", ":")), event=one.kind, id_=str(one.seq))


async def _box_frames(events: AsyncIterator[reading.BoxEvent]) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for one in events:
        frame = schemas.BoxEvent.of(one.org, one.env, one.entry)
        yield sse.frame(frame.dump_json(), event=one.entry.type, id_=str(one.entry.seq))


def _seq_of(header: str | None) -> int:
    try:
        return max(int(header or 0), 0)
    except ValueError:
        return 0
