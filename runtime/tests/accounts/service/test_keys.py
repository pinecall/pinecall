"""Keys: what an issued key opens, the scopes a role gives, and a key stopped the moment it is revoked."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.repository.keys import ApiKeyRepository
from runtime.accounts.service import actor, invitations, keys, members
from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import ROLE_SCOPES, SERVER_SCOPES, KeyScope, Role
from runtime.kit.crypto import fingerprint
from runtime.kit.time import now
from tests.conftest import Gateway, Tenant, needs_the_database, needs_the_services

pytestmark = needs_the_database


async def test_a_servers_key_opens_its_org_with_its_scopes_and_no_person(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A server's key names its org and the server's scopes, and nobody behind it."""
    async with sessions.begin() as session:
        verified = await actor.verify_key(session, tenant.server_key)
    assert verified is not None
    assert (verified.key.org, verified.membership) == (tenant.org, None)
    assert frozenset(verified.key.scopes) == SERVER_SCOPES


async def test_a_persons_key_carries_exactly_the_scopes_of_their_role(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """An admin's key opens what an admin may; a supervisor's never `keys`."""
    async with sessions.begin() as session:
        verified = await actor.verify_key(session, tenant.person_key)
    assert verified is not None
    assert verified.membership is not None and verified.membership.id == tenant.member
    assert frozenset(verified.key.scopes) == ROLE_SCOPES[Role.admin]
    assert KeyScope.keys not in ROLE_SCOPES[Role.supervisor]


async def test_a_revoked_key_opens_nothing_and_cannot_be_revoked_twice(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """Revoked, a key is unknown to verification; a second revocation finds no key."""
    async with sessions.begin() as session:
        stopped = await keys.revoke_fingerprint(session, key_cache, fingerprint(tenant.server_key))
    assert stopped == [fingerprint(tenant.server_key)]
    async with sessions.begin() as session:
        assert await actor.verify_key(session, tenant.server_key) is None
        assert await keys.revoke_fingerprint(session, key_cache, fingerprint(tenant.server_key)) == []


async def test_the_key_of_a_person_removed_from_the_org_opens_nothing(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """A person out of the org takes their keys with them, without anybody revoking them."""
    async with sessions.begin() as session:
        invitee = invitations.Invitee(f"qa@{tenant.slug}.test", "QA", Role.qa)
        invited = await invitations.invite(session, tenant.org, invitee, vouched=True, held_to_seats=False)
    async with sessions.begin() as session:
        seated = await invitations.accept_link(session, key_cache, invited.token, "a-password-for-qa", 8)
        assert seated is not None
        secret = (await keys.issue_person_key(session, seated.member)).secret
    async with sessions.begin() as session:
        await members.remove_member(session, key_cache, seated)
    async with sessions.begin() as session:
        assert await actor.verify_key(session, secret) is None


def test_an_unknown_scope_for_a_server_is_refused_and_none_asked_is_the_servers_own() -> None:
    """A server may not be given a person's scopes; asking for nothing is the server's set."""
    assert keys.server_scopes(None) == SERVER_SCOPES
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


@needs_the_services
async def test_a_person_reads_their_own_sign_ins_and_which_one_is_this(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """GET /v1/me/keys lists the person's live keys alone, the one of this request marked, never a server's."""
    async with sessions.begin() as session:
        seat = await members.get_member(session, tenant.org, tenant.member)
        other = await keys.issue_person_key(session, seat.member, label="a phone")
    listed = await gateway.http.get("/v1/me/keys", headers=tenant.person)
    assert listed.status_code == 200, listed.text
    rows = {row["fingerprint"]: row for row in listed.json()}
    assert set(rows) == {fingerprint(tenant.person_key), fingerprint(other.secret)}
    assert rows[fingerprint(tenant.person_key)]["current"] is True
    assert (rows[fingerprint(other.secret)]["current"], rows[fingerprint(other.secret)]["label"]) == (False, "a phone")
    revoked = await gateway.http.post(f"/v1/keys/{fingerprint(other.secret)}/revoke", headers=tenant.person)
    assert revoked.status_code == 200, revoked.text
    left = (await gateway.http.get("/v1/me/keys", headers=tenant.person)).json()
    assert [row["fingerprint"] for row in left] == [fingerprint(tenant.person_key)]


async def test_a_sign_in_is_kept_a_month_from_its_last_use_and_a_servers_token_has_no_date(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A person's key is minted a month out and each use gives it a month again; unused past it, it opens nothing."""
    month = actor.A_SIGN_IN_IS_KEPT
    async with sessions.begin() as session:
        seat = await members.get_member(session, tenant.org, tenant.member)
        issued = await keys.issue_person_key(session, seat.member, label="a browser")
        assert issued.row.expires_at is not None
        assert month - timedelta(minutes=1) < issued.row.expires_at - now() <= month
        server = await actor.verify_key(session, tenant.server_key)
        assert server is not None and server.key.expires_at is None
    async with sessions.begin() as session:
        key = await ApiKeyRepository(session).find(issued.row.id)
        assert key is not None
        await ApiKeyRepository(session).update(
            key, last_used_at=now() - timedelta(days=29), expires_at=now() + timedelta(days=1)
        )
    async with sessions.begin() as session:
        used = await actor.verify_key(session, issued.secret)
        assert used is not None and used.key.expires_at is not None
        assert month - timedelta(minutes=1) < used.key.expires_at - now() <= month
        await ApiKeyRepository(session).update(used.key, expires_at=now() - timedelta(seconds=1))
    async with sessions.begin() as session:
        with pytest.raises(
            actor.KeyExpired, match=r"this sign-in ended at .*30 days after it was last used: sign in again"
        ):
            await actor.verify_key(session, issued.secret)
        mine = await keys.list_sign_ins(session, actor.actor_of(used, used.key.env))
        assert issued.row.hash not in {one.fingerprint for one in mine}


@needs_the_services
async def test_a_person_ends_every_other_sign_in_of_theirs_and_keeps_the_one_asking(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """POST /v1/me/keys/revoke stops the person's other keys at once; this one and the org's server go on."""
    async with sessions.begin() as session:
        seat = await members.get_member(session, tenant.org, tenant.member)
        phone = await keys.issue_person_key(session, seat.member, label="a phone")
        browser = await keys.issue_person_key(session, seat.member, label="a browser")
    theirs = {"Authorization": f"Bearer {phone.secret}"}
    assert (await gateway.http.get("/v1/me", headers=theirs)).status_code == 200
    ended = await gateway.http.post("/v1/me/keys/revoke", headers=tenant.person)
    assert ended.status_code == 200, ended.text
    assert ended.json() == {"revoked": 2}
    assert (await gateway.http.get("/v1/me", headers=theirs)).status_code == 401
    assert (await gateway.http.get("/v1/me", headers={"Authorization": f"Bearer {browser.secret}"})).status_code == 401
    left = (await gateway.http.get("/v1/me/keys", headers=tenant.person)).json()
    assert [row["fingerprint"] for row in left] == [fingerprint(tenant.person_key)]
    assert (await gateway.http.get("/v1/agents", headers=tenant.server)).status_code == 200
    assert (await gateway.http.post("/v1/me/keys/revoke", headers=tenant.person)).json() == {"revoked": 0}
