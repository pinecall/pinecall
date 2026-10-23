"""The org's judging: the model its calls are judged on is tried on the org's keys before it is kept."""

from tests.conftest import Gateway, Tenant, needs_the_services
from tests.fakes import acme


async def kept_model(gateway: Gateway, tenant: Tenant) -> dict[str, object] | None:
    answer = await gateway.http.get("/v1/org/judging", headers=tenant.person)
    model: dict[str, object] | None = answer.json()["model"]
    return model


@needs_the_services
async def test_a_model_its_vendor_turns_away_is_refused_naming_it_and_never_kept(
    gateway: Gateway, tenant: Tenant
) -> None:
    """F F6: `judging --model openai/nosuchmodel-xyz` was kept, and every hang-up then failed on it."""
    body = {"on": True, "model": {"provider": acme.ACME, "model": acme.UNKNOWN}}
    refused = await gateway.http.put("/v1/org/judging", json=body, headers=tenant.person)
    assert refused.status_code == 400, refused.text
    assert f"{acme.ACME} refused the judge model {acme.ACME}/{acme.UNKNOWN}: no such model" in refused.json()["detail"]
    assert "judges its calls on this model, and it cannot run there" in refused.json()["detail"]
    assert await kept_model(gateway, tenant) is None


@needs_the_services
async def test_a_model_the_vendor_answers_on_is_kept(gateway: Gateway, tenant: Tenant) -> None:
    body = {"on": True, "model": {"provider": acme.ACME, "model": acme.MODEL}}
    kept = await gateway.http.put("/v1/org/judging", json=body, headers=tenant.person)
    assert kept.status_code == 200, kept.text
    model = await kept_model(gateway, tenant)
    assert model is not None and (model["provider"], model["model"]) == (acme.ACME, acme.MODEL)
