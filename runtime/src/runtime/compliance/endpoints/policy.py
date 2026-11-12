"""The org's policy, who read its data, and the dial guards its operator sets."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.accounts.auth import TheNamedOrg
from runtime.compliance import schemas
from runtime.compliance.auth import TeamKey
from runtime.compliance.service import dial_guards, policy, reads
from runtime.postgres import Session, TheBoxSession

router = APIRouter()


# ── the policy ──


@router.get("/v1/org/policy")
async def get_policy(actor: TeamKey, session: Session) -> schemas.PolicyRow:
    """The org's compliance settings: how long a sealed call is kept, calling rules, who set them."""
    return schemas.PolicyRow.of(await policy.policy_of(session, actor.org))


@router.put("/v1/org/policy")
async def put_policy(body: schemas.PolicyBody, actor: TeamKey, session: Session) -> schemas.PolicyRow:
    """Replace the org's compliance settings whole, from the next nightly run."""
    hours = body.calling_hours
    wanted = policy.Policy(
        retention_days=body.retention_days,
        calling_hours=None if hours is None else policy.Hours(hours.from_, hours.until),
        per_number_day=body.per_number_day,
        consent_everywhere=body.consent_everywhere,
        disclosure=body.disclosure,
        recording_notice=body.recording_notice,
    )
    return schemas.PolicyRow.of(await policy.put_policy(session, actor.org, wanted, by=actor.asked_by))


# ── who read what ──


@router.get("/v1/org/reads")
async def list_reads(
    actor: TeamKey, session: Session, subject: Annotated[str | None, Query()] = None
) -> schemas.ReadsResponse:
    """Who read the org's calls, recordings, exports and memory in the key's env; of one subject when named."""
    listed = await reads.list_reads(session, actor.scope, subject=subject)
    return schemas.ReadsResponse(reads=[schemas.ReadRow.of(read) for read in listed])


# ── the dial guards ──


# The operator's: an org able to lift its own dial guards would have none.
@router.put("/v1/ops/orgs/{named}/dialling")
async def put_dialling(org: TheNamedOrg, body: schemas.PutDialGuards, session: TheBoxSession) -> schemas.DialGuards:
    """The org's dial guards, replaced whole; one left out is the default."""
    wanted = dial_guards.read_guards(body.dial_anywhere, body.per_minute, body.per_day, body.max_duration_s)
    return schemas.DialGuards.of(await dial_guards.put_guards(session, org.id, wanted))
