"""A member's password set with no link: by the service, through the admin's door, and refused where it must be."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import members, signin
from pinecall_runtime.enums import MemberStatus, Role
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from tests.conftest import Gateway, Tenant, make_tenant, needs_the_database, needs_the_services

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
