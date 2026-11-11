"""The person: one address, one password, the proof the address is theirs, and their seats across orgs."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts.models import Member, Person
from runtime.accounts.repository.members import MemberRepository, Membership
from runtime.accounts.repository.people import PersonRepository
from runtime.accounts.service import keys, passwords
from runtime.accounts.service.actor import check_may_grant
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Actor
from runtime.exceptions import Conflict
from runtime.kit.crypto import random_id
from runtime.kit.time import now
from runtime.scoping import box_wide

ID_PREFIX = "p_"


class PasswordIsTheirs(Conflict):
    """A person who proved their address, or has a seat beyond this org, sets their own password."""

    def __init__(self, email: str, *, elsewhere: bool) -> None:
        why = (
            "has an account on this box beyond this org, and their one password opens every org of theirs"
            if elsewhere
            else "proved this address is theirs, and their one password is theirs alone to choose"
        )
        super().__init__(
            f"{email} {why}: send them a reset, which is mailed to them, instead of typing a password for them"
        )


async def find_person(session: AsyncSession, email: str) -> Person | None:
    """The person of the address, or None when the box knows nobody by it."""
    return await PersonRepository(session).find_by_email(email)


async def find_or_create_person(session: AsyncSession, email: str) -> Person:
    """The person of the address, made when the address is new to the box: unproven, with no password."""
    return await PersonRepository(session).find_or_create(random_id(ID_PREFIX, 6), email)


async def memberships_of(session: AsyncSession, person: Person) -> Sequence[Member]:
    """Every seat of the person, oldest first, across orgs."""
    with box_wide():
        return await MemberRepository(session).list_of_person(person.id)


async def is_member_elsewhere(session: AsyncSession, person: Person, org: str) -> bool:
    """Whether the person has a seat in another org on this box."""
    return any(seat.org != org for seat in await memberships_of(session, person))


# The one predicate behind every "may this org's admin choose for them": a password typed for a
# member, a link handed to the admin instead of mailed. Once the address is proven, or the person
# has a seat anywhere else, what opens their account goes to their mailbox and nowhere else.
async def is_the_orgs_own(session: AsyncSession, person: Person, org: str) -> bool:
    """Whether the person never proved their address and has no seat outside this org."""
    return not person.verified and not await is_member_elsewhere(session, person, org)


# Until 2026-11-11 a password typed in one org opened every other org of the person: an admin of any
# org could invite another org's member, type their password, and sign in as them there; and a manager
# could type an admin's. Every path that lets a key choose a password asks here.
async def check_may_set_password(session: AsyncSession, actor: Actor, membership: Membership) -> None:
    """Refuse a key that would choose the password of somebody it has no say over."""
    # Whoever sets a password can sign in as that person: a key sets only what it could grant.
    check_may_grant(actor, membership.role, production=False)
    person, org = membership.person, membership.org
    if not await is_the_orgs_own(session, person, org):
        raise PasswordIsTheirs(membership.email, elsewhere=await is_member_elsewhere(session, person, org))


async def set_password(session: AsyncSession, person: Person, hashed: str) -> None:
    """The person's one password, kept as its hash: it opens every org that seats them."""
    await PersonRepository(session).update(person, password_hash=hashed)


async def password_matches(person: Person | None, password: str) -> bool:
    """Whether the password is the person's; nobody, and a person with none, cost a verification all the same."""
    return await passwords.matches(password, None if person is None else person.password_hash)


# A seat can be made for an address by somebody else, with a password of their choosing, before its
# owner ever arrives (found on 2026-11-11, with the takeover above). So what an unproven address holds
# is not its owner's yet: at the first proof that did not present the password (a link only their
# mailbox got, a sign-up's code, Google, the org's provider) the password set while unproven is cleared
# and every key it opened is revoked. A proof that presented the password keeps both: it is theirs.
async def prove_mailbox(session: AsyncSession, cache: KeyCache, person: Person, *, presented_password: bool) -> None:
    """The address is proven the person's, from now; a first proof without the password ends what was set unproven."""
    if person.verified:
        return
    values: dict[str, object] = {"verified_at": now()}
    if person.password_hash is not None and not presented_password:
        values["password_hash"] = None
        await keys.revoke_person_keys(session, cache, person)
    await PersonRepository(session).update(person, **values)


# A person who runs the box does so from whatever org they signed in to: every seat's keys are asked again.
async def set_operator(session: AsyncSession, cache: KeyCache, person: Person, *, on: bool) -> None:
    """Make a person one who runs the box, or take it back at once."""
    await PersonRepository(session).update(person, operator=on)
    for seat in await memberships_of(session, person):
        cache.forget_after_commit(session, subject=seat.id)


async def list_operator_addresses(session: AsyncSession) -> list[str]:
    """The addresses of the box's operators who may sign in: who every org's alerts are mailed to."""
    with box_wide():
        return sorted(person.email for person in await PersonRepository(session).list_active_operators())


# A person exists while an org seats them: the address of somebody removed from their last org is new
# to the box again, as it was when a person was a row of their org.
async def delete_if_orphan(session: AsyncSession, person: Person) -> bool:
    """Forget the person once no org seats them; whether they went."""
    with box_wide():
        return await PersonRepository(session).delete_if_orphan(person.id)


# An org erased takes its members by the foreign key's cascade, and nothing reaches their people.
async def delete_orphans(session: AsyncSession) -> int:
    """Forget every person no org seats: called once an org was erased; how many went."""
    with box_wide():
        return await PersonRepository(session).delete_orphans()
