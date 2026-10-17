"""A member's password set with no link: by the service, through the admin's door, and refused where it must be."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import members, signin
from pinecall_runtime.enums import MemberStatus, Role
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from tests.conftest import Gateway, Tenant, needs_the_database, needs_the_services

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
