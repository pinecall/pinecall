"""Invitations: a person invited within the org's seats, the link mailed or handed over, and a link accepted."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts.models import Invitation, InvitationPurpose, Member, Org, Person
from runtime.accounts.repository.invitations import InvitationRepository
from runtime.accounts.repository.members import MemberRepository, Membership
from runtime.accounts.repository.orgs import OrgRepository
from runtime.accounts.service import emails, keys, members, passwords, people
from runtime.accounts.service.actor import check_may_grant
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Actor
from runtime.billing import service as billing
from runtime.enums import MemberStatus, Role
from runtime.exceptions import Conflict, NotFound, Unauthorized
from runtime.kit.crypto import fingerprint, random_id, random_token
from runtime.kit.time import now
from runtime.mail import service as mail
from runtime.platform import service as platform

MEMBER_PREFIX = "m_"
# Stored as a sha256 like a key, but it dies in a week: a mailed link gets forwarded.
INVITATION_PREFIX = "inv_"
INVITATION_TTL = timedelta(days=7)
# Who an email says invited, when a key with no person did, and when the operator did.
AN_ADMIN = "An admin"
THE_OPERATOR = "The operator"
# What a first key is written under when the device did not say what it is.
BY_INVITATION = "invitation"


class AlreadyAMember(Conflict):
    """The address accepted already."""

    def __init__(self, email: str) -> None:
        super().__init__(f"{email} is a member of this org already: they sign in, nobody invites them")


class NotActive(Conflict):
    """Only an active member's password is reset."""

    def __init__(self, email: str, status: MemberStatus) -> None:
        super().__init__(
            f"{email} is {status}, not active: an invited member uses their invitation, "
            "and a disabled one is enabled before their password is reset"
        )


class NoSuchInvitation(NotFound):
    """The token opens no link: one opens once, and dies in a week."""

    def __init__(self) -> None:
        super().__init__("no open invitation answers to that token: it was used, it expired, or it never existed")


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
class Link:
    """A link minted: the member, the token once, and when it dies."""

    membership: Membership
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class Handover:
    """An invitation or a reset on its way: the member, whether a mailbox takes it, the link if the caller holds it."""

    member: Membership
    expires_at: datetime
    mailed: bool
    # The token and its card, once; None when the link goes to the person's mailbox and nowhere else.
    token: str | None
    link: str | None


@dataclass(frozen=True, slots=True)
class FirstKey(keys.Issued):
    """A link accepted: the member now active, and their first key."""

    member: Membership


async def invite(
    session: AsyncSession, org: str, invitee: Invitee, *, vouched: bool = False, held_to_seats: bool = True
) -> Link:
    """Invite a person, or give a link again to one still invited; within the org's seats unless the box seats them."""
    person = await people.find_or_create_person(session, invitee.email)
    return await _invite(session, org, person, invitee, vouched=vouched, held_to_seats=held_to_seats)


# The token is handed to the admin only when the person is the org's own: an address nobody proved,
# with no seat elsewhere. Otherwise it is mailed only, by the box's own mailbox, and opening it
# proves the address; the link seats the person with the password they have.
async def invite_as_admin(
    session: AsyncSession, actor: Actor, invitee: Invitee, *, outbox: mail.Outbox, base: str
) -> Handover:
    """Invite a person into the actor's org, within its seats, and mail them the link."""
    check_may_grant(actor, invitee.role, production=invitee.production)
    person = await people.find_or_create_person(session, invitee.email)
    own = await people.is_the_orgs_own(session, person, actor.org)
    link = await _invite(session, actor.org, person, invitee, vouched=not own, held_to_seats=True)
    org = await OrgRepository(session).find(actor.org)
    details = _details_of(link, actor.org if org is None else org.name, actor.name or AN_ADMIN, base)
    email = emails.invitation_email(link.membership.email, details, await platform.get_brand(session))
    return await _hand_over(session, outbox, link, email, details.link, through=actor.org if own else None, held=own)


# Takes no seat of the org's plan: this is how an org gets its first admin with sign-up shut. The
# token is answered this once; the email goes too when the box can mail.
async def invite_as_operator(
    session: AsyncSession, org: Org, invitee: Invitee, *, outbox: mail.Outbox, base: str
) -> Handover:
    """Invite a person into any org at the operator's word, the link's token once."""
    link = await invite(session, org.id, invitee, vouched=True, held_to_seats=False)
    details = _details_of(link, org.name, THE_OPERATOR, base)
    email = emails.invitation_email(link.membership.email, details, await platform.get_brand(session))
    return await _hand_over(session, outbox, link, email, details.link, through=None, held=True)


async def reset_link(session: AsyncSession, membership: Membership, *, vouched: bool = False) -> Link | None:
    """A link that sets an active member's password again; None for anybody else."""
    if membership.status is not MemberStatus.active:
        return None
    await InvitationRepository(session).spend_open_of(membership.id)
    return await _mint_link(session, membership, vouched=vouched, purpose=InvitationPurpose.reset)


# Whoever holds a reset's link chooses the password, so the link follows the rule of a password
# typed: handed to the caller for a person who is the org's own, mailed to the person and nobody
# else for anybody whose password is theirs; and a key resets only for a role it could grant.
async def reset_as_admin(
    session: AsyncSession, actor: Actor, membership: Membership, *, outbox: mail.Outbox, base: str
) -> Handover:
    """A one-time link that sets an active member's password, mailed to them."""
    check_may_grant(actor, membership.role, production=False)
    own = await people.is_the_orgs_own(session, membership.person, actor.org)
    link = await reset_link(session, membership, vouched=not own)
    if link is None:
        raise NotActive(membership.email, membership.status)
    org = await OrgRepository(session).find(actor.org)
    details = _details_of(link, actor.org if org is None else org.name, actor.name or AN_ADMIN, base)
    email = emails.reset_email(membership.email, details, await platform.get_brand(session))
    return await _hand_over(session, outbox, link, email, details.link, through=actor.org if own else None, held=own)


# A link the person's mailbox alone received proves the address, so it is weighed first: it clears a
# password somebody set while the address was unproven, unless the one typed is that password. An
# invitation never replaces a password the person keeps: they type the one they have, and it is
# compared before the box's floor is asked of it, since a floor raised later is not theirs to meet.
async def accept_link(
    session: AsyncSession, cache: KeyCache, token: str, password: str, shortest: int
) -> Membership | None:
    """Spend the link and seat or reset the member as its purpose says; None for a dead link."""
    spent = await InvitationRepository(session).spend(fingerprint(token))
    if spent is None:
        return None
    membership = await members.find_membership(session, spent.member)
    if membership is None or membership.status is MemberStatus.disabled:
        return None
    person = membership.person
    if spent.purpose is InvitationPurpose.reset:
        await _reset_password(session, cache, person, spent, await passwords.hash_password(password, shortest))
    else:
        matched = person.password_hash is not None and await people.password_matches(person, password)
        if spent.vouched:
            await people.prove_mailbox(session, cache, person, presented_password=matched)
        if person.password_hash is None:
            await people.set_password(session, person, await passwords.hash_password(password, shortest))
        elif not matched:
            raise TypeTheOneKept()
    await MemberRepository(session).update(membership.member, status=MemberStatus.active)
    return membership


async def accept_invitation(
    session: AsyncSession, cache: KeyCache, token: str, password: str, shortest: int, *, device: str | None = None
) -> FirstKey:
    """Type the password: the member is active, and here is their first key."""
    membership = await accept_link(session, cache, token, password, shortest)
    if membership is None:
        raise NoSuchInvitation()
    issued = await keys.issue_person_key(session, membership.member, label=device or BY_INVITATION)
    return FirstKey(issued.row, issued.secret, membership)


# No link is minted for a founder: the sign-up that makes the org proved the address its own way, and
# says so to `people.prove_mailbox` before it calls here. A password the person keeps is never replaced.
async def seat_founder(session: AsyncSession, org: str, founder: Invitee, hashed: str | None) -> Membership:
    """Seat a new org's first member, active at once, with the password their sign-up chose when they have none."""
    person = await people.find_or_create_person(session, founder.email)
    member = await MemberRepository(session).add(_seat_of(org, person, founder, MemberStatus.active))
    if person.password_hash is None and hashed is not None:
        await people.set_password(session, person, hashed)
    return Membership(member, person)


async def _invite(
    session: AsyncSession, org: str, person: Person, invitee: Invitee, *, vouched: bool, held_to_seats: bool
) -> Link:
    repository = MemberRepository(session)
    # The seat count and the insert go together: two invitations at the last seat are admitted in turn.
    await repository.lock_org(org)
    kept = await repository.find_by_email(org, person.email)
    if kept is not None and kept.status is not MemberStatus.invited:
        raise AlreadyAMember(person.email)
    if kept is not None:
        await InvitationRepository(session).spend_open_of(kept.id)
        return await _mint_link(session, Membership(kept, person), vouched=vouched)
    if held_to_seats:
        await billing.admit_seat(session, org, seated=await repository.count_seated(org))
    member = await repository.add(_seat_of(org, person, invitee, MemberStatus.invited))
    return await _mint_link(session, Membership(member, person), vouched=vouched)


def _seat_of(org: str, person: Person, invitee: Invitee, status: MemberStatus) -> Member:
    return Member(
        id=random_id(MEMBER_PREFIX, 6),
        org=org,
        person=person.id,
        email=person.email,
        name=invitee.name,
        role=invitee.role,
        agents=sorted(invitee.agents),
        status=status,
        production=invitee.production,
    )


async def _mint_link(
    session: AsyncSession,
    membership: Membership,
    *,
    vouched: bool,
    purpose: InvitationPurpose = InvitationPurpose.invite,
) -> Link:
    token = f"{INVITATION_PREFIX}{random_token(24)}"
    expires_at = now() + INVITATION_TTL
    minted = Invitation(
        token_hash=fingerprint(token), member=membership.id, expires_at=expires_at, vouched=vouched, purpose=purpose
    )
    await InvitationRepository(session).add(minted)
    return Link(membership, token, expires_at)


def _details_of(link: Link, org: str, by: str, base: str) -> mail.LinkDetails:
    return mail.LinkDetails(org=org, link=emails.card_link(base, link.token), by=by, dies=link.expires_at)


# The email leaves once the link's row is committed, never before: a commit that failed left a link
# mailed to a row that did not exist. A link vouched for went to no mailbox but the person's, through
# the box's own; the caller holds the token only when it did not, or when the operator sent it.
async def _hand_over(
    session: AsyncSession,
    outbox: mail.Outbox,
    link: Link,
    email: mail.Email,
    card: str,
    *,
    through: str | None,
    held: bool,
) -> Handover:
    return Handover(
        member=link.membership,
        expires_at=link.expires_at,
        mailed=await outbox.post_after_commit(session, through, email),
        token=link.token if held else None,
        link=card if held else None,
    )


# A reset mailed to the address and nobody else proves it. Either way it ends whatever the old
# password opened, in every org of the person: a key minted with it would outlive it otherwise.
async def _reset_password(
    session: AsyncSession, cache: KeyCache, person: Person, spent: Invitation, hashed: str
) -> None:
    if spent.vouched:
        await people.prove_mailbox(session, cache, person, presented_password=False)
    await people.set_password(session, person, hashed)
    await keys.revoke_person_keys(session, cache, person)
