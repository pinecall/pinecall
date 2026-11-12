"""The erasure and export endpoints: a call, a contact, an agent or an org erased; the trail; the export."""

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from runtime.accounts.auth import TeamKey
from runtime.auth import TheOperator
from runtime.calls.auth import TheLogs, TheRecordings
from runtime.compliance import service as compliance
from runtime.enums import ReadKind
from runtime.handles import TheServers, TheSessions
from runtime.postgres import Session, TheBoxSession
from runtime.retention import schemas
from runtime.retention.auth import TheHolders
from runtime.retention.service import erasure, export

router = APIRouter()

NDJSON = "application/x-ndjson"


# ── the org's own ──


# The one endpoint that deletes from a call's log: through erasure's own path, never the trigger's.
@router.delete("/v1/calls/{call}")
async def erase_call(
    call: str, actor: TeamKey, recordings: TheRecordings, logs: TheLogs, session: Session
) -> schemas.ErasureRow:
    """Erase one call: its log, facts, tokens, the memories it taught and its recording."""
    erasing = erasure.Erasing(recordings, logs)
    return schemas.ErasureRow.of(await erasure.erase_own_call(session, erasing, actor, call))


@router.delete("/v1/contacts/{contact}")
async def erase_contact(
    contact: str, actor: TeamKey, recordings: TheRecordings, logs: TheLogs, session: Session
) -> schemas.ErasureRow:
    """Erase a contact in the env: every call they were on and every fact kept of them."""
    erasing = erasure.Erasing(recordings, logs)
    erased = await erasure.erase_contact(session, erasing, actor.scope, contact, by=actor.asked_by)
    return schemas.ErasureRow.of(erased)


@router.get("/v1/org/erasures")
async def list_erasures(actor: TeamKey, session: Session) -> schemas.ErasureTrail:
    """The org's erasures, newest first: what went, when, and who asked."""
    trail = await erasure.list_trail(session, actor.org)
    return schemas.ErasureTrail(erasures=[schemas.ErasureRow.of(row) for row in trail])


@router.get("/v1/org/export", response_model=None)
async def export_org(actor: TeamKey, sessions: TheSessions, session: Session) -> StreamingResponse:
    """The org's data in the key's env as JSON Lines: its calls, then everything it wrote or configured."""
    await compliance.record_read(session, actor.scope, actor.org, ReadKind.export, by=actor.asked_by)
    filename = f"pinecall-{actor.org}-{actor.env.value}.jsonl"
    lines = _end_each(export.export_lines(sessions, actor.org, actor.env))
    return StreamingResponse(
        lines, media_type=NDJSON, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ── the operator's ──


@router.delete("/v1/ops/orgs/{named}", status_code=204)
async def erase_org(
    named: str, _actor: TheOperator, recordings: TheRecordings, logs: TheLogs, session: TheBoxSession
) -> None:
    """Erase the org whole, its calls and recordings too; refused while a key or route names it."""
    await erasure.erase_unused_org(session, erasure.Erasing(recordings, logs), named, by=compliance.OPERATOR)


@router.delete("/v1/ops/orgs/{named}/agents/{agent}")
async def erase_agent(
    named: str,
    agent: str,
    _actor: TheOperator,
    recordings: TheRecordings,
    logs: TheLogs,
    servers: TheServers,
    holders: TheHolders,
    session: TheBoxSession,
) -> schemas.ErasureRow:
    """Erase one agent of the org, its logs, recordings and every row it owns; the trail row."""
    erasing = erasure.Erasing(recordings, logs)
    erased = await erasure.erase_agent(session, erasing, servers, holders, named, agent, by=compliance.OPERATOR)
    return schemas.ErasureRow.of(erased)


async def _end_each(lines: AsyncIterator[str]) -> AsyncIterator[bytes]:
    async for line in lines:
        yield (line + "\n").encode()
