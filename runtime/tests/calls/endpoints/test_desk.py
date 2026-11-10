"""Tests for the desk's doors: a live call told to take its stages anew."""

from tests.conftest import Gateway, Tenant, holding, needs_the_services


# The door answers before any worker does: a call minted and never answered has nothing to rebuild, and
# the one who asked is told so instead of reading a 202 that changed nothing.
@needs_the_services
async def test_a_call_no_worker_runs_has_no_stages_to_take_anew(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    async with holding(gateway, tenant, agent):
        minted = (
            await gateway.http.post("/v1/tokens", json={"agent": agent, "scope": "talk"}, headers=tenant.person)
        ).json()
    asked = await gateway.http.post(f"/v1/calls/{minted['call']}/stages", headers=tenant.person)
    assert asked.status_code == 404, asked.text
    # With the call's own token and no key, nobody is asked anything: the door takes a key that writes vendors.
    with_a_token = await gateway.http.post(f"/v1/calls/{minted['call']}/stages", params={"token": minted["log_token"]})
    assert with_a_token.status_code == 401, with_a_token.text
