"""A call's lookups: recall and search for one turn, written on its log; its turns read for memory."""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Channel
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.knowledge.schemas import FoundChunk, SearchFound
from pinecall_runtime.knowledge.service import bases, memory
from pinecall_runtime.knowledge.service.embedder import Embedder, EmbedderUnreachable, WrongModel
from pinecall_runtime.knowledge.service.extraction import Heard, Spoken
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import (
    AgentTurnEnded,
    DocsSources,
    ErrorEvent,
    MemoryOps,
    UserTurnEnded,
)
from pinecall_runtime.wire.parts import DocSource, MemoryFact, MemoryOp, PlatformTool

logger = logging.getLogger(__name__)


class CallLog(Protocol):
    """What a lookup needs of the call's log: to append one entry."""

    async def append(self, kind: str, data: JsonObject | None = None, *, ephemeral: bool | None = None) -> Entry:
        """One entry on the call's log, numbered."""
        ...


@dataclass(frozen=True, slots=True)
class LookupCall:
    """The call a lookup runs for: whose it is, who the caller is remembered as, what the agent declared."""

    scope: Scope
    call: str
    channel: Channel
    # The contact the platform knows the caller as; None when nobody is remembered.
    contact: str | None
    config: AgentConfig
    log: CallLog
    # When the endpoint answered: recency is measured from it.
    now: datetime


@dataclass(frozen=True, slots=True)
class LookupRequest:
    """What the app or the worker asks: which tool, its input, and the speech it is for."""

    tool: PlatformTool
    input: Mapping[str, Any]
    speech_id: str | None = None


# The results reach the model inside a tool result and nowhere else. A lookup that cannot run is
# an entry and the empty shape: the turn never waits on it. Nothing is written when a tool is
# off: an empty memory.ops would say a recall ran, and an empty docs.sources reads to the
# grounded judge as a search that found nothing.
async def lookup(
    session: AsyncSession,
    embedder: Embedder | None,
    call: LookupCall,
    request: LookupRequest,
    *,
    quotas: billing.Quotas,
) -> dict[str, Any]:
    """Recall or search for the call, written on its log; the empty shape when nothing may run."""
    if embedder is None or not _switched_on(call, request.tool, quotas):
        return _nothing_found(request.tool)
    started = time.perf_counter()
    try:
        if request.tool == "recall":
            return await _recalled(session, embedder, call, request, started=started)
        return await _searched(session, embedder, call, request, started=started)
    except (EmbedderUnreachable, WrongModel, SQLAlchemyError) as failed:
        logger.warning("%s did not run for call %s", request.tool, call.call, exc_info=True)
        why = f"{request.tool} did not run for this turn: {failed or type(failed).__name__}"
        skipped = ErrorEvent(code=f"{request.tool}_skipped", message=why, recoverable=True)
        await call.log.append("error", skipped.dump())
        return _nothing_found(request.tool)


def heard_in(
    call: str, channel: Channel, contact: str | None, config: AgentConfig, entries: Sequence[Entry], *, at: datetime
) -> Heard | None:
    """What the extraction model reads of a finished call; None when nothing is to be kept."""
    if contact is None or config.memory is None:
        return None
    return Heard(
        contact=contact,
        call=call,
        channel=channel,
        policy=config.memory,
        tools=tuple(tool.name for tool in config.tools),
        spoken=[spoken for entry in entries if (spoken := _spoken(entry)) is not None],
        at=at,
    )


# A memory at its cap is still read, since a cap is about keeping.
def _switched_on(call: LookupCall, tool: PlatformTool, quotas: billing.Quotas) -> bool:
    if tool == "recall":
        keeps = call.config.memory is not None and call.contact is not None
        return keeps and not quotas.is_switched_off("memory_facts")
    return bool(call.config.bases) and not quotas.is_switched_off("knowledge_chunks")


# The contact is the one the platform knows, never one the model named.
async def _recalled(
    session: AsyncSession, embedder: Embedder, call: LookupCall, request: LookupRequest, *, started: float
) -> dict[str, Any]:
    contact = call.contact or ""
    query = _query(request)
    recalled = await memory.recall(
        session, embedder, call.scope, memory.Recall(contact=contact, query=query, at=call.now)
    )
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
            for item in recalled.facts
        ],
        took_ms=_since(started),
    )
    await call.log.append("memory.ops", MemoryOps(ops=[op], speech_id=request.speech_id).dump())
    return {
        "facts": [
            {
                "text": " ".join(item.fact.text.split()),
                "source": item.fact.source_call,
                "since": item.fact.valid_from.date().isoformat(),
            }
            for item in recalled.facts
            if item.fact.text.strip()
        ]
    }


# Every base in one search, so their scores are comparable; the app may say how many it wants.
async def _searched(
    session: AsyncSession, embedder: Embedder, call: LookupCall, request: LookupRequest, *, started: float
) -> dict[str, Any]:
    docs = call.config.bases
    query = _query(request)
    wanted = request.input.get("k")
    k = wanted if isinstance(wanted, int) and wanted > 0 else max(item.k for item in docs)
    floors = {item.base: item.min_score or 0.0 for item in docs}
    searched = await bases.search(session, embedder, call.scope, bases.SearchQuery(query=query, k=k, bases=floors))
    sources = DocsSources(
        query=query,
        sources=[
            DocSource(
                id=item.id, base=item.base, path=item.path, heading=item.heading, score=item.score, excerpt=item.text
            )
            for item in searched.found
        ],
        took_ms=_since(started),
        speech_id=request.speech_id,
    )
    await call.log.append("docs.sources", sources.dump())
    return SearchFound(
        chunks=[FoundChunk(path=item.path, heading=item.heading, text=item.text) for item in searched.found]
    ).dump()


def _nothing_found(tool: PlatformTool) -> dict[str, Any]:
    if tool == "recall":
        return {"facts": []}
    return SearchFound(chunks=[]).dump()


def _query(request: LookupRequest) -> str:
    return str(request.input.get("query") or "")


def _spoken(entry: Entry) -> Spoken | None:
    if entry.type == "turn.user":
        return Spoken(role="user", text=UserTurnEnded.parse(entry.data, "turn.user").text)
    if entry.type == "turn.agent":
        return Spoken(role="agent", text=AgentTurnEnded.parse(entry.data, "turn.agent").text)
    return None


def _since(started: float) -> float:
    return (time.perf_counter() - started) * 1000
