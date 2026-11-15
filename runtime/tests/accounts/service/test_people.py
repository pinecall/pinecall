"""A person's own password: changed with the one they have, refused without it, and what it ends."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import invitations, keys, members
from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import Role
from tests.conftest import A_PASSWORD, Gateway, Tenant, needs_the_services

NEW_PASSWORD = "a-new-password-of-mine"

pytestmark = needs_the_services


async def test_a_person_changes_their_password_and_their_other_sign_ins_end(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """PUT /v1/me/password: the new one signs in, the old one does not, this key goes on, every other is revoked."""
    async with sessions.begin() as session:
        seat = await members.get_member(session, tenant.org, tenant.member)
        elsewhere = await keys.issue_person_key(session, seat.member, label="another browser")
    other = {"authorization": f"Bearer {elsewhere.secret}"}
    assert (await gateway.http.get("/v1/whoami", headers=other)).status_code == 200
    changed = await gateway.http.put(
        "/v1/me/password", json={"current": A_PASSWORD, "password": NEW_PASSWORD}, headers=tenant.person
    )
    assert changed.status_code == 204, changed.text
    assert (await gateway.http.get("/v1/whoami", headers=tenant.person)).status_code == 200
    assert (await gateway.http.get("/v1/whoami", headers=other)).status_code == 401
    address = f"admin@{tenant.slug}.test"
    old = await gateway.http.post("/v1/login", json={"email": address, "password": A_PASSWORD})
    assert old.status_code == 401, old.text
    new = await gateway.http.post("/v1/login", json={"email": address, "password": NEW_PASSWORD})
    assert new.status_code == 200, new.text


async def test_a_wrong_current_password_and_a_short_new_one_change_nothing(gateway: Gateway, tenant: Tenant) -> None:
    """The key alone never chooses a password: a wrong current one is 403 (the key is alive), a short new one 400."""
    wrong = await gateway.http.put(
        "/v1/me/password", json={"current": "not-it-at-all", "password": NEW_PASSWORD}, headers=tenant.person
    )
    assert wrong.status_code == 403, wrong.text
    assert wrong.json()["detail"] == "that is not your current password"
    short = await gateway.http.put(
        "/v1/me/password", json={"current": A_PASSWORD, "password": "x"}, headers=tenant.person
    )
    assert short.status_code == 400, short.text
    address = f"admin@{tenant.slug}.test"
    still = await gateway.http.post("/v1/login", json={"email": address, "password": A_PASSWORD})
    assert still.status_code == 200, still.text


async def test_a_person_with_no_password_is_sent_to_the_link_in_their_mailbox(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """Who only ever signed in through a provider has none to prove themselves with: 409, and nothing set."""
    async with sessions.begin() as session:
        invitee = invitations.Invitee(f"google@{tenant.slug}.test", "By Google", Role.qa)
        await invitations.invite(session, tenant.org, invitee, vouched=True, held_to_seats=False)
        invited = await members.get_member_by_email(session, tenant.org, invitee.email)
        seated = await members.seat_vouched(session, key_cache, invited)
        assert seated is not None
        key = await keys.issue_person_key(session, seated.member)
    theirs = {"authorization": f"Bearer {key.secret}"}
    account = await gateway.http.get("/v1/me", headers=theirs)
    assert account.status_code == 200, account.text
    assert account.json()["has_password"] is False
    refused = await gateway.http.put(
        "/v1/me/password", json={"current": "anything", "password": NEW_PASSWORD}, headers=theirs
    )
    assert refused.status_code == 409, refused.text
