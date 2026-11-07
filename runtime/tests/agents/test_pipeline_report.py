"""The pipeline report: the voices a call speaks unpicked, as the providers row says them."""

from tests.conftest import THE_CATALOG, Gateway, Tenant, holding, needs_the_services

pytestmark = needs_the_services


async def test_the_report_says_the_voice_each_vendor_speaks_unpicked_as_the_row_lists_it(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The console marks the voice a call would speak when the agent picked none: the row's, by vendor and language."""
    async with holding(gateway, tenant, agent):
        read = await gateway.http.get(f"/v1/agents/{agent}/pipeline", headers=tenant.person)
    assert read.status_code == 200, read.text
    assert read.json()["voice_defaults"] == THE_CATALOG.voices
