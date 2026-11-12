"""The operator's telephony doors: one org as it stands, read by the box's own key alone."""

from tests.conftest import BOX, Gateway, Tenant, needs_the_services

pytestmark = needs_the_services


async def test_an_org_as_it_stands_is_its_quotas_in_each_env_its_dial_guards_and_what_it_holds(
    gateway: Gateway, tenant: Tenant
) -> None:
    answer = await gateway.http.get(f"/v1/ops/orgs/{tenant.slug}", headers=BOX)
    assert answer.status_code == 200, answer.text
    profile = answer.json()
    assert (profile["id"], profile["slug"]) == (tenant.org, tenant.slug)
    assert set(profile["quotas"]) == {"sandbox", "production"}
    assert set(profile["dialling"]) == {"dial_anywhere", "per_minute", "per_day", "max_duration_s"}
    held = profile["holding"]
    assert (held["memory_facts"], held["knowledge_chunks"], held["numbers"]) == (0, 0, 0)
    assert held["seats"] >= 1, "the org's admin holds a seat"


async def test_an_org_is_the_operators_to_read_and_not_its_own_key(gateway: Gateway, tenant: Tenant) -> None:
    answer = await gateway.http.get(f"/v1/ops/orgs/{tenant.slug}", headers=tenant.server)
    assert answer.status_code == 403
    missing = await gateway.http.get("/v1/ops/orgs/an-org-nobody-made", headers=BOX)
    assert missing.status_code == 404
