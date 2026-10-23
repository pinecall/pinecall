"""A page's tokens: seated with the attributes it asked for and its contact, and reading its log as itself."""

import jwt

from pinecall_runtime.kit.text import JsonObject
from tests.conftest import Gateway, Tenant, holding, needs_the_services


def claims_of(token: str) -> JsonObject:
    """What a token says, unverified: the gateway signs it, the test only reads it."""
    claims: JsonObject = jwt.decode(token, options={"verify_signature": False})
    return claims


@needs_the_services
async def test_a_page_is_seated_with_its_own_attributes_and_its_contact_and_reads_its_log_as_itself(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The attributes are published as given, the contact is the participant's metadata, and the log token is
    the same identity, so the events the page sends come back to it."""
    async with holding(gateway, tenant, agent):
        minted = await gateway.http.post(
            "/v1/tokens",
            json={"agent": agent, "scope": "chat", "contact": "c_1", "participant_attributes": {"plan": "pro"}},
            headers=tenant.person,
        )
    assert minted.status_code == 201, minted.text
    seat = claims_of(minted.json()["participant_token"])
    reading = claims_of(minted.json()["log_token"])
    assert seat["attributes"]["plan"] == "pro"
    assert seat["metadata"] == "c_1"
    assert reading["sub"] == seat["sub"]
