"""The judges doors: one of Pinecall's switched, one of the org's written, a name nobody wrote refused."""

from tests.conftest import Gateway, Tenant, holding, needs_the_services


@needs_the_services
async def test_switching_a_judge_nobody_wrote_is_a_name_typed_wrong(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """A switch names one of Pinecall's or one the org wrote; any other is 404, never a 409 calling it the org's."""
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.put(
            f"/v1/agents/{agent}/judges/nonesuch", json={"on": True}, headers=tenant.person
        )
    assert refused.status_code == 404, refused.text
    assert refused.json()["detail"] == f"{agent} has no judge called nonesuch"


@needs_the_services
async def test_a_refusal_names_the_verb_to_type_never_a_route(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.delete(f"/v1/agents/{agent}/judges/grounded", headers=tenant.person)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"].endswith("`pinecall judges off grounded` turns it off")
