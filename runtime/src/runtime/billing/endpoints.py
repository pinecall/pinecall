"""The billing endpoints: what a newborn org is given, and an org's quotas as the operator sets them."""

from fastapi import APIRouter

from runtime.accounts import service as accounts
from runtime.accounts.auth import AnyKey, TheNamedOrg
from runtime.auth import TheOperator
from runtime.billing import schemas
from runtime.billing.service import admission, limits, quotas
from runtime.handles import TheSettings
from runtime.hosting import service as hosting
from runtime.knowledge import service as knowledge
from runtime.live.auth import TheLive
from runtime.postgres import Session, TheBoxSession
from runtime.providers import service as providers
from runtime.telephony import service as telephony

router = APIRouter()


# Any key of the org. What is held is counted by its owner, as each admission is asked with it; an
# endpoint may ask every domain, which no service below them can.
@router.get("/v1/limits")
async def get_limits(actor: AnyKey, live: TheLive, settings: TheSettings, session: Session) -> schemas.Limits:
    """Each quota of the key's env as {limit, used}, the lends, and where to buy more."""
    org, env = actor.org, actor.env
    held = limits.Held(
        concurrent_calls=len(live.calls.holding(org, env)),
        agents=len(live.holders.slugs_of(org)),
        seats=await accounts.count_seated(session, org),
        numbers=await telephony.count_managed(session, org, env),
        memory_facts=await knowledge.count_facts(session, org, env),
        knowledge_chunks=await knowledge.count_chunks(session, org, env),
        hosted_apps=len(await hosting.list_standing(session, env, org)),
    )
    read = await limits.read_limits(session, org, env, held, at=live.store.clock())
    said: dict[str, object] = {str(name): measure for name, measure in read.measures.items()}
    said |= {"lends": None if read.lends is None else sorted(read.lends)}
    said |= {"billing_url": settings.billing_url, "world": env}
    return schemas.Limits.model_validate(said, from_attributes=True)


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
    return schemas.OrgQuotas.of(await quotas.put_limits(session, org.id, body.env, wanted.limits_named(), lends))


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
    return schemas.OrgQuotas.of(kept)
