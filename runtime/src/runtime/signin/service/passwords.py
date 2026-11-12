"""Signing in with a password: the tries it is held to, the key it opens, the orgs it opens, and the reset by mail."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.accounts.models import Member, Person
from runtime.enums import MemberStatus, Role
from runtime.exceptions import Forbidden, Unauthorized
from runtime.kit.time import epoch
from runtime.mail import service as mail
from runtime.platform import service as platform
from runtime.signin.repository import SsoRepository
from runtime.signin.service import emails
from runtime.signin.service.turnstile import Turnstile

# Every attempt counts, not only the misses: counting misses would say which guess was right.
SIGN_IN_TRIES = 5
# A password is also so many a minute from one place whatever the address, and at one address from
# wherever: a list of addresses tried from one machine, or one address tried from a list of
# machines, meets the same minute's wait as a person who mistyped five times.
PASSWORD_TRIES_A_PLACE = 20
PASSWORD_TRIES_AN_ADDRESS = 20


class NobodyAnswers(Unauthorized):
    """One sentence for a wrong org, address or password: nobody learns who is a member."""

    def __init__(self) -> None:
        super().__init__("nobody answers to that email and password")


# The address is the one a body read (`kit.schemas.EmailAddress`): folded, so `Ana@x.io` and `ana@x.io`
# are one budget. Until 2026-11 the budget was kept under the address as typed, and the ceiling on one
# address tried from many machines was passed by changing a letter's case.
class PasswordThrottle:
    """A password tried: five a minute per address from one place, and a budget per place and per address."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Callable[[], float] = epoch) -> None:
        self.each = platform.AttemptThrottle(sessions, SIGN_IN_TRIES, clock)
        self.a_place = platform.AttemptThrottle(sessions, PASSWORD_TRIES_A_PLACE, clock)
        self.an_address = platform.AttemptThrottle(sessions, PASSWORD_TRIES_AN_ADDRESS, clock)

    async def check(self, client: str, email: str, org: str | None = None) -> None:
        """TooManyAttempts once any of the three counts is past its tries; the sentence is the same whichever."""
        await self.each.check(f"{client} {org or '*'}/{email}", email)
        await self.a_place.check(f"place {client}", email)
        await self.an_address.check(f"address {email}", email)


@dataclass(frozen=True, slots=True)
class PasswordSignIn:
    """What a person typed: the address, the password, the org when they have several."""

    email: str
    password: str
    org: str | None = None
    device: str | None = None


@dataclass(frozen=True, slots=True)
class OpenedOrg:
    """One org a password opens, and the person's role there."""

    org: str
    slug: str
    name: str
    role: Role


# A code is one use and minted by a signed-in page or a terminal; a password is what a stranger
# tries, and what a phone or a terminal types too, so no captcha stands here: the throttle does.
async def sign_in_with_password(
    session: AsyncSession, throttle: PasswordThrottle, asking: PasswordSignIn, *, client: str
) -> accounts.Issued:
    """A person's key for the address and password; the org named, or the one a password opens."""
    await throttle.check(client, asking.email, asking.org)
    person = await accounts.find_person(session, asking.email)
    if not await accounts.password_matches(person, asking.password) or person is None:
        raise NobodyAnswers()
    seat = await _seat_for(session, person, asking.org)
    if seat is None:
        raise NobodyAnswers()
    if await SsoRepository(session).is_required(seat.org):
        slug = await accounts.slug_of(session, seat.org)
        raise Forbidden(f"{slug} signs in with its identity provider: open /v1/login/sso?org={slug}")
    if seat.status is MemberStatus.disabled:
        raise Forbidden(f"{person.email} is disabled in {await accounts.slug_of(session, seat.org)}")
    if seat.status is MemberStatus.invited:
        # A password set through a link an admin handed over could be anybody's: only a proven
        # address joins with the password it has.
        seated = await accounts.take_seat(session, accounts.Membership(seat, person)) if person.verified else None
        if seated is None:
            raise Forbidden(
                f"{person.email} has not accepted their invitation yet: open the link and choose a password"
            )
    return await accounts.issue_person_key(session, seat, label=asking.device)


async def list_orgs_a_password_opens(
    session: AsyncSession, throttle: PasswordThrottle, email: str, password: str, *, client: str
) -> list[OpenedOrg]:
    """The orgs an address and password open, minting nothing; NobodyAnswers for a wrong password."""
    await throttle.check(client, email)
    person = await accounts.find_person(session, email)
    if not await accounts.password_matches(person, password) or person is None:
        raise NobodyAnswers()
    seats = [
        seat for seat in await accounts.memberships_of(session, person) if seat.status is not MemberStatus.disabled
    ]
    if not seats:
        raise NobodyAnswers()
    opened: list[OpenedOrg] = []
    for seat in seats:
        org = await accounts.find_org(session, seat.org)
        if org is not None:
            opened.append(OpenedOrg(org.id, org.slug, org.name, seat.role))
    return opened


# Answered alike whoever asks, so nobody learns who is a member. The link goes through the box's own
# mailbox to the address and nobody else: opening it proves the address, and sets the one password.
async def forget_password(
    session: AsyncSession,
    email: str,
    captcha: str | None,
    *,
    client: str,
    base: str,
    turnstile: Turnstile,
    attempts: platform.AttemptThrottle,
    outbox: mail.Outbox,
) -> None:
    """Mail a one-time link that sets the person's password, where one can go."""
    await turnstile.check(captcha, "password_reset", client)
    await attempts.check(f"{client} */{email}", email)
    if await outbox.mailbox_for(None) is None:
        return
    person = await accounts.find_person(session, email)
    if person is None:
        return
    sso = SsoRepository(session)
    for seat in await accounts.memberships_of(session, person):
        if seat.status is not MemberStatus.active or await sso.is_required(seat.org):
            continue
        link = await accounts.reset_link(session, accounts.Membership(seat, person), vouched=True)
        if link is None:
            continue
        org = await accounts.find_org(session, seat.org)
        details = mail.LinkDetails(
            org=org.name if org else seat.org, link=accounts.card_link(base, link.token), dies=link.expires_at
        )
        brand = await platform.get_brand(session)
        await outbox.post_after_commit(session, None, emails.password_forgotten_email(person.email, details, brand))
        return


async def _seat_for(session: AsyncSession, person: Person, named: str | None) -> Member | None:
    seats = await accounts.memberships_of(session, person)
    if named is not None:
        org = await accounts.find_org(session, named)
        return None if org is None else next((seat for seat in seats if seat.org == org.id), None)
    enabled = [seat for seat in seats if seat.status is not MemberStatus.disabled]
    # A sign-in that names no org opens one the person took; an org that signs in only with its
    # provider comes after one a password opens.
    taken = [seat for seat in enabled if seat.status is MemberStatus.active] or enabled
    sso = SsoRepository(session)
    for seat in taken:
        if not await sso.is_required(seat.org):
            return seat
    return next(iter(taken), seats[0] if seats else None)
