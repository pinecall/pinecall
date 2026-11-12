"""The billing endpoints: what a newborn org is given, and an org's quotas as the operator sets them."""

from fastapi import APIRouter

from runtime.accounts.auth import TheNamedOrg
from runtime.auth import TheOperator
from runtime.billing import schemas
from runtime.billing.service import admission, quotas
from runtime.postgres import Session, TheBoxSession
from runtime.providers import service as providers

router = APIRouter()


@router.get("/v1/ops/admission")
async def get_admission(_actor: TheOperator, session: Session) -> schemas.Admission:
    """What a newborn org is given in each env; nothing limited on a box that never said."""
    kept = await admission.get_admission(session)
    return schemas.Admission.model_validate(admission.dump_admission(kept))


# Read at the moment an org is made: the orgs already made keep their quotas.
@router.put("/v1/ops/admission")
async def put_admission(body: schemas.Admission, _actor: TheOperator, session: Session) -> schemas.Admission:
    """What a newborn org is given, replaced whole."""
    await admission.put_admission(session, admission.load_admission(body.model_dump(mode="json")))
    return body


@router.put("/v1/ops/orgs/{named}/quotas")
async def put_quotas(org: TheNamedOrg, body: schemas.PutQuotasRequest, session: TheBoxSession) -> schemas.OrgQuotas:
    """The org's limits in one env, replaced whole; they bite the next call and register."""
    wanted = body.quotas
    lends = None if wanted.lends is None else providers.parse_lending(wanted.lends)
    return _body_of(await quotas.put_limits(session, org.id, body.env, wanted.limits_named(), lends))


# Not a month's count but a shape: a ceiling on the fleet's seats the org's simulated callers take at
# once, and on what one comparison places. The org's quotas and lends are kept.
@router.put("/v1/ops/orgs/{named}/simulating")
async def put_simulating(
    org: TheNamedOrg, body: schemas.PutSimulatingRequest, session: TheBoxSession
) -> schemas.OrgQuotas:
    """How the org's simulations are shaped in one env: the calls at once, and the calls a comparison places."""
    kept = await quotas.put_simulating(
        session, org.id, body.env, simulations_at_once=body.simulations_at_once, comparison_calls=body.comparison_calls
    )
    return _body_of(kept)


# The same shape read and written: `lends` comes back sorted.
def _body_of(kept: quotas.Quotas) -> schemas.OrgQuotas:
    return schemas.OrgQuotas(
        limits=dict(kept.limits),
        budget_usd=kept.budget_usd,
        lends=None if kept.lends is None else sorted(kept.lends),
        simulations_at_once=kept.simulations_at_once,
        comparison_calls=kept.comparison_calls,
    )
