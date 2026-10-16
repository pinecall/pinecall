"""The retention endpoints: a call, a contact, an agent or an org erased; the trail; the export."""

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from pinecall_runtime.accounts.service import keys, orgs
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Env, ReadKind
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Actor, Scope
from pinecall_runtime.kit.handles import Handles, TheHandles
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.retention import schemas, service
from pinecall_runtime.retention.auth import TeamKey, TheOperator

router = APIRouter()

NO_SUCH_CALL = "no call {call} in this key's org and env"
STILL_LIVE = "call {call} is still running: it can be erased once it has ended"
NOT_HELD = "agent {slug} is held right now: stop it, move it, and start it again"


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


def _recordings(handles: Handles) -> calls.Recordings:
    return calls.recordings_of(handles.settings, handles.http)


# The org's own calls, in the key's env; a holder's call is the holder's or the org's to erase.
def _sees_to_erase(where: Scope, owner: Scope) -> bool:
    same = where.org == owner.org and where.env == owner.env
    return same and owner.holder in (THE_ORGS_OWN, where.holder)


# ── the org's own ──


# The one endpoint that deletes from a call's log: through erasure's own path, never the trigger's.
@router.delete("/v1/calls/{call}")
async def erase_call(
    call: str, actor: TeamKey, serving: TheServing, handles: TheHandles, session: Session
) -> schemas.ErasureRow:
    """Erase one call: its log, facts, tokens, the memories it taught and its recording."""
    kept = await calls.head_of_call(session, call)
    if kept is None or kept.scope is None or not _sees_to_erase(actor.scope, kept.scope):
        raise NotFound(NO_SUCH_CALL.format(call=call))
    keys.check_agent(actor, kept.agent)
    if not kept.sealed:
        raise Conflict(STILL_LIVE.format(call=call))
    erased = await service.erase_call(session, _recordings(handles), kept.scope, call, by=_asked_by(actor))
    serving.logs.forget(call)
    return erased.trail


# A person's "delete my data": what they said on every call of the env, and what was kept.
@router.delete("/v1/contacts/{contact}")
async def erase_contact(
    contact: str, actor: TeamKey, serving: TheServing, handles: TheHandles, session: Session
) -> schemas.ErasureRow:
    """Erase a contact in the env: every call they were on and every fact kept of them."""
    erased = await service.erase_contact(session, _recordings(handles), actor.scope, contact, by=_asked_by(actor))
    for call in erased.calls:
        serving.logs.forget(call)
    return erased.trail


@router.get("/v1/org/erasures")
async def list_erasures(actor: TeamKey, session: Session) -> schemas.ErasureTrail:
    """The org's erasures, newest first: what went, when, and who asked."""
    return schemas.ErasureTrail(erasures=await service.trail_of(session, actor.org))


# The export streams after the endpoint returned and its session closed, so it opens one of its own.
@router.get("/v1/org/export", response_model=None)
async def export_org(actor: TeamKey, handles: TheHandles, session: Session) -> StreamingResponse:
    """The org's data in the key's env as JSON Lines: calls, memories, settings, documents."""
    await compliance.record_read(session, actor.scope, actor.org, ReadKind.export, by=_asked_by(actor))
    filename = f"pinecall-{actor.org}-{actor.env.value}.jsonl"
    return StreamingResponse(
        _one_per_line(handles, actor.org, actor.env),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _one_per_line(handles: Handles, org: str, env: Env) -> AsyncIterator[bytes]:
    async with handles.sessions() as session:
        async for line in service.export_lines(session, org, env):
            yield (line + "\n").encode()


# ── the operator's ──


@router.delete("/v1/ops/orgs/{named}", status_code=204)
async def erase_org(
    named: str, _actor: TheOperator, serving: TheServing, handles: TheHandles, session: Session
) -> None:
    """Erase the org whole, its calls and recordings too; refused while a key or route names it."""
    erased = await service.erase_unused_org(session, _recordings(handles), named, by=compliance.OPERATOR)
    for call in erased.calls:
        serving.logs.forget(call)


# An agent that is not the org's — run once under its key, a test, a copy — taken out whole, both
# envs. Refused while a process of the org holds it, which would only register it again; another
# org's agent of the same slug is not this one and is never looked at.
@router.delete("/v1/ops/orgs/{named}/agents/{agent}")
async def erase_agent(
    named: str, agent: str, _actor: TheOperator, serving: TheServing, handles: TheHandles, session: Session
) -> schemas.ErasureRow:
    """Erase one agent of the org, its logs, recordings and every row it owns; the trail row."""
    with box_wide():
        org = await orgs.get_org(session, named)
        if serving.registry.is_held(org.id, agent):
            raise Conflict(NOT_HELD.format(slug=agent))
        erased = await service.erase_agent(session, _recordings(handles), org.id, agent, by=compliance.OPERATOR)
    for call in erased.calls:
        serving.logs.forget(call)
    return erased.trail
