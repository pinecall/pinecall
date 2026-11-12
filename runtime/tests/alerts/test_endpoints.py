"""The monitors' endpoints: a monitor watches an agent the org has."""

from tests.conftest import Gateway, Tenant, holding, needs_the_services

pytestmark = needs_the_services


async def test_a_monitor_watches_an_agent_the_org_has(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """An agent no app of the org ever held is a slug typed wrong: 404, never a monitor that never fires."""
    body = {"name": "slow", "metric": "e2e_median_s", "above": True, "threshold": 2.0, "agent": "nobody-held"}
    refused = await gateway.http.post("/v1/monitors", json=body, headers=tenant.person)
    assert refused.status_code == 404, refused.text
    async with holding(gateway, tenant, agent):
        kept = await gateway.http.post("/v1/monitors", json={**body, "agent": agent}, headers=tenant.person)
    assert kept.status_code == 201, kept.text
