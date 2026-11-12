"""Sign-up: an org made by whoever the box lets in, from a mailed code or for somebody Google vouched for."""

import hashlib
import hmac
import secrets
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.enums import Role
from runtime.exceptions import Conflict, NotFound, ServiceUnavailable, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import parse_slug, slug_of
from runtime.kit.time import epoch
from runtime.mail import service as mail
from runtime.platform import service as platform
from runtime.signin.service import emails
from runtime.signin.service.codes import LoginCodes, holder_of_member
from runtime.signin.service.google import Newcomer, Newcomers
from runtime.signin.service.one_time import Kind, OneTimeSecrets
from runtime.signin.service.turnstile import Turnstile

type Refusal = Literal["wrong", "expired", "burned"]

# A sign-up waits as long as its code.
SIGNUP = Kind("su_", 15 * 60.0)
CODE_DIGITS = 6
CODE_ATTEMPTS = 6
# What a founder's first key is written under when the device did not say what it is.
SIGNED_UP = "signup"
# What the throttle says it counted, whichever sign-up endpoint ran out.
FROM_HERE = "sign-ups from here"
REFUSED: dict[Refusal, str] = {
    "wrong": "that code is not valid",
    "expired": "that code has expired: ask for a new one",
    "burned": "too many tries: ask for a new code",
}


class SignUpsShut(NotFound):
    """The box takes no sign-ups."""

    def __init__(self) -> None:
        super().__init__(
            "sign-ups are not open on this box: its operator sets PINECALL_SIGNUP, or makes the org and invites you"
        )


class CannotMailACode(ServiceUnavailable):
    """A sign-up's code goes by mail, and the box has no mailbox of its own."""

    def __init__(self) -> None:
        super().__init__("this box cannot mail a code: its operator sets PINECALL_SMTP_URL and PINECALL_MAIL_FROM")


class CodeRefused(ValidationError):
    """The code is not the sign-up's, the sign-up died, or too many guesses were made at it."""

    def __init__(self, why: Refusal) -> None:
        super().__init__(REFUSED[why])
        self.why = why


class NoNewcomer(NotFound):
    """The token is nobody Google vouched for: one is used once, and dies in ten minutes."""

    def __init__(self) -> None:
        super().__init__(
            "the sign-in with Google behind this page is over: it was used, or ten minutes went by — "
            "continue with Google again"
        )


@dataclass(frozen=True, slots=True)
class Asking:
    """What a sign-up's page sends: who, their password, the org's slug or its name, and the captcha's token."""

    email: str
    person: str
    password: str
    org: str | None = None
    name: str | None = None
    device: str | None = None
    captcha: str | None = None


@dataclass(frozen=True, slots=True)
class Naming:
    """What somebody Google vouched for sends: their token, and the workspace's slug or its name."""

    token: str
    org: str | None = None
    name: str | None = None
    device: str | None = None


@dataclass(frozen=True, slots=True)
class Founding:
    """An org about to be made: its admin's address and name, the org's slug and name, their password if any."""

    email: str
    slug: str
    person: str
    name: str | None
    # None for somebody Google vouched for: they sign in through it, or choose one by a reset.
    hashed: str | None
    device: str | None = None


@dataclass(frozen=True, slots=True)
class PendingSignUp:
    """A sign-up waiting for its code: who, the org they name, their password hashed, the code hashed."""

    email: str
    slug: str
    person: str
    hashed: str
    code_hash: str
    salt: str
    name: str | None = None
    device: str | None = None

    def founding(self) -> Founding:
        """The org this sign-up makes, once its code came back."""
        return Founding(self.email, self.slug, self.person, self.name, self.hashed, self.device)


def _load_pending(value: Mapping[str, Any]) -> PendingSignUp:
    return PendingSignUp(
        email=str(value["email"]),
        slug=str(value["slug"]),
        person=str(value["person"]),
        hashed=str(value["hashed"]),
        code_hash=str(value["code_hash"]),
        salt=str(value["salt"]),
        name=value.get("name"),
        device=value.get("device"),
    )


@dataclass(frozen=True, slots=True)
class Drawn:
    """A sign-up kept under a fresh code: the sign-up, the six digits to mail, and when they die."""

    pending: PendingSignUp
    code: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class Mailed:
    """What a sign-up is answered: where the code went and when it dies; never the code."""

    email: str
    code_expires_at: float


@dataclass(frozen=True, slots=True)
class Founded(accounts.Issued):
    """An org just made: its admin's first key, its slug, the admin, and the code that opens the console."""

    slug: str
    member: accounts.Membership
    code: str
    code_expires_at: float


class SignUps:
    """Sign-ups waiting for the six digits that were mailed, and whether the box takes any."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        vault: Vault,
        *,
        accepting: bool,
        clock: Callable[[], float] = epoch,
    ) -> None:
        self.secrets = OneTimeSecrets(SIGNUP, sessions, vault, load=_load_pending, dump=asdict, clock=clock)
        self.accepting = accepting

    def check_open(self) -> None:
        """Refuse where the box takes no sign-ups."""
        if not self.accepting:
            raise SignUpsShut()

    async def keep_on(self, session: AsyncSession, pending: PendingSignUp) -> Drawn:
        """Keep the sign-up under a fresh code, in the caller's transaction, and hand the code back."""
        code, kept = _draw(pending)
        return Drawn(kept, code, await self.secrets.keep_on(session, _secret_of(pending.email), kept))

    # A new code is a new secret: it starts with every one of its guesses.
    async def renew(self, email: str) -> Drawn | None:
        """A new code for a sign-up still waiting; None for nobody's."""
        waiting = await self.secrets.read_alive(_secret_of(email))
        if waiting is None:
            return None
        code, kept = _draw(waiting.value)
        return Drawn(kept, code, await self.secrets.keep(_secret_of(email), kept))

    # The guess is counted before it is compared, in one statement that holds the ceiling: until
    # 2026-11 guesses sent together were all compared before any was counted.
    async def take(self, email: str, code: str) -> PendingSignUp:
        """The sign-up, taken out, when the code is its own; CodeRefused saying why otherwise."""
        secret = _secret_of(email)
        tried = await self.secrets.take_attempt(secret, CODE_ATTEMPTS)
        if tried is None:
            raise CodeRefused(await self._why_not(secret))
        wanted = _hash(bytes.fromhex(tried.value.salt), code).hex()
        if not hmac.compare_digest(tried.value.code_hash, wanted):
            raise CodeRefused("burned" if tried.attempts >= CODE_ATTEMPTS else "wrong")
        # Of two requests with the right code, one takes the sign-up out and founds its org.
        if await self.secrets.spend(secret) is None:
            raise CodeRefused("wrong")
        return tried.value

    async def _why_not(self, secret: str) -> Refusal:
        kept = await self.secrets.read(secret)
        if kept is None:
            return "wrong"
        if kept.expires_at <= self.secrets.clock():
            await self.secrets.forget(secret)
            return "expired"
        return "burned"


def pick_slug(org: str | None, name: str | None) -> str:
    """The org's slug: the one typed, else made of its name; the page never derives one."""
    if org is not None and org.strip():
        return parse_slug(org.strip())
    if name is not None and name.strip():
        return slug_of(name)
    raise ValidationError("an org has a name, or a slug: one of the two")


# Every address is answered alike, so nobody learns who has an account: what differs goes to the
# mailbox. The code is mailed once the sign-up it opens is committed.
async def begin(
    session: AsyncSession,
    sign_ups: SignUps,
    asking: Asking,
    *,
    client: str,
    shortest: int,
    turnstile: Turnstile,
    attempts: platform.AttemptThrottle,
    outbox: mail.Outbox,
) -> Mailed:
    """Keep the sign-up and mail its six digits."""
    sign_ups.check_open()
    if await outbox.mailbox_for(None) is None:
        raise CannotMailACode()
    await turnstile.check(asking.captcha, "signup", client)
    await attempts.check(f"{client} signup", FROM_HERE)
    slug = pick_slug(asking.org, asking.name)
    if not asking.person.strip():
        raise ValidationError("a person has a name: it is what a seat says when they sit")
    hashed = await accounts.hash_password(asking.password, shortest)
    brand = await platform.get_brand(session)
    # Somebody who has a password signs up with it, or anybody could mint keys in their name; a
    # sign-up for an invited address would choose that person's password for them.
    person = await accounts.find_person(session, asking.email)
    known = person is not None and person.password_hash is not None
    notice = None
    if known and not await accounts.password_matches(person, asking.password):
        notice = emails.account_exists_email(asking.email, brand)
    elif person is not None and not known and await accounts.memberships_of(session, person):
        notice = emails.invitation_waiting_email(asking.email, brand)
    if notice is not None:
        await outbox.post_after_commit(session, None, notice)
        return Mailed(asking.email, sign_ups.secrets.clock() + SIGNUP.ttl_s)
    if await accounts.find_org(session, slug) is not None:
        raise accounts.SlugTaken(slug)
    pending = PendingSignUp(asking.email, slug, asking.person, hashed, "", "", asking.name, asking.device)
    drawn = await sign_ups.keep_on(session, pending)
    await outbox.post_after_commit(
        session, None, emails.signup_code_email(asking.email, drawn.code, asking.person, brand)
    )
    return Mailed(asking.email, drawn.expires_at)


async def verify(
    session: AsyncSession,
    cache: accounts.KeyCache,
    sign_ups: SignUps,
    codes: LoginCodes,
    email: str,
    code: str,
    *,
    client: str,
    attempts: platform.AttemptThrottle,
) -> Founded:
    """The mailed code back: the org made, its admin seated, their first key and a login code."""
    sign_ups.check_open()
    await attempts.check(f"{client} signup/verify", FROM_HERE)
    pending = await sign_ups.take(email, code.strip())
    return await found_org(session, cache, codes, pending.founding())


async def resend(
    session: AsyncSession,
    sign_ups: SignUps,
    email: str,
    captcha: str | None,
    *,
    client: str,
    turnstile: Turnstile,
    attempts: platform.AttemptThrottle,
    outbox: mail.Outbox,
) -> None:
    """A new code for a sign-up still waiting; the same answer for any address."""
    sign_ups.check_open()
    await turnstile.check(captcha, "signup_resend", client)
    await attempts.check(f"{client} signup/resend", FROM_HERE)
    drawn = await sign_ups.renew(email)
    if drawn is None:
        return
    brand = await platform.get_brand(session)
    pending = drawn.pending
    await outbox.post_after_commit(
        session, None, emails.signup_code_email(pending.email, drawn.code, pending.person, brand)
    )


async def get_newcomer(sign_ups: SignUps, newcomers: Newcomers, token: str) -> Newcomer:
    """Whom Google vouched for, spending nothing: the page asks them only for a workspace."""
    sign_ups.check_open()
    kept = await newcomers.read_alive(token)
    if kept is None:
        raise NoNewcomer()
    return kept.value


# The token is spent in the transaction that makes the org: a slug taken in between leaves it to be
# used again, and the page to pick another.
async def found_with_google(
    session: AsyncSession,
    cache: accounts.KeyCache,
    sign_ups: SignUps,
    newcomers: Newcomers,
    codes: LoginCodes,
    naming: Naming,
    *,
    client: str,
    attempts: platform.AttemptThrottle,
) -> Founded:
    """The workspace named: the org made, its admin the address Google vouched for, no password and no code."""
    sign_ups.check_open()
    await attempts.check(f"{client} signup/google", FROM_HERE)
    kept = await newcomers.read_alive(naming.token)
    if kept is None:
        raise NoNewcomer()
    newcomer = kept.value
    slug = pick_slug(naming.org, naming.name)
    # Somebody let in elsewhere since Google's callback signs in; a slug taken keeps the page to pick another.
    person = await accounts.find_person(session, newcomer.email)
    if person is not None and await accounts.memberships_of(session, person):
        raise Conflict(f"{newcomer.email} has an account here already: continue with Google again to sign in")
    if await accounts.find_org(session, slug) is not None:
        raise accounts.SlugTaken(slug)
    if await newcomers.spend_on(session, naming.token) is None:
        raise NoNewcomer()
    founding = Founding(newcomer.email, slug, newcomer.person, naming.name, hashed=None, device=naming.device)
    return await found_org(session, cache, codes, founding)


# The code that came back, or Google, proved the address without the password it may hold: a password
# somebody set for it while it was unproven ends here, with every key it opened, before the founder is
# seated with the one this sign-up chose. A password a proven person keeps is never replaced.
async def found_org(session: AsyncSession, cache: accounts.KeyCache, codes: LoginCodes, founding: Founding) -> Founded:
    """The org of a proven address, its admin seated, their key, and the console's code."""
    person = await accounts.find_or_create_person(session, founding.email)
    already = len(await accounts.memberships_of(session, person))
    org = await accounts.create_org(session, founding.slug, founding.name or founding.slug, already=already)
    await accounts.prove_mailbox(session, cache, person, presented_password=False)
    founder = accounts.Invitee(founding.email, founding.person, Role.admin)
    admin = await accounts.seat_founder(session, org.id, founder, founding.hashed)
    issued = await accounts.issue_person_key(session, admin.member, label=founding.device or SIGNED_UP)
    minted = await codes.mint_on(session, holder_of_member(admin))
    return Founded(issued.row, issued.secret, org.slug, admin, minted.code, minted.expires_at)


def _draw(pending: PendingSignUp) -> tuple[str, PendingSignUp]:
    code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
    salt = secrets.token_bytes(16)
    return code, replace(pending, code_hash=_hash(salt, code).hex(), salt=salt.hex())


def _hash(salt: bytes, code: str) -> bytes:
    return hashlib.sha256(salt + code.encode()).digest()


def _secret_of(email: str) -> str:
    return f"{SIGNUP.prefix}{email}"
