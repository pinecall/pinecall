"""Keys: what an issued key opens, the scopes a role gives, and a key stopped the moment it is revoked."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import keys, members
from pinecall_runtime.enums import KeyScope, Role
from pinecall_runtime.kit.crypto import fingerprint
from tests.conftest import Gateway, Tenant, needs_the_database, needs_the_services

pytestmark = needs_the_database


async def test_a_servers_key_opens_its_org_with_its_scopes_and_no_person(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A server's key names its org and the server's scopes, and nobody behind it."""
    async with sessions.begin() as session:
        verified = await keys.verify_key(session, tenant.server_key)
    assert verified is not None
    key, person = verified
    assert (key.org, person) == (tenant.org, None)
    assert frozenset(key.scopes) == keys.SERVER_SCOPES


async def test_a_persons_key_carries_exactly_the_scopes_of_their_role(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """An admin's key opens what an admin may; a supervisor's never `keys`."""
    async with sessions.begin() as session:
        verified = await keys.verify_key(session, tenant.person_key)
    assert verified is not None
    key, person = verified
    assert person is not None and person.id == tenant.member
    assert frozenset(key.scopes) == keys.ROLE_SCOPES[Role.admin]
    assert KeyScope.keys not in keys.ROLE_SCOPES[Role.supervisor]


async def test_a_revoked_key_opens_nothing_and_cannot_be_revoked_twice(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Revoked, a key is unknown to verification; a second revocation finds no key."""
    async with sessions.begin() as session:
        stopped = await keys.revoke_fingerprint(session, fingerprint(tenant.server_key))
    assert stopped == [fingerprint(tenant.server_key)]
    async with sessions.begin() as session:
        assert await keys.verify_key(session, tenant.server_key) is None
        assert await keys.revoke_fingerprint(session, fingerprint(tenant.server_key)) == []


async def test_the_key_of_a_person_removed_from_the_org_opens_nothing(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A person out of the org takes their keys with them, without anybody revoking them."""
    async with sessions.begin() as session:
        invited = await members.invite(
            session, tenant.org, members.Invitee(f"qa@{tenant.slug}.test", "QA", Role.qa), seats=None, vouched=True
        )
    async with sessions.begin() as session:
        seated = await members.accept_link(session, invited.token, "a-password-for-qa", 8)
        assert seated is not None
        _, secret = await keys.issue_person_key(session, seated)
    async with sessions.begin() as session:
        await members.remove_member(session, tenant.org, seated.id)
    async with sessions.begin() as session:
        assert await keys.verify_key(session, secret) is None


def test_an_unknown_scope_for_a_server_is_refused_and_none_asked_is_the_servers_own() -> None:
    """A server may not be given a person's scopes; asking for nothing is the server's set."""
    assert keys.server_scopes(None) == keys.SERVER_SCOPES
    with pytest.raises(keys.NotAServersScopes):
        keys.server_scopes([KeyScope.keys])


@needs_the_services
async def test_a_key_revoked_through_the_api_is_refused_on_its_very_next_request(
    gateway: Gateway, tenant: Tenant
) -> None:
    """Every gateway forgets a revoked key at once, and says it is a key that opens nothing, not a missing one."""
    assert (await gateway.http.get("/v1/agents", headers=tenant.server)).status_code == 200
    revoked = await gateway.http.post(f"/v1/keys/{fingerprint(tenant.server_key)}/revoke", headers=tenant.person)
    assert revoked.status_code == 200, revoked.text
    refused = await gateway.http.get("/v1/agents", headers=tenant.server)
    assert refused.status_code == 401
    assert "this key opens nothing here" in refused.json()["detail"]
    nothing = await gateway.http.get("/v1/agents")
    assert nothing.json()["detail"] == "this endpoint takes an API key"
