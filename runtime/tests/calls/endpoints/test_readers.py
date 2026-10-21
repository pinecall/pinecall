"""What a reader reads: the org's feed, every entry or the types asked for, and what a call's own token may not."""

from tests.conftest import Gateway, Tenant, holding, needs_the_services

AS_A_STREAM = {"accept": "text/event-stream"}


@needs_the_services
async def test_the_feed_keeps_the_types_asked_for(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """An app held and let go writes registered then detached; a reader of the latter meets it first."""
    headers = {**tenant.person, **AS_A_STREAM}
    async with gateway.http.stream("GET", "/v1/events", params={"types": "agent.detached"}, headers=headers) as feed:
        assert feed.status_code == 200, await feed.aread()
        lines = feed.aiter_lines()
        assert (await anext(lines)).startswith("retry:")
        async with holding(gateway, tenant, agent):
            pass
        async for line in lines:
            if line.startswith("event:"):
                assert line == "event: agent.detached"
                break


@needs_the_services
async def test_a_type_that_is_no_name_is_refused(gateway: Gateway, tenant: Tenant) -> None:
    refused = await gateway.http.get("/v1/events", params={"types": "Not A Type"}, headers=tenant.person)
    assert refused.status_code == 400, refused.text


@needs_the_services
async def test_a_calls_own_token_reads_its_log_and_never_its_prompt(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The prompt is the operator's words: a page's token, even one minted to read as the tenant, is refused."""
    async with holding(gateway, tenant, agent):
        minted = await gateway.http.post(
            "/v1/tokens", json={"agent": agent, "scope": "talk", "log": "tenant"}, headers=tenant.person
        )
    assert minted.status_code == 201, minted.text
    taken = minted.json()
    for token in (taken["log_token"], taken["participant_token"]):
        refused = await gateway.http.get(f"/v1/calls/{taken['call']}/prompt", params={"token": token})
        assert refused.status_code == 403, refused.text
        assert "read with a key" in refused.text
