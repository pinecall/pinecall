"""The persona endpoints: a caller is written only for a model and a voice that can run."""

import httpx

from tests.conftest import Gateway, Tenant, holding, needs_the_services

NOBODY_KEYED = "openai has no key: the org brought none and the box holds none"


async def written(gateway: Gateway, tenant: Tenant, agent: str, name: str, body: dict[str, str]) -> httpx.Response:
    return await gateway.http.put(f"/v1/agents/{agent}/personas/{name}", json=body, headers=tenant.server)


async def names_of(gateway: Gateway, tenant: Tenant, agent: str) -> list[str]:
    answer = await gateway.http.get(f"/v1/agents/{agent}/personas", headers=tenant.server)
    return [row["name"] for row in answer.json()["personas"] if row["owner"] != "pinecall"]


@needs_the_services
async def test_a_persona_written_for_a_vendor_nobody_keyed_is_refused_at_write_and_kept_nowhere(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """F F1: it was written, and failed only on a run, with the sentence it now says at write."""
    async with holding(gateway, tenant, agent):
        for field in ({"llm": "openai/gpt-5.4-mini"}, {"tts": "openai"}):
            answer = await written(gateway, tenant, agent, "x-openai", {"goal": "g", "style": "s", **field})
            assert answer.status_code == 503
            assert NOBODY_KEYED in answer.text
        assert await names_of(gateway, tenant, agent) == []


@needs_the_services
async def test_a_vendor_this_box_lacks_is_still_refused_as_a_400_and_a_vendor_it_keys_is_written(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        lacking = await written(gateway, tenant, agent, "x-none", {"goal": "g", "style": "s", "llm": "nonvendor/x"})
        assert lacking.status_code == 400
        assert "no vendor named 'nonvendor'" in lacking.text
        keyed = await written(gateway, tenant, agent, "x-acme", {"goal": "g", "style": "s", "llm": "acme/acme-1"})
        assert keyed.status_code == 200
        assert await names_of(gateway, tenant, agent) == ["x-acme"]


@needs_the_services
async def test_one_of_pinecalls_is_refused_for_a_model_nobody_keyed_when_it_is_told_how_to_be_played(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        answer = await written(gateway, tenant, agent, "in-a-hurry", {"llm": "openai/gpt-5.4-mini"})
    assert answer.status_code == 503
    assert NOBODY_KEYED in answer.text
