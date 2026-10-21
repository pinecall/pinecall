"""What a reader reads: the feed, every entry or the types asked, what a call's token may not, whose hang-up it says."""

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


@needs_the_services
async def test_a_hang_up_is_the_callers_own_said_with_the_calls_token_and_nobody_elses(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """A key is told to end with a verb, another call's token is refused, and the call's own is heard."""
    async with holding(gateway, tenant, agent):
        minted = [
            (
                await gateway.http.post("/v1/tokens", json={"agent": agent, "scope": "talk"}, headers=tenant.person)
            ).json()
            for _ in range(2)
        ]
    mine, theirs = minted[0], minted[1]
    with_a_key = await gateway.http.post(f"/v1/calls/{mine['call']}/hangup", headers=tenant.server)
    assert with_a_key.status_code == 403, with_a_key.text
    assert "the verb end" in with_a_key.text
    not_mine = await gateway.http.post(f"/v1/calls/{mine['call']}/hangup", params={"token": theirs["log_token"]})
    assert not_mine.status_code == 403, not_mine.text
    # Minted and never answered by a worker: there is no call to end, and the page is told so.
    for token in (mine["log_token"], mine["participant_token"]):
        heard = await gateway.http.post(f"/v1/calls/{mine['call']}/hangup", params={"token": token})
        assert heard.status_code == 404, heard.text
    # Any page may say it: the preflight of a foreign origin is answered, with POST allowed.
    asked = await gateway.http.options(
        f"/v1/calls/{mine['call']}/hangup",
        headers={"origin": "https://a-page.example", "access-control-request-method": "POST"},
    )
    assert asked.status_code == 200, asked.text
    assert asked.headers["access-control-allow-origin"] == "*"
    assert "POST" in asked.headers["access-control-allow-methods"]
