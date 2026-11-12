"""What the org is shown: every limit it was given, with what is used of each."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.enums import Env
from tests.conftest import Gateway, Tenant, needs_the_services

# ── what the org is shown: every limit it was given ──


# Seats and the budget are the org's, not an env's: a key of the sandbox reads them off the org's own
# row, the one its admissions are held to, and every other limit off its env's.
@needs_the_services
async def test_the_limits_an_org_reads_are_every_one_an_operator_can_set_with_what_is_used_of_each(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant
) -> None:
    """C B6: the budget, the hosted apps, the memory and the knowledge were limits `pinecall limits` never showed."""
    in_the_sandbox = billing.Quotas(memory_facts=500, knowledge_chunks=2000, hosted_apps=3, minutes=30, seats=9)
    async with sessions.begin() as session:
        await quotas.put_quotas(session, tenant.org, Env.sandbox, in_the_sandbox)
        await quotas.put_quotas(session, tenant.org, quotas.THE_ORGS_ROW, billing.Quotas(budget_usd=60, seats=4))
    answer = (await gateway.http.get("/v1/limits", headers=tenant.server)).json()
    for quota in quotas.QUOTA_NAMES:
        assert set(answer[quota]) == {"limit", "used"}, quota
    assert answer["budget_usd"] == {"limit": 60, "used": 0.0}
    assert answer["seats"] == {"limit": 4, "used": 1}
    assert (answer["memory_facts"], answer["knowledge_chunks"], answer["hosted_apps"]) == (
        {"limit": 500, "used": 0},
        {"limit": 2000, "used": 0},
        {"limit": 3, "used": 0},
    )
    assert (answer["minutes"]["limit"], answer["agents"]["limit"]) == (30, None)
    assert (answer["lends"], answer["world"]) == (None, "sandbox")
