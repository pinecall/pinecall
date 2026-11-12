"""The pipeline report: the voices a call speaks unpicked, as the providers row says them, and the agent's greeting."""

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


# The greeting is the one part of the report shaped by the wire; read as the service holds it, it
# was refused and the report answered 500 for every agent that greets (2026-11-12, the console's
# Configure page).
async def test_the_report_of_an_agent_that_greets_says_its_greeting(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """An agent's greeting is in its report as its settings say it."""
    async with holding(gateway, tenant, agent):
        kept = await gateway.http.put(
            f"/v1/agents/{agent}/settings", json={"config": {"greeting": {"say": "Hola."}}}, headers=tenant.person
        )
        assert kept.status_code == 200, kept.text
        read = await gateway.http.get(f"/v1/agents/{agent}/pipeline", headers=tenant.person)
    assert read.status_code == 200, read.text
    assert read.json()["greeting"] == {"say": "Hola.", "reply": None, "allow_interruptions": None}
