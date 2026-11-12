"""What the org is shown: every limit it was given, with what is used of each."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.billing import service as billing
from runtime.billing.service import quotas
from tests.billing.service.test_limits import limited
from tests.conftest import Gateway, Tenant, needs_the_services

# ── what the org is shown: every limit it was given ──


@needs_the_services
async def test_the_limits_an_org_reads_are_every_one_an_operator_can_set_with_what_is_used_of_each(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant
) -> None:
    """C B6: the budget, the hosted apps, the memory and the knowledge were limits `pinecall limits` never showed."""
    given = billing.Quotas(memory_facts=500, knowledge_chunks=2000, hosted_apps=3, budget_usd=60, minutes=30)
    await limited(sessions, tenant, given)
    answer = (await gateway.http.get("/v1/limits", headers=tenant.server)).json()
    for quota in quotas.QUOTA_NAMES:
        assert set(answer[quota]) == {"limit", "used"}, quota
    assert answer["budget_usd"] == {"limit": 60, "used": 0.0}
    assert (answer["memory_facts"], answer["knowledge_chunks"], answer["hosted_apps"]) == (
        {"limit": 500, "used": 0},
        {"limit": 2000, "used": 0},
        {"limit": 3, "used": 0},
    )
    assert answer["agents"]["limit"] is None
