"""A member's password set with no link: by the service, through the admin's door, and refused where it must be."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import actor, invitations, keys, members
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Actor
from runtime.enums import Env, MemberStatus, Role
from runtime.exceptions import Conflict, NotFound, ValidationError
from runtime.signin.service.passwords import NobodyAnswers, PasswordSignIn, PasswordThrottle, sign_in_with_password
from tests.conftest import A_PASSWORD, Gateway, Tenant, make_tenant, needs_the_database, needs_the_services

NEW_PASSWORD = "a-new-password-of-ours"


async def signed_in(sessions: async_sessionmaker[AsyncSession], asking: PasswordSignIn) -> str:
    """The secret of the key a password opens, asked from a place of the test's own."""
    async with sessions.begin() as session:
        issued = await sign_in_with_password(session, PasswordThrottle(sessions), asking, client="the suite")
    return issued.secret


async def the_admin(session: AsyncSession, tenant: Tenant) -> Actor:
    """The tenant's admin, as their key acts in the sandbox."""
    verified = await actor.verify_key(session, tenant.person_key)
    assert verified is not None
    return actor.actor_of(verified, Env.sandbox)


@needs_the_database
async def test_an_invited_person_given_a_password_is_active_and_signs_in_with_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """No link opened: the password set makes them active, and it opens a key."""
    email = f"invited@{tenant.slug}.test"
    async with sessions.begin() as session:
        await invitations.invite(
            session, tenant.org, invitations.Invitee(email, "Invited", Role.qa), held_to_seats=False
        )
        found = await members.get_member_by_email(session, tenant.org, email)
        assert found.status is MemberStatus.invited
        await members.set_password(session, found, NEW_PASSWORD, 8)
    async with sessions() as session:
        assert (await members.get_member_by_email(session, tenant.org, email)).status is MemberStatus.active
    assert await signed_in(sessions, PasswordSignIn(email=email, password=NEW_PASSWORD))


@needs_the_database
async def test_a_short_password_a_disabled_member_and_an_unknown_address_are_refused(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """The box's floor holds; a disabled member is enabled first; an address nobody has is named."""
    email = f"gone@{tenant.slug}.test"
    async with sessions.begin() as session:
        await invitations.invite(session, tenant.org, invitations.Invitee(email, "Gone", Role.qa), held_to_seats=False)
        found = await members.get_member_by_email(session, tenant.org, email)
        with pytest.raises(ValidationError):
            await members.set_password(session, found, "short", 8)
        await members.update_member(session, key_cache, found, members.Change(status=MemberStatus.disabled))
    async with sessions.begin() as session:
        disabled = await members.get_member_by_email(session, tenant.org, email)
        with pytest.raises(Conflict, match="enable them before setting their password"):
            await members.set_password(session, disabled, NEW_PASSWORD, 8)
        with pytest.raises(NotFound, match=f"nobody with the address nobody@{tenant.slug}.test"):
            await members.get_member_by_email(session, tenant.org, f"nobody@{tenant.slug}.test")


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
        invitee = invitations.Invitee(victim, "Not ours", Role.qa)
        await invitations.invite(session, tenant.org, invitee, held_to_seats=False)
        planted = await members.get_member_by_email(session, tenant.org, victim)
        with pytest.raises(Conflict, match="send them a reset"):
            await members.set_password_as_admin(session, await the_admin(session, tenant), planted, NEW_PASSWORD, 8)
        assert planted.status is MemberStatus.invited
    with pytest.raises(NobodyAnswers):
        await signed_in(sessions, PasswordSignIn(email=victim, password=NEW_PASSWORD, org=theirs.slug))
    assert await signed_in(sessions, PasswordSignIn(email=victim, password=A_PASSWORD, org=theirs.slug))


@needs_the_services
async def test_a_manager_neither_sets_nor_resets_an_admins_password(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """Whoever sets a password signs in as that person, so a key sets only what it could grant."""
    email = f"manager@{tenant.slug}.test"
    async with sessions.begin() as session:
        invitee = invitations.Invitee(email, "A manager", Role.manager)
        link = await invitations.invite(session, tenant.org, invitee, held_to_seats=False)
    async with sessions.begin() as session:
        seated = await invitations.accept_link(session, key_cache, link.token, A_PASSWORD, 8)
        assert seated is not None
        secret = (await keys.issue_person_key(session, seated.member, label="the suite")).secret
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
        link = await invitations.reset_link(session, await members.get_member(session, tenant.org, tenant.member))
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
        whose = await members.find_member_by_test_phone(session, phone)
        assert whose is not None and whose.id == tenant.member
        await members.set_test_phone(session, other.org, other.member, phone, "front")
    async with sessions() as session:
        whose = await members.find_member_by_test_phone(session, phone)
        assert whose is not None and (whose.org, whose.test_agent) == (other.org, "front")
        assert (await members.get_member(session, tenant.org, tenant.member)).member.test_phone is None
        assert [m.id for m in await members.list_test_phones(session) if m.test_phone == phone] == [other.member]
    async with sessions.begin() as session:
        assert await members.forget_test_phone(session, other.org, other.member) == phone
        assert await members.forget_test_phone(session, other.org, other.member) is None
        assert await members.find_member_by_test_phone(session, phone) is None
