"""Consent and the do-not-call list: facts about a number, read and written by the org."""

from fastapi import APIRouter

from pinecall_runtime.enums import ConsentKind
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.postgres import Session
from pinecall_runtime.telephony import schemas
from pinecall_runtime.telephony.auth import CallsKey, TalkKey
from pinecall_runtime.telephony.service import consents
from pinecall_runtime.telephony.service.consents import Given

router = APIRouter()

# Who the trail names for an opt-out written at an endpoint, with no form behind it.
ASKED_BY_HAND = "asked at the console or the API"


@router.post("/v1/org/consents")
async def record_consent(body: schemas.RecordConsent, actor: TalkKey, session: Session) -> schemas.ConsentHistory:
    """Write one fact about a number, a consent or an opt-out; what stands for it after."""
    given = Given(kind=body.kind, source=body.source, given_by=_asked_by(actor), text=body.text, evidence=body.evidence)
    await consents.give_consent(session, actor.scope, body.number, given)
    return await consents.history_of(session, actor.scope, body.number)


@router.get("/v1/org/consents/{number}")
async def consent_of(number: str, actor: CallsKey, session: Session) -> schemas.ConsentHistory:
    """What stands for the number in the key's env, and every fact about it, newest first."""
    return await consents.history_of(session, actor.scope, number)


# An opt-out is a fact, not a deletion: the consent before it stays in the history.
@router.delete("/v1/org/consents/{number}")
async def opt_out(number: str, actor: TalkKey, session: Session) -> schemas.ConsentHistory:
    """Put the number on the do-not-call list: no call of the org's reaches it from now on."""
    await consents.give_consent(
        session, actor.scope, number, Given(kind=ConsentKind.opt_out, source=ASKED_BY_HAND, given_by=_asked_by(actor))
    )
    return await consents.history_of(session, actor.scope, number)


@router.get("/v1/org/dnc")
async def do_not_call(actor: CallsKey, session: Session, after: str | None = None) -> schemas.DoNotCall:
    """The env's do-not-call list, newest first, a page after the cursor."""
    return await consents.do_not_call(session, actor.scope, after=after)


@router.post("/v1/org/dnc")
async def import_do_not_call(
    body: schemas.DoNotCallImport, actor: TalkKey, session: Session
) -> schemas.DoNotCallImported:
    """Numbers the org's own list or its Registry scrub says not to call, onto the list at once."""
    given = Given(kind=ConsentKind.opt_out, source=body.source, given_by=_asked_by(actor))
    added, refused = await consents.opt_out_many(session, actor.scope, body.numbers, given)
    return schemas.DoNotCallImported(added=added, refused=refused)


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id
