"""The billing endpoints: what an org may use and has used, what a new org is given, an org's quotas."""

from fastapi import APIRouter

from pinecall_runtime.accounts.service import members, orgs
from pinecall_runtime.billing import schemas, service
from pinecall_runtime.billing.auth import AnyKey, TheOperator
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.channels import service as channels
from pinecall_runtime.kit.time import month_of
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.providers import service as providers

router = APIRouter()


# Any key of the org. `used` reads what admission reads, so this page and a refusal agree.
@router.get("/v1/limits")
async def limits(actor: AnyKey, serving: TheServing, session: Session) -> schemas.Limits:
    """Each quota of the key's env as {limit, used}, the lends, and where to buy more."""
    org, env = actor.org, actor.env
    quotas = await service.get_quotas(session, org, env)
    used = await service.get_usage(session, org, env, month_of(serving.logs.store.clock()))
    return schemas.Limits(
        minutes=schemas.Limit(limit=quotas.minutes, used=used.minutes),
        messages=schemas.Limit(limit=quotas.messages, used=used.messages),
        llm_tokens=schemas.Limit(limit=quotas.llm_tokens, used=used.input_tokens + used.output_tokens),
        concurrent_calls=schemas.Limit(limit=quotas.concurrent_calls, used=serving.live.running(org, env)),
        agents=schemas.Limit(limit=quotas.agents, used=len(serving.registry.slugs_of(org))),
        seats=schemas.Limit(limit=quotas.seats, used=await members.seats_taken(session, org)),
        numbers=schemas.Limit(limit=quotas.numbers, used=await channels.managed_in(session, org, env)),
        evals=schemas.Limit(limit=quotas.evals, used=used.evals),
        simulations=schemas.Limit(limit=quotas.simulations, used=used.simulations),
        lends=None if quotas.lends is None else sorted(quotas.lends),
        billing_url=serving.handles.settings.billing_url,
        world=env,
    )


@router.get("/v1/ops/admission")
async def get_admission(_actor: TheOperator, session: Session) -> service.Admission:
    """What a newborn org is given in each env; nothing limited on a box that never said."""
    return await service.get_admission(session)


# Read at the moment an org is made: the orgs already made keep their quotas.
@router.put("/v1/ops/admission")
async def put_admission(body: service.Admission, _actor: TheOperator, session: Session) -> service.Admission:
    """What a newborn org is given, replaced whole."""
    await service.set_admission(session, body)
    return body


@router.put("/v1/ops/orgs/{named}/quotas")
async def put_quotas(
    named: str, body: schemas.PutQuotasRequest, _actor: TheOperator, session: Session
) -> schemas.OrgQuotas:
    """The org's limits in one env, replaced whole; they bite the next call and register."""
    wanted = body.quotas
    quotas = service.Quotas(
        minutes=wanted.limits.get("minutes"),
        messages=wanted.limits.get("messages"),
        agents=wanted.limits.get("agents"),
        concurrent_calls=wanted.limits.get("concurrent_calls"),
        memory_facts=wanted.limits.get("memory_facts"),
        knowledge_chunks=wanted.limits.get("knowledge_chunks"),
        numbers=wanted.limits.get("numbers"),
        seats=wanted.limits.get("seats"),
        llm_tokens=wanted.limits.get("llm_tokens"),
        hosted_apps=wanted.limits.get("hosted_apps"),
        evals=wanted.limits.get("evals"),
        simulations=wanted.limits.get("simulations"),
        budget_usd=wanted.budget_usd,
        lends=None if wanted.lends is None else providers.parse_lending(wanted.lends),
    )
    with box_wide():
        org = await orgs.get_org(session, named)
        await service.set_quotas(session, org.id, body.env, quotas)
    return schemas.OrgQuotas.of(quotas)
