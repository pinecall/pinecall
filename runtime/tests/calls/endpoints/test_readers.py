"""The org's feed, read as an SDK reads it: every entry of the floor, or the types asked for alone."""

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
