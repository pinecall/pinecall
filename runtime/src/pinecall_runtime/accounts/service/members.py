"""Members: invited within the org's seats, seated by a link, changed, reset, removed."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.models import Invitation, Member
from pinecall_runtime.accounts.repository import (
    ApiKeyRepository,
    InvitationRepository,
    MemberRepository,
)
from pinecall_runtime.enums import InvitationPurpose, MemberStatus, Role
from pinecall_runtime.exceptions import (
    Conflict,
    NotFound,
    QuotaExceeded,
    Unauthorized,
    ValidationError,
)
from pinecall_runtime.kit.crypto import (
    fingerprint,
    hash_password,
    random_id,
    random_token,
    verify_password,
)
from pinecall_runtime.kit.text import parse_email
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide

ID_PREFIX = "m_"
# Stored as a sha256 like a key, but it dies in a week: a mailed link gets forwarded.
INVITATION_PREFIX = "inv_"
INVITATION_TTL = timedelta(days=7)


# Verified when the address is nobody's, so the time taken does not say who is a member. Hashed
# on first use, not at import: argon2 costs tens of milliseconds.
@cache
def _nobodys_hash() -> str:
    return hash_password(random_token(32))


class NoSuchMember(NotFound):
    """Nobody by that id in this org."""

    def __init__(self) -> None:
        super().__init__("nobody by that id in this org")


class AlreadyAMember(Conflict):
    """The address accepted already."""

    def __init__(self, email: str) -> None:
        super().__init__(f"{email} is a member of this org already: they sign in, nobody invites them")


class NoSeatLeft(QuotaExceeded):
    """The org holds all of its seats."""

    def __init__(self, seated: int, limit: int) -> None:
        super().__init__(
            f"the org holds all {seated} of its seats: free one, or ask for more",
            quota="seats",
            used=seated,
            limit=limit,
        )


class LastAdmin(Conflict):
    """The org keeps one active admin."""

    def __init__(self) -> None:
        super().__init__("the org keeps one active admin: make another one admin first")


class PasswordTooShort(ValidationError):
    """Under the box's floor."""

    def __init__(self, shortest: int) -> None:
        super().__init__(f"a password is at least {shortest} characters")


class TypeTheOneKept(Unauthorized):
    """An invitation seats a person; the password they have is theirs to keep and to type."""

    def __init__(self) -> None:
        super().__init__(
            "this address has a password already, and that is not it: accept with the password "
            "you have, or reset it from the sign-in page first"
        )


@dataclass(frozen=True, slots=True)
class Invitee:
    """Who is invited, and what they are given."""

    email: str
    name: str
    role: Role
    agents: frozenset[str] = frozenset()
    production: bool = False


@dataclass(frozen=True, slots=True)
class Change:
    """What a PATCH names; None keeps what the member has."""

    role: Role | None = None
    agents: frozenset[str] | None = None
    status: MemberStatus | None = None
    production: bool | None = None


@dataclass(frozen=True, slots=True)
class Link:
    """A link minted: the member, the token once, and when it dies."""

    member: Member
    token: str
    expires_at: datetime


def check_password(password: str, shortest: int) -> None:
    """Refuse a password under the box's floor, before anything is hashed or spent on it."""
    if len(password) < shortest:
        raise PasswordTooShort(shortest)


# argon2id costs tens of milliseconds and 64 MiB: off the event loop.
async def hashed_password(password: str, shortest: int) -> str:
    """The password hashed; refused before hashing when under the floor."""
    check_password(password, shortest)
    return await asyncio.to_thread(hash_password, password)


async def password_matches(password: str, kept: str | None) -> bool:
    """Whether the password is the one kept; nobody's costs a verification all the same."""
    return await asyncio.to_thread(verify_password, kept or _nobodys_hash(), password) and kept is not None


async def invite(
    session: AsyncSession, org: str, invitee: Invitee, *, seats: int | None, vouched: bool = False
) -> Link:
    """Invite a person, or give a link again to one still invited; within the org's seats."""
    members = MemberRepository(session)
    email = parse_email(invitee.email)
    with box_wide():
        proven = await members.is_verified_anywhere(email)
    await members.lock_org(org)
    kept = await members.get_by_email(org, email)
    if kept is not None and kept.status is not MemberStatus.invited:
        raise AlreadyAMember(email)
    if kept is not None:
        await InvitationRepository(session).spend_open_of(kept.id)
        return await _link(session, kept, vouched=vouched)
    seated = await members.count_seated(org)
    if seats is not None and seated >= seats:
        raise NoSeatLeft(seated, seats)
    member = Member(
        id=random_id(ID_PREFIX, 6),
        org=org,
        email=email,
        name=invitee.name,
        role=invitee.role,
        agents=sorted(invitee.agents),
        status=MemberStatus.invited,
        production=invitee.production,
        verified_at=now() if proven else None,
    )
    await members.add(member)
    return await _link(session, member, vouched=vouched)


# A reset mailed to the address (vouched) sets the person's one password everywhere; a reset handed
# to an admin sets this row's alone. An invitation never sets a password the person has.
async def accept_link(session: AsyncSession, token: str, password: str, shortest: int) -> Member | None:
    """Spend the link and seat or reset the member as its purpose says; None for a dead link."""
    members = MemberRepository(session)
    spent = await InvitationRepository(session).spend(fingerprint(token))
    if spent is None:
        return None
    member = await members.get_by_id(spent.member)
    if member is None:
        return None
    with box_wide():
        kept = await members.password_hash_of(member.email)
    if spent.purpose is InvitationPurpose.reset:
        hashed = await hashed_password(password, shortest)
        if spent.vouched:
            with box_wide():
                await members.set_password_everywhere(member.email, hashed)
        return await _activate(members, member, spent, hashed)
    if kept is None:
        return await _activate(members, member, spent, await hashed_password(password, shortest))
    if not await password_matches(password, kept):
        raise TypeTheOneKept()
    return await _activate(members, member, spent, None)


async def seat_founder(session: AsyncSession, token: str, hashed: str) -> Member | None:
    """Spend a sign-up's link and seat the org's first admin with the password the sign-up proved."""
    members = MemberRepository(session)
    spent = await InvitationRepository(session).spend(fingerprint(token))
    if spent is None:
        return None
    member = await members.get_by_id(spent.member)
    if member is None:
        return None
    with box_wide():
        kept = await members.password_hash_of(member.email)
    return await _activate(members, member, spent, None if kept is not None else hashed)


async def reset_link(session: AsyncSession, org: str, member_id: str, *, vouched: bool = False) -> Link | None:
    """A link that sets an active member's password again; None for anybody else."""
    found = await MemberRepository(session).get(org, member_id)
    if found is None or found.status is not MemberStatus.active:
        return None
    await InvitationRepository(session).spend_open_of(member_id)
    return await _link(session, found, vouched=vouched, purpose=InvitationPurpose.reset)


# A password typed for a person by an admin, by the operator, or by `setup` for the machine's
# owner: no link is mailed, and an invited person becomes active by it, as accepting would.
async def set_password(session: AsyncSession, org: str, member_id: str, password: str, shortest: int) -> Member:
    """A member's password set; an invited member made active, a disabled one refused."""
    members = MemberRepository(session)
    found = await members.get(org, member_id)
    if found is None:
        raise NoSuchMember()
    if found.status is MemberStatus.disabled:
        raise Conflict(f"{found.email} is disabled: enable them before setting their password")
    hashed = await hashed_password(password, shortest)
    await InvitationRepository(session).spend_open_of(member_id)
    await members.update(found, password_hash=hashed, status=MemberStatus.active)
    return found


async def member_by_email(session: AsyncSession, org: str, email: str) -> Member:
    """The org's member with that address; NotFound naming it otherwise."""
    found = await MemberRepository(session).get_by_email(org, parse_email(email))
    if found is None:
        raise NotFound(f"nobody with the address {email} in this org")
    return found


async def update_member(session: AsyncSession, org: str, member_id: str, change: Change) -> Member:
    """Change what was named; disabling revokes the member's keys."""
    members = MemberRepository(session)
    member = await members.get(org, member_id)
    if member is None:
        raise NoSuchMember()
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
    await members.update(member, **values)
    if change.status is MemberStatus.disabled:
        await ApiKeyRepository(session).revoke_of_person(member_id)
    return member


async def remove_member(session: AsyncSession, org: str, member_id: str) -> None:
    """Take a member out for good, keys revoked first; never the last active admin."""
    members = MemberRepository(session)
    member = await members.get(org, member_id)
    if member is None:
        raise NoSuchMember()
    an_admin = member.role is Role.admin and member.status is MemberStatus.active
    if an_admin and await members.count_other_active_admins(org, member_id) == 0:
        raise LastAdmin()
    await ApiKeyRepository(session).revoke_of_person(member_id)
    await members.delete(member)


async def admins_of(session: AsyncSession, org: str) -> list[str]:
    """The addresses of the org's admins who may sign in: who an alert of the org is mailed to."""
    return sorted({member.email for member in await MemberRepository(session).active_admins(org)})


async def operators_of_the_box(session: AsyncSession) -> list[str]:
    """The addresses of the box's operators who may sign in: who every org's alerts are mailed to."""
    with box_wide():
        return sorted({member.email for member in await MemberRepository(session).active_operators()})


async def list_members(session: AsyncSession, org: str) -> Sequence[Member]:
    """The org's people, oldest first, the disabled ones too."""
    return await MemberRepository(session).list_of_org(org)


async def seats_taken(session: AsyncSession, org: str) -> int:
    """How many of the org's people hold a seat: the seats quota counts these."""
    return await MemberRepository(session).count_seated(org)


async def get_member(session: AsyncSession, org: str, member_id: str) -> Member:
    """By id within the org; NotFound otherwise."""
    member = await MemberRepository(session).get(org, member_id)
    if member is None:
        raise NoSuchMember()
    return member


async def memberships_of(session: AsyncSession, email: str) -> Sequence[Member]:
    """Every membership of the address, oldest first, across orgs."""
    with box_wide():
        return await MemberRepository(session).list_of_person(parse_email(email))


async def password_hash_of(session: AsyncSession, email: str) -> str | None:
    """The person's one password hash, across orgs."""
    with box_wide():
        return await MemberRepository(session).password_hash_of(parse_email(email))


async def is_member_elsewhere(session: AsyncSession, org: str, email: str) -> bool:
    """Whether the address is a member of another org on this box."""
    return any(row.org != org for row in await memberships_of(session, email))


async def join_with_password(session: AsyncSession, member: Member, password_hash: str) -> Member | None:
    """Seat an invited member who signs in with the password they already have."""
    if member.status is not MemberStatus.invited:
        return None
    await MemberRepository(session).update(member, status=MemberStatus.active, password_hash=password_hash)
    return member


async def seat_vouched(session: AsyncSession, member: Member) -> Member | None:
    """Seat a member an identity provider vouched for; never a disabled one."""
    if member.status is MemberStatus.disabled:
        return None
    values: dict[str, object] = {"status": MemberStatus.active}
    if member.verified_at is None:
        values["verified_at"] = now()
    await MemberRepository(session).update(member, **values)
    return member


async def set_operator(session: AsyncSession, org: str, member_id: str, *, on: bool) -> Member:
    """Make a member one who runs the box, or take it back."""
    member = await get_member(session, org, member_id)
    await MemberRepository(session).update(member, operator=on)
    return member


async def _link(
    session: AsyncSession, member: Member, *, vouched: bool, purpose: InvitationPurpose = InvitationPurpose.invite
) -> Link:
    token = f"{INVITATION_PREFIX}{random_token(24)}"
    expires_at = now() + INVITATION_TTL
    await InvitationRepository(session).add(
        Invitation(
            token_hash=fingerprint(token), member=member.id, expires_at=expires_at, vouched=vouched, purpose=purpose
        )
    )
    return Link(member=member, token=token, expires_at=expires_at)


async def _activate(members: MemberRepository, member: Member, spent: Invitation, hashed: str | None) -> Member | None:
    if member.status is MemberStatus.disabled:
        return None
    values: dict[str, object] = {"status": MemberStatus.active}
    if hashed is not None:
        values["password_hash"] = hashed
    if spent.vouched and member.verified_at is None:
        values["verified_at"] = now()
    await members.update(member, **values)
    return member
