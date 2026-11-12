"""A call's lookups: the recall or the search of one turn, written on its log and answered as the model reads it."""

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.billing import service as billing
from runtime.enums import Channel
from runtime.exceptions import ServiceUnavailable, UpstreamError
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.knowledge.service import memory, search
from runtime.knowledge.service.embedder import Embedder, embedder_of
from runtime.postgres import DatabaseError
from runtime.wire.base import Entry
from runtime.wire.events import DocsSources, ErrorEvent, MemoryOps
from runtime.wire.parts import (
    DocSource,
    FoundChunk,
    MemoryFact,
    MemoryOp,
    PlatformTool,
    RecalledFact,
    RecalledFacts,
    SearchFound,
)

logger = logging.getLogger(__name__)

type Answer = SearchFound | RecalledFacts


# A call's log is `calls`', above this domain: what a lookup needs of it is this much, and the log of
# the call it runs for is handed in with the call.
class CallLog(Protocol):
    """What a lookup needs of the call's log: to append one entry."""

    async def append(self, kind: str, data: JsonObject | None = None, *, ephemeral: bool | None = None) -> Entry:
        """One entry on the call's log, numbered."""
        ...


@dataclass(frozen=True, slots=True)
class LookupCall:
    """The call a lookup runs for: whose it is, who the caller is remembered as, the agent as the call runs it."""

    scope: Scope
    call: str
    channel: Channel
    # The contact the platform knows the caller as; None when nobody is remembered.
    contact: str | None
    declaration: Declaration
    log: CallLog
    # When the endpoint answered: recency is measured from it.
    now: datetime


@dataclass(frozen=True, slots=True)
class LookupRequest:
    """What the app or the worker asks: which tool, its input, and the speech it is for."""

    tool: PlatformTool
    input: Mapping[str, Any]
    speech_id: str | None = None


# What one of the two tools is, said once: whether it may run for the call, how it runs, and what it
# answers when it does not.
@dataclass(frozen=True, slots=True)
class _Tool:
    may_run: Callable[[LookupCall, billing.Quotas], bool]
    run: Callable[[async_sessionmaker[AsyncSession], Embedder, LookupCall, LookupRequest, float], Awaitable[Answer]]
    nothing: Answer


# The results reach the model inside a tool result and nowhere else. A lookup that cannot run is
# an entry and the empty shape: the turn never waits on it. Nothing is written when a tool is
# off: an empty memory.ops would say a recall ran, and an empty docs.sources reads to the
# grounded judge as a search that found nothing. The quotas and the embedder are read per lookup,
# in a transaction closed before the vendor is asked: a plan changed mid-call, or the providers row
# edited, applies from the next turn, and no connection waits on the embedder.
async def look_up(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    http: httpx.AsyncClient,
    call: LookupCall,
    request: LookupRequest,
) -> Answer:
    """Recall or search for the call, written on its log; the empty shape when nothing may run."""
    tool = _tool_of(request.tool)
    started = time.perf_counter()
    try:
        async with sessions.begin() as session:
            quotas = await billing.get_quotas(session, call.scope.org, call.scope.env)
            embedder = await embedder_of(session, vault, http) if tool.may_run(call, quotas) else None
        if embedder is None:
            return tool.nothing
        return await tool.run(sessions, embedder, call, request, started)
    except (UpstreamError, ServiceUnavailable, DatabaseError) as failed:
        logger.warning("%s did not run for call %s", request.tool, call.call, exc_info=True)
        why = f"{request.tool} did not run for this turn: {failed or type(failed).__name__}"
        skipped = ErrorEvent(code=f"{request.tool}_skipped", message=why, recoverable=True)
        await call.log.append("error", skipped.dump())
        return tool.nothing


def _tool_of(name: PlatformTool) -> _Tool:
    match name:
        case "recall":
            return _Tool(_may_recall, _recall, RecalledFacts(facts=[]))
        case "search":
            return _Tool(_may_search, _search, SearchFound(chunks=[]))


# A memory at its cap is still read, since a cap is about keeping.
def _may_recall(call: LookupCall, quotas: billing.Quotas) -> bool:
    keeps = call.declaration.memory is not None and call.contact is not None
    return keeps and not quotas.is_switched_off("memory_facts")


def _may_search(call: LookupCall, quotas: billing.Quotas) -> bool:
    return bool(call.declaration.bases) and not quotas.is_switched_off("knowledge_chunks")


# The contact is the one the platform knows, never one the model named.
async def _recall(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    call: LookupCall,
    request: LookupRequest,
    started: float,
) -> Answer:
    contact = call.contact or ""
    query = _query(request)
    asked = memory.Recall(contact=contact, query=query, at=call.now)
    recalled = await memory.recall(sessions, embedder, call.scope, asked)
    op = MemoryOp(
        op="recall",
        contact=contact,
        query=query,
        facts=[
            MemoryFact(
                id=str(item.fact.id),
                text=item.fact.text,
                category=item.fact.category,
                score=item.score,
                source=item.fact.source_call,
            )
            for item in recalled
        ],
        took_ms=_since(started),
    )
    await call.log.append("memory.ops", MemoryOps(ops=[op], speech_id=request.speech_id).dump())
    return RecalledFacts(
        facts=[
            RecalledFact(
                text=" ".join(item.fact.text.split()),
                source=item.fact.source_call,
                since=item.fact.valid_from.date().isoformat(),
            )
            for item in recalled
            if item.fact.text.strip()
        ]
    )


# Every base in one search, so their scores are comparable; the app may say how many it wants.
async def _search(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    call: LookupCall,
    request: LookupRequest,
    started: float,
) -> Answer:
    docs = call.declaration.bases
    query = _query(request)
    wanted = request.input.get("k")
    k = wanted if isinstance(wanted, int) and wanted > 0 else max(item.k for item in docs)
    floors = {item.base: item.min_score or 0.0 for item in docs}
    found = await search.search(sessions, embedder, call.scope, search.SearchQuery(query=query, k=k, bases=floors))
    sources = DocsSources(
        query=query,
        sources=[
            DocSource(
                id=item.id, base=item.base, path=item.path, heading=item.heading, score=item.score, excerpt=item.text
            )
            for item in found
        ],
        took_ms=_since(started),
        speech_id=request.speech_id,
    )
    await call.log.append("docs.sources", sources.dump())
    return SearchFound(chunks=[FoundChunk(path=item.path, heading=item.heading, text=item.text) for item in found])


def _query(request: LookupRequest) -> str:
    return str(request.input.get("query") or "")


def _since(started: float) -> float:
    return (time.perf_counter() - started) * 1000
