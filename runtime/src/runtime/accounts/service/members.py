"""Members: an org's people read, changed, removed, their password typed for them, the phone they test from."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts.models import Member
from runtime.accounts.repository.invitations import InvitationRepository
from runtime.accounts.repository.members import MemberRepository, Membership
from runtime.accounts.service import keys, passwords, people
from runtime.accounts.service.actor import check_may_grant
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Actor
from runtime.enums import MemberStatus, Role
from runtime.exceptions import Conflict, NotFound, ValidationError
from runtime.scoping import box_wide


class NoSuchMember(NotFound):
    """Nobody by that id in this org."""

    def __init__(self) -> None:
        super().__init__("nobody by that id in this org")


class LastAdmin(Conflict):
    """The org keeps one active admin."""

    def __init__(self) -> None:
        super().__init__("the org keeps one active admin: make another one admin first")


@dataclass(frozen=True, slots=True)
class Change:
    """What a PATCH names; None keeps what the member has."""

    role: Role | None = None
    agents: frozenset[str] | None = None
    status: MemberStatus | None = None
    production: bool | None = None


@dataclass(frozen=True, slots=True)
class Team:
    """An org's people, oldest first, and how many of them hold a seat."""

    members: Sequence[Membership]
    seated: int


async def get_member(session: AsyncSession, org: str, member_id: str) -> Membership:
    """By id within the org; NotFound otherwise."""
    found = await MemberRepository(session).find_membership_in(org, member_id)
    if found is None:
        raise NoSuchMember()
    return found


async def get_member_by_email(session: AsyncSession, org: str, email: str) -> Membership:
    """The org's member with that address; NotFound naming it otherwise."""
    found = await MemberRepository(session).find_membership_by_email(org, email)
    if found is None:
        raise NotFound(f"nobody with the address {email} in this org")
    return found


async def find_membership(session: AsyncSession, member_id: str) -> Membership | None:
    """The member and their person by the member's id, in whatever org; None when the seat is gone."""
    with box_wide():
        return await MemberRepository(session).find_membership(member_id)


async def list_members(session: AsyncSession, org: str) -> Sequence[Membership]:
    """The org's people, oldest first, the disabled ones too."""
    return await MemberRepository(session).list_memberships(org)


async def team_of(session: AsyncSession, org: str) -> Team:
    """The org's people, oldest first, and how many hold a seat."""
    repository = MemberRepository(session)
    return Team(await repository.list_memberships(org), await repository.count_seated(org))


async def count_seated(session: AsyncSession, org: str) -> int:
    """How many of the org's people hold a seat: the seats quota counts these."""
    return await MemberRepository(session).count_seated(org)


async def list_admin_addresses(session: AsyncSession, org: str) -> list[str]:
    """The addresses of the org's admins who may sign in: who an alert of the org is mailed to."""
    return sorted({member.email for member in await MemberRepository(session).list_active_admins(org)})


async def update_member(session: AsyncSession, cache: KeyCache, membership: Membership, change: Change) -> Membership:
    """Change what was named; disabling revokes the member's keys, and every gateway asks their key again."""
    values = {
        name: value
        for name, value in (
            ("role", change.role),
            ("agents", None if change.agents is None else sorted(change.agents)),
            ("status", change.status),
            ("production", change.production),
        )
        if value is not None
    }
    await MemberRepository(session).update(membership.member, **values)
    if change.status is MemberStatus.disabled:
        await keys.revoke_member_keys(session, cache, membership.id)
    else:
        cache.forget_after_commit(session, subject=membership.id)
    return membership


async def change_member(
    session: AsyncSession, cache: KeyCache, actor: Actor, membership: Membership, change: Change
) -> Membership:
    """Change a colleague's role, agents, standing or production access, as far as the actor's key may."""
    member = membership.member
    if change.status is MemberStatus.active and member.status is MemberStatus.invited:
        raise ValidationError(
            f"{membership.email} has not accepted their invitation: they become active by accepting it"
        )
    yours = actor.person is not None and actor.person.id == member.id
    if change.status is MemberStatus.disabled and yours:
        raise Conflict("you cannot disable yourself: another admin of this org disables you")
    if yours and (change.role is not None or change.production is not None):
        raise Conflict("nobody changes their own role or production access: another admin does")
    check_may_grant(actor, change.role, production=bool(change.production))
    if change.production is False and (change.role or member.role) is Role.admin:
        raise Conflict(f"{membership.email} is an admin, and an admin always opens production")
    return await update_member(session, cache, membership, change)


async def remove_member(session: AsyncSession, cache: KeyCache, membership: Membership) -> None:
    """Take a member out for good, keys revoked first; never the last active admin."""
    member = membership.member
    repository = MemberRepository(session)
    an_admin = member.role is Role.admin and member.status is MemberStatus.active
    if an_admin and await repository.count_other_active_admins(member.org, member.id) == 0:
        raise LastAdmin()
    await keys.revoke_member_keys(session, cache, member.id)
    await repository.delete(member)
    await people.delete_if_orphan(session, membership.person)


# The operator's removal is this less "not yourself": the last active admin still stays.
async def remove_colleague(session: AsyncSession, cache: KeyCache, actor: Actor, membership: Membership) -> None:
    """Take a colleague out of the actor's org for good; never yourself, never the last admin."""
    if actor.person is not None and actor.person.id == membership.id:
        raise Conflict("you cannot remove yourself: another admin of this org removes you")
    await remove_member(session, cache, membership)


# A password typed for a person by the box's operator, or by `setup` for the machine's owner: no link
# is mailed, and an invited person becomes active by it, as accepting would. An org's admin types one
# through `set_password_as_admin`, which asks first whether it is theirs to type.
async def set_password(session: AsyncSession, membership: Membership, password: str, shortest: int) -> Membership:
    """A member's password set; an invited member made active, a disabled one refused."""
    if membership.status is MemberStatus.disabled:
        raise Conflict(f"{membership.email} is disabled: enable them before setting their password")
    hashed = await passwords.hash_password(password, shortest)
    await InvitationRepository(session).spend_open_of(membership.id)
    await people.set_password(session, membership.person, hashed)
    await MemberRepository(session).update(membership.member, status=MemberStatus.active)
    return membership


async def set_password_as_admin(
    session: AsyncSession, actor: Actor, membership: Membership, password: str, shortest: int
) -> Membership:
    """A password an org's admin types for one of its own people; refused for anybody whose password is their own."""
    await people.check_may_set_password(session, actor, membership)
    return await set_password(session, membership, password, shortest)


async def set_operator(session: AsyncSession, cache: KeyCache, membership: Membership, *, on: bool) -> Membership:
    """Make a member's person one who runs the box, or take it back."""
    await people.set_operator(session, cache, membership.person, on=on)
    return membership


# Signing in to an org one was invited to is taking the seat. Whoever calls has checked whose
# password it was: only a person whose address is proven joins with the password they have.
async def take_seat(session: AsyncSession, membership: Membership) -> Membership | None:
    """Seat an invited member who signed in with the password they already have; None for anybody else."""
    if membership.status is not MemberStatus.invited:
        return None
    await MemberRepository(session).update(membership.member, status=MemberStatus.active)
    return membership


# The provider proved the address without the password: what was set while it was unproven ends here.
async def seat_vouched(session: AsyncSession, cache: KeyCache, membership: Membership) -> Membership | None:
    """Seat a member an identity provider vouched for, their address proven; never a disabled one."""
    if membership.status is MemberStatus.disabled:
        return None
    await people.prove_mailbox(session, cache, membership.person, presented_password=False)
    await MemberRepository(session).update(membership.member, status=MemberStatus.active)
    return membership


# ── the phone a person tests from ──


async def set_test_phone(session: AsyncSession, org: str, member_id: str, phone: str, agent: str | None) -> Member:
    """This phone is the member's own from now on, and nobody else's; a call from it reaches the agent named."""
    repository = MemberRepository(session)
    member = await repository.find(org, member_id)
    if member is None:
        raise NoSuchMember()
    with box_wide():
        await repository.release_test_phone(phone)
    await repository.update(member, test_phone=phone, test_agent=agent)
    return member


async def forget_test_phone(session: AsyncSession, org: str, member_id: str) -> str | None:
    """The member's phone is nobody's again; the phone forgotten, or None when there was none."""
    repository = MemberRepository(session)
    member = await repository.find(org, member_id)
    if member is None:
        raise NoSuchMember()
    forgotten = member.test_phone
    await repository.update(member, test_phone=None, test_agent=None)
    return forgotten


async def find_member_by_test_phone(session: AsyncSession, phone: str) -> Member | None:
    """The one member on the box whose phone this is, or None."""
    with box_wide():
        return await MemberRepository(session).find_by_test_phone(phone)


async def list_test_phones(session: AsyncSession) -> Sequence[Member]:
    """Everyone on the box who said which phone is theirs: what a gateway starting remembers."""
    with box_wide():
        return await MemberRepository(session).list_with_test_phones()
