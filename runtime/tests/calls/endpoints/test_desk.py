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


# The stages of a teammate are an agent's somebody is serving: a name nobody holds is refused before any worker is told.
@needs_the_services
async def test_a_call_takes_the_stages_of_an_agent_somebody_holds_and_of_no_other(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        minted = (
            await gateway.http.post("/v1/tokens", json={"agent": agent, "scope": "talk"}, headers=tenant.person)
        ).json()
        door = f"/v1/calls/{minted['call']}/stages"
        of_nobody = await gateway.http.post(door, json={"agent": "nobody-holds-this"}, headers=tenant.server)
        assert of_nobody.status_code == 404, of_nobody.text
        assert "nobody holds nobody-holds-this" in of_nobody.text
        # The agent is held and the call has no worker yet: the worker is the one that was not found.
        of_a_teammate = await gateway.http.post(door, json={"agent": agent}, headers=tenant.server)
        assert of_a_teammate.status_code == 404, of_a_teammate.text
        assert "nobody holds" not in of_a_teammate.text
