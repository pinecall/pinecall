"""A member's password set with no link: by the service, through the admin's door, and refused where it must be."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import keys, members, signin
from pinecall_runtime.enums import MemberStatus, Role
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from tests.conftest import A_PASSWORD, Gateway, Tenant, make_tenant, needs_the_database, needs_the_services

NEW_PASSWORD = "a-new-password-of-ours"


@needs_the_database
async def test_an_invited_person_given_a_password_is_active_and_signs_in_with_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """No link opened: the password set makes them active, and it opens a key."""
    email = f"invited@{tenant.slug}.test"
    async with sessions.begin() as session:
        await members.invite(session, tenant.org, members.Invitee(email, "Invited", Role.qa), seats=None)
        found = await members.member_by_email(session, tenant.org, email)
        assert found.status is MemberStatus.invited
        changed = await members.set_password(session, tenant.org, found.id, NEW_PASSWORD, 8)
        assert changed.status is MemberStatus.active
    async with sessions.begin() as session:
        signed = await signin.sign_in_with_password(session, signin.PasswordSignIn(email=email, password=NEW_PASSWORD))
    assert signed.secret


@needs_the_database
async def test_a_short_password_a_disabled_member_and_an_unknown_address_are_refused(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The box's floor holds; a disabled member is enabled first; an address nobody has is named."""
    email = f"gone@{tenant.slug}.test"
    async with sessions.begin() as session:
        await members.invite(session, tenant.org, members.Invitee(email, "Gone", Role.qa), seats=None)
        found = await members.member_by_email(session, tenant.org, email)
        with pytest.raises(ValidationError):
            await members.set_password(session, tenant.org, found.id, "short", 8)
        await members.update_member(session, tenant.org, found.id, members.Change(status=MemberStatus.disabled))
    async with sessions.begin() as session:
        with pytest.raises(Conflict, match="enable them before setting their password"):
            await members.set_password(session, tenant.org, found.id, NEW_PASSWORD, 8)
        with pytest.raises(NotFound, match=f"nobody with the address nobody@{tenant.slug}.test"):
            await members.member_by_email(session, tenant.org, f"nobody@{tenant.slug}.test")


@needs_the_services
async def test_an_admin_sets_a_members_password_through_the_door(gateway: Gateway, tenant: Tenant) -> None:
    """PUT /v1/members/{id}/password answers the member, active, and never the password."""
    answer = await gateway.http.put(
        f"/v1/members/{tenant.member}/password", json={"password": NEW_PASSWORD}, headers=tenant.person
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "active"
    assert NEW_PASSWORD not in answer.text
    short = await gateway.http.put(
        f"/v1/members/{tenant.member}/password", json={"password": "x"}, headers=tenant.person
    )
    assert short.status_code == 400, short.text


# ── whose password it is ──


@needs_the_database
async def test_an_admin_cannot_type_a_password_for_a_person_of_another_org(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The takeover of 2026-11-11: invite another org's member, type their password, sign in as them there."""
    theirs = await make_tenant(sessions)
    victim = f"admin@{theirs.slug}.test"
    async with sessions.begin() as session:
        await members.invite(session, tenant.org, members.Invitee(victim, "Not ours", Role.qa), seats=None)
        planted = await members.member_by_email(session, tenant.org, victim)
        with pytest.raises(Conflict, match="send them a reset"):
            await members.set_password_as_admin(session, tenant.org, planted.id, NEW_PASSWORD, 8)
        assert planted.status is MemberStatus.invited
    async with sessions.begin() as session:
        with pytest.raises(signin.NobodyAnswers):
            asking = signin.PasswordSignIn(email=victim, password=NEW_PASSWORD, org=theirs.slug)
            await signin.sign_in_with_password(session, asking)
        kept = signin.PasswordSignIn(email=victim, password=A_PASSWORD, org=theirs.slug)
        assert (await signin.sign_in_with_password(session, kept)).secret


@needs_the_services
async def test_a_manager_neither_sets_nor_resets_an_admins_password(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Whoever sets a password signs in as that person, so a key sets only what it could grant."""
    email = f"manager@{tenant.slug}.test"
    async with sessions.begin() as session:
        link = await members.invite(session, tenant.org, members.Invitee(email, "A manager", Role.manager), seats=None)
    async with sessions.begin() as session:
        seated = await members.accept_link(session, link.token, A_PASSWORD, 8)
        assert seated is not None
        _, secret = await keys.issue_person_key(session, seated, label="the suite")
    manager = {"authorization": f"Bearer {secret}", "pinecall-env": "sandbox"}
    typed = await gateway.http.put(
        f"/v1/members/{tenant.member}/password", json={"password": NEW_PASSWORD}, headers=manager
    )
    assert typed.status_code == 403, typed.text
    reset = await gateway.http.post(f"/v1/members/{tenant.member}/reset", headers=manager)
    assert reset.status_code == 403, reset.text
    own = await gateway.http.put(f"/v1/members/{seated.id}/password", json={"password": NEW_PASSWORD}, headers=manager)
    assert own.status_code == 200, own.text


@needs_the_services
async def test_a_reset_ends_the_keys_the_old_password_opened(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A key minted before the reset is refused after it; the reset's own key opens."""
    before = await gateway.http.get("/v1/members", headers=tenant.person)
    assert before.status_code == 200, before.text
    async with sessions.begin() as session:
        link = await members.reset_link(session, tenant.org, tenant.member)
        assert link is not None
    accepted = await gateway.http.post(f"/v1/invitations/{link.token}", json={"password": NEW_PASSWORD})
    assert accepted.status_code == 200, accepted.text
    after = await gateway.http.get("/v1/members", headers=tenant.person)
    assert after.status_code == 401, after.text
    fresh = {"authorization": f"Bearer {accepted.json()['key']}", "pinecall-env": "sandbox"}
    assert (await gateway.http.get("/v1/members", headers=fresh)).status_code == 200


# ── the phone a person tests from ──


@needs_the_database
async def test_a_phone_is_one_persons_on_the_whole_box_and_the_newest_to_say_so_has_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    phone = "+34600000000"
    other = await make_tenant(sessions)
    async with sessions.begin() as session:
        await members.set_test_phone(session, tenant.org, tenant.member, phone, None)
        whose = await members.whose_test_phone(session, phone)
        assert whose is not None and whose.id == tenant.member
        await members.set_test_phone(session, other.org, other.member, phone, "front")
    async with sessions() as session:
        whose = await members.whose_test_phone(session, phone)
        assert whose is not None and (whose.org, whose.test_agent) == (other.org, "front")
        assert (await members.get_member(session, tenant.org, tenant.member)).test_phone is None
        assert [m.id for m in await members.test_phones(session) if m.test_phone == phone] == [other.member]
    async with sessions.begin() as session:
        assert await members.forget_test_phone(session, other.org, other.member) == phone
        assert await members.forget_test_phone(session, other.org, other.member) is None
        assert await members.whose_test_phone(session, phone) is None
