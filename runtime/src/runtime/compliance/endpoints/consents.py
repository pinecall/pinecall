"""Consent and the do-not-call list: facts about a number, read and written by the org."""

from fastapi import APIRouter

from runtime.compliance import schemas
from runtime.compliance.auth import CallsKey, TalkKey
from runtime.compliance.service import consents
from runtime.enums import ConsentKind
from runtime.postgres import Session

router = APIRouter()


@router.post("/v1/org/consents")
async def record_consent(body: schemas.RecordConsent, actor: TalkKey, session: Session) -> schemas.ConsentHistory:
    """Write one fact about a number, a consent or an opt-out; what stands for it after."""
    given = consents.Given(
        kind=body.kind, source=body.source, given_by=actor.asked_by, text=body.text, evidence=body.evidence
    )
    return schemas.ConsentHistory.of(await consents.record_consent(session, actor.scope, body.number, given))


@router.get("/v1/org/consents/{number}")
async def consent_of(number: str, actor: CallsKey, session: Session) -> schemas.ConsentHistory:
    """What stands for the number in the key's env, and every fact about it, newest first."""
    return schemas.ConsentHistory.of(await consents.history_of(session, actor.scope, number))


# An opt-out is a fact, not a deletion: the consent before it stays in the history.
@router.delete("/v1/org/consents/{number}")
async def opt_out(number: str, actor: TalkKey, session: Session) -> schemas.ConsentHistory:
    """Put the number on the do-not-call list: no call of the org's reaches it from now on."""
    return schemas.ConsentHistory.of(await consents.opt_out(session, actor.scope, number, by=actor.asked_by))


@router.get("/v1/org/dnc")
async def do_not_call(actor: CallsKey, session: Session, after: str | None = None) -> schemas.DoNotCall:
    """The env's do-not-call list, newest first, a page after the cursor."""
    return schemas.DoNotCall.of(await consents.list_do_not_call(session, actor.scope, after=after))


@router.post("/v1/org/dnc")
async def import_do_not_call(
    body: schemas.DoNotCallImport, actor: TalkKey, session: Session
) -> schemas.DoNotCallImported:
    """Numbers the org's own list or its Registry scrub says not to call, onto the list at once."""
    given = consents.Given(kind=ConsentKind.opt_out, source=body.source, given_by=actor.asked_by)
    return schemas.DoNotCallImported.of(await consents.opt_out_many(session, actor.scope, body.numbers, given))
