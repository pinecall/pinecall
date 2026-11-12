"""Login codes: the one-time code that signs a browser in, a key for another device, and a key into another org."""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.accounts.models import ApiKey
from runtime.actor import Actor, Person
from runtime.enums import KEY_SCOPES, Env, KeyScope, MemberStatus
from runtime.exceptions import Forbidden, NotFound
from runtime.kit.crypto import Vault
from runtime.kit.time import epoch
from runtime.scoping import box_wide
from runtime.signin.repository import SsoRepository
from runtime.signin.service.one_time import Kind, Minted, OneTimeSecrets

# A browser signs in with a code, never a key in the URL.
LOGIN_CODE = Kind("lc_", 300.0)
A_BROWSER = "console"
# The role an org shows for somebody who runs the box and has no seat in it.
VISITING = "operator"


class NoSuchCode(NotFound):
    """The code opens nothing: one opens once, and dies in five minutes."""

    def __init__(self) -> None:
        super().__init__("no code answers to that: it was used, it expired, or it never existed")


class NotAPersons(Forbidden):
    """A server's token names nobody."""

    def __init__(self) -> None:
        super().__init__("a server's token names nobody: a person's key signs another device in")


class NotTheirOrg(Forbidden):
    """The org is not one of the person's."""

    def __init__(self, org: str) -> None:
        super().__init__(f"{org} is not an org of this person's")


# Until 2026-11-11 a key switched into any org its address had a seat in. A seat somebody else made
# for an address, with a key of their own, then opened every org the address's owner joined later.
class MailboxUnproven(Forbidden):
    """A key of an address nobody proved opens the org it was minted in and no other."""

    def __init__(self, email: str) -> None:
        super().__init__(
            f"{email} was never proven yours on this box, so this key opens its own org alone: reset your "
            "password from the sign-in page, which mails you a link, and sign in again"
        )


@dataclass(frozen=True, slots=True)
class CodeHolder:
    """What a login code gives: a person's key, or a copy of the server key that asked for it."""

    member_id: str | None = None
    key_id: str | None = None
    org: str = ""
    env: Env = Env.production
    scopes: tuple[str, ...] = ()
    label: str | None = None
    subject: str | None = None
    name: str | None = None
    expires_at: float | None = None


def _load_holder(value: Mapping[str, Any]) -> CodeHolder:
    return CodeHolder(
        member_id=value.get("member_id"),
        key_id=value.get("key_id"),
        org=str(value.get("org") or ""),
        env=Env(value.get("env") or Env.production),
        scopes=tuple(str(scope) for scope in value.get("scopes") or ()),
        label=value.get("label"),
        subject=value.get("subject"),
        name=value.get("name"),
        expires_at=value.get("expires_at"),
    )


class LoginCodes(OneTimeSecrets[CodeHolder]):
    """The codes a browser signs in with, each for five minutes."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], vault: Vault, clock: Callable[[], float] = epoch
    ) -> None:
        super().__init__(LOGIN_CODE, sessions, vault, load=_load_holder, dump=asdict, clock=clock)


@dataclass(frozen=True, slots=True)
class OrgOfPerson:
    """One org a person's key may open: their seat in it, or a visit for somebody who runs the box."""

    org: str
    slug: str | None
    name: str | None
    role: str
    status: MemberStatus
    here: bool
    member: bool


def holder_of_member(membership: accounts.Membership) -> CodeHolder:
    """A login code that signs a browser in as this person."""
    return CodeHolder(member_id=membership.id, org=membership.org)


def holder_of_key(key: ApiKey) -> CodeHolder:
    """A login code that gives a copy of this key."""
    return CodeHolder(
        key_id=key.id,
        org=key.org,
        env=key.env,
        scopes=tuple(key.scopes),
        label=key.label,
        subject=key.subject,
        name=key.name,
        expires_at=None if key.expires_at is None else key.expires_at.timestamp(),
    )


async def mint_for_key(session: AsyncSession, codes: LoginCodes, key_id: str) -> Minted:
    """A one-time code that gives a browser a key like the one asking, for five minutes."""
    return await codes.mint_on(session, holder_of_key(await accounts.get_key(session, key_id)))


async def sign_in_with_code(
    session: AsyncSession, codes: LoginCodes, code: str, *, device: str | None = None
) -> accounts.Issued:
    """The key the code was minted for, spent; NoSuchCode for a code dead, spent or nobody's."""
    holder = await codes.spend(code)
    if holder is None:
        raise NoSuchCode()
    label = device or A_BROWSER
    if holder.member_id is not None:
        membership = await accounts.find_membership(session, holder.member_id)
        if membership is None or membership.status is not MemberStatus.active:
            raise NoSuchCode()
        return await accounts.issue_person_key(session, membership.member, label=label)
    expires_at = None if holder.expires_at is None else datetime.fromtimestamp(holder.expires_at, UTC)
    issue = accounts.Issue(
        org=holder.org,
        env=holder.env,
        scopes=frozenset(KeyScope(scope) for scope in holder.scopes),
        label=label,
        subject=holder.subject,
        name=holder.name,
        created_by=holder.subject,
        expires_at=expires_at,
        parent=holder.key_id,
    )
    return await accounts.issue_key(session, issue)


async def another_device_key(session: AsyncSession, actor: Actor, *, device: str | None = None) -> accounts.Issued:
    """The same person's key for another device, never outliving the key that asked."""
    if actor.person is None:
        raise NotAPersons()
    membership = await accounts.find_membership(session, actor.person.id)
    # Somebody who runs the box and is visiting an org has no seat in it to sign a device in to.
    if membership is None or membership.org != actor.org or membership.status is not MemberStatus.active:
        raise Forbidden("the person this key was minted for is no longer an active member of this org")
    parent = await accounts.get_key(session, actor.key_id)
    return await accounts.issue_person_key(session, membership.member, parent=parent, label=device)


# A person of the box is let into any org, as an admin; anybody else only into an org of theirs. Either
# way the person is asked of the database, not of the key: the key remembers them for seconds.
async def key_into_org(
    session: AsyncSession, asking: Person, named: str, *, label: str | None = None
) -> accounts.Issued:
    """The person's key in another org: their seat there, or a visit if they run the box."""
    with box_wide():
        org = await accounts.find_org(session, named)
        mine = await accounts.find_membership(session, asking.id)
        if org is None or mine is None:
            raise NotTheirOrg(named)
        person = mine.person
        if not person.verified and org.id != mine.org:
            raise MailboxUnproven(person.email)
        seats = await accounts.memberships_of(session, person)
        there = next((seat for seat in seats if seat.org == org.id), None)
        # Opening an org one was invited to is taking the seat, with the one password they have.
        takes_it = there is not None and there.status is MemberStatus.invited and person.password_hash is not None
        if there is not None and takes_it and not await SsoRepository(session).is_required(org.id):
            await accounts.take_seat(session, accounts.Membership(there, person))
        if there is not None and there.status is MemberStatus.active:
            return await accounts.issue_person_key(session, there, label=label)
        if not person.operator:
            raise NotTheirOrg(org.id)
        visit = accounts.Issue(
            org=org.id,
            env=Env.production,
            scopes=KEY_SCOPES,
            label=label or A_BROWSER,
            subject=asking.id,
            name=asking.name,
            created_by=asking.id,
        )
        return await accounts.issue_key(session, visit)


# What a key of an unproven address lists is the org it was minted in: the others are its owner's to
# open once the address is proven theirs.
async def list_orgs_of_person(session: AsyncSession, asking: Person, here: str) -> list[OrgOfPerson]:
    """Every org this key's person may open, oldest first, and which one the key opens."""
    with box_wide():
        mine = await accounts.find_membership(session, asking.id)
        if mine is None:
            return []
        person = mine.person
        opened: list[OrgOfPerson] = []
        for seat in await accounts.memberships_of(session, person):
            if seat.status is MemberStatus.disabled or not (person.verified or seat.org == mine.org):
                continue
            org = await accounts.find_org(session, seat.org)
            slug, name = (None, None) if org is None else (org.slug, org.name)
            opened.append(OrgOfPerson(seat.org, slug, name, seat.role.value, seat.status, seat.org == here, True))
        if person.operator and person.verified:
            theirs = {row.org for row in opened}
            opened.extend(
                OrgOfPerson(org.id, org.slug, org.name, VISITING, MemberStatus.active, org.id == here, False)
                for org in await accounts.list_orgs(session)
                if org.id not in theirs
            )
        return opened
