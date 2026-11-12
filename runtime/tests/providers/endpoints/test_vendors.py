"""The vendors' doors: a plugin's options for a stage, and a vendor not installed refused saying so."""

from tests.conftest import Gateway, Tenant, needs_the_services
from tests.fakes import acme


@needs_the_services
async def test_the_door_answers_a_vendors_options_for_a_stage_and_refuses_a_stage_it_has_not(
    gateway: Gateway, tenant: Tenant
) -> None:
    """`GET /v1/providers/acme/options?modality=stt` lists them; a vendor not installed is a 400 saying so."""
    answered = await gateway.http.get(
        f"/v1/providers/{acme.ACME}/options", params={"modality": "stt"}, headers=tenant.person
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["vendor"] == acme.ACME and any(
        one["name"] == "keyterms" for one in answered.json()["options"]
    )
    refused = await gateway.http.get("/v1/providers/nobody/options", params={"modality": "stt"}, headers=tenant.person)
    assert refused.status_code == 400 and "no vendor named" in refused.json()["detail"]
