"""Sign-in: a password, a one-time code, a paired terminal, a sign-up, or another org of the person's."""

import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import ApiKey, Member
from pinecall_runtime.accounts.repository import ApiKeyRepository, MemberRepository, SsoRepository
from pinecall_runtime.accounts.service import emails, members, orgs
from pinecall_runtime.accounts.service.attempts import SIGN_IN_TRIES, AttemptThrottle
from pinecall_runtime.accounts.service.keys import KEY_SCOPES, Issue, issue_key, issue_person_key
from pinecall_runtime.accounts.service.mail import Outbox
from pinecall_runtime.accounts.service.one_time import OneTimeSecrets
from pinecall_runtime.enums import Env, KeyScope, MemberStatus, Role
from pinecall_runtime.exceptions import Forbidden, Unauthorized
from pinecall_runtime.kit.auth import Actor, Person
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import box_wide
from pinecall_runtime.redis import Signal

type Refusal = Literal["wrong", "expired", "burned"]

# A browser signs in with a code, never a key in the URL; a terminal waits ten minutes; a provider
# handshake the same; a sign-up as long as its code.
LOGIN_CODE = ("lc_", 300.0)
PAIRING = ("cli_", 600.0)
HANDSHAKE = ("st_", 600.0)
SIGNUP = ("su_", 15 * 60.0)
CODE_DIGITS = 6
CODE_ATTEMPTS = 6
A_BROWSER = "console"
SIGNED_UP = "signup"


class NobodyAnswers(Unauthorized):
    """One sentence for a wrong org, address or password: nobody learns who is a member."""

    def __init__(self) -> None:
        super().__init__("nobody answers to that email and password")


class NotAPersons(Forbidden):
    """A server's token names nobody."""

    def __init__(self) -> None:
        super().__init__("a server's token names nobody: a person's key signs another device in")


class NotTheirOrg(Forbidden):
    """The org is not one of the person's."""

    def __init__(self, org: str) -> None:
        super().__init__(f"{org} is not an org of this person's")


@dataclass(frozen=True, slots=True)
class SignedIn:
    """The key a sign-in minted, handed over once, and the person it is for."""

    key: ApiKey
    secret: str
    member: Member | None = None


@dataclass(frozen=True, slots=True)
class PasswordSignIn:
    """What a person typed: the address, the password, the org when they have several."""

    email: str
    password: str
    org: str | None = None
    device: str | None = None


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


@dataclass(frozen=True, slots=True)
class WaitingTerminal:
    """A terminal waiting: what it calls itself, and the key a browser gave it once approved."""

    device: str | None = None
    key: str | None = None
    org: str | None = None


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


@dataclass(frozen=True, slots=True)
class Handshake:
    """A sign-in at a provider, in flight: its state, nonce, verifier and where it returns."""

    state: str
    org: str | None
    nonce: str
    verifier: str
    redirect_uri: str
    pairing: str | None = None


@dataclass(frozen=True, slots=True)
class Founded:
    """An org just made, its admin, their first key, and the code that opens the console."""

    org_id: str
    slug: str
    admin: Member
    signed_in: SignedIn
    code: str
    code_expires_at: float


class SignIns:
    """What sign-in keeps between two requests: codes, terminals, sign-ups, handshakes, attempts."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: Vault, signal: Signal) -> None:
        self.sessions = sessions
        self.signal = signal
        self.codes = OneTimeSecrets(*LOGIN_CODE, TypeAdapter(CodeHolder), sessions, vault)
        self.pairings = OneTimeSecrets(*PAIRING, TypeAdapter(WaitingTerminal), sessions, vault)
        self.signups = OneTimeSecrets(*SIGNUP, TypeAdapter(PendingSignUp), sessions, vault)
        self.handshakes = OneTimeSecrets(*HANDSHAKE, TypeAdapter(Handshake), sessions, vault)
        self.attempts = AttemptThrottle(sessions, SIGN_IN_TRIES)


# ── passwords ──


async def sign_in_with_password(session: AsyncSession, asking: PasswordSignIn) -> SignedIn:
    """A person's key for the address and password; the org named, or the one a password opens."""
    known = await members.password_hash_of(session, asking.email)
    if not await members.password_matches(asking.password, known) or known is None:
        raise NobodyAnswers()
    member = await _membership_for(session, asking)
    if member is None:
        raise NobodyAnswers()
    if await SsoRepository(session).is_required(member.org):
        slug = await orgs.slug_of(session, member.org)
        raise Forbidden(f"{slug} signs in with its identity provider: open /v1/login/sso?org={slug}")
    if member.status is MemberStatus.disabled:
        raise Forbidden(f"{member.email} is disabled in {await orgs.slug_of(session, member.org)}")
    if member.status is MemberStatus.invited:
        # A password set through a link an admin handed over could be anybody's: only a proven
        # address joins with the password it has.
        seated = await members.join_with_password(session, member, known) if member.verified else None
        if seated is None:
            raise Forbidden(
                f"{member.email} has not accepted their invitation yet: open the link and choose a password"
            )
        member = seated
    key, secret = await issue_person_key(session, member, label=asking.device)
    return SignedIn(key, secret, member)


async def orgs_a_password_opens(session: AsyncSession, email: str, password: str) -> list[Member]:
    """The memberships an address and password open, minting nothing; none for a wrong password."""
    known = await members.password_hash_of(session, email)
    if not await members.password_matches(password, known):
        return []
    return [m for m in await members.memberships_of(session, email) if m.status is not MemberStatus.disabled]


# ── codes ──


def holder_of_member(member: Member) -> CodeHolder:
    """A login code that signs a browser in as this person."""
    return CodeHolder(member_id=member.id, org=member.org)


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


async def sign_in_with_code(
    session: AsyncSession, codes: OneTimeSecrets[CodeHolder], code: str, *, device: str | None = None
) -> SignedIn | None:
    """The key the code was minted for, spent; None for a code dead, spent or nobody's."""
    holder = await codes.spend(code)
    if holder is None:
        return None
    label = device or A_BROWSER
    if holder.member_id is not None:
        member = await MemberRepository(session).get_by_id(holder.member_id)
        if member is None or member.status is not MemberStatus.active:
            return None
        key, secret = await issue_person_key(session, member, label=label)
        return SignedIn(key, secret, member)
    expires_at = None if holder.expires_at is None else datetime.fromtimestamp(holder.expires_at, UTC)
    issue = Issue(
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
    key, secret = await issue_key(session, issue)
    return SignedIn(key, secret)


async def another_device_key(session: AsyncSession, actor: Actor, *, device: str | None = None) -> SignedIn:
    """The same person's key for another device, never outliving the key that asked."""
    if actor.person is None:
        raise NotAPersons()
    member = await MemberRepository(session).get_by_id(actor.person.id)
    if member is None or member.status is not MemberStatus.active:
        raise Forbidden("the person this key was minted for is no longer an active member of this org")
    keys = ApiKeyRepository(session)
    parent = await keys.one_or_none(keys.statement().where(ApiKey.id == actor.key_id))
    key, secret = await issue_person_key(session, member, parent=parent, label=device)
    return SignedIn(key, secret, member)


# A person of the box is let into any org, as an admin; anybody else only into an org of theirs.
async def key_into_org(session: AsyncSession, person: Person, org: str, *, label: str | None = None) -> SignedIn:
    """The person's key in another org: their membership there, or a visit if they run the box."""
    with box_wide():
        there = await MemberRepository(session).get_by_email(org, person.email)
        if there is not None and there.status is MemberStatus.invited and there.verified:
            # Opening an org one was invited to is taking the seat, with the one password they have.
            known = await members.password_hash_of(session, person.email)
            if known is not None and not await SsoRepository(session).is_required(org):
                there = await members.join_with_password(session, there, known) or there
        if there is not None and there.status is MemberStatus.active:
            key, secret = await issue_person_key(session, there, label=label)
            return SignedIn(key, secret, there)
        if not person.operator or await orgs.find_org(session, org) is None:
            raise NotTheirOrg(org)
        visit = Issue(
            org=org,
            env=Env.production,
            scopes=KEY_SCOPES,
            label=label or A_BROWSER,
            subject=person.id,
            name=person.name,
            created_by=person.id,
        )
        key, secret = await issue_key(session, visit)
    return SignedIn(key, secret)


# ── pairings ──


class Pairings:
    """Terminals waiting for a browser to sign them in; the approval is heard on every gateway."""

    def __init__(self, secrets_: OneTimeSecrets[WaitingTerminal], signal: Signal) -> None:
        self.secrets = secrets_
        self.signal = signal

    async def open(self, device: str | None) -> tuple[str, float]:
        """The code a terminal prints, and when it dies."""
        return await self.secrets.mint(WaitingTerminal(device))

    async def status(self, code: str) -> tuple[WaitingTerminal, float] | None:
        """The terminal and when its code dies, without spending; None for a dead one."""
        kept = await self.secrets.read_alive(code)
        return None if kept is None else (kept.value, kept.expires_at)

    async def approve(self, code: str, key: str, org: str) -> bool:
        """Hand the terminal the key a browser approved; False when dead or answered already."""
        kept = await self.secrets.read_alive(code)
        if kept is None or kept.value.key is not None:
            return False
        filled = await self.secrets.fill(code, replace(kept.value, key=key, org=org))
        if filled:
            self.signal.publish(_approval_channel(code), b"")
        return filled

    async def collect(self, code: str, *, within_s: float = 0) -> tuple[str | None, bool]:
        """The key once, waiting up to `within_s` for an approval: (key, still waiting)."""
        # Listening before the first look, so an approval between the two is heard.
        listener = await self.signal.subscribe(_approval_channel(code))
        try:
            key, waiting = await self._collect(code)
            if waiting and within_s > 0:
                try:
                    async with asyncio.timeout(within_s):
                        await anext(listener)
                except (TimeoutError, StopAsyncIteration):
                    pass
                key, waiting = await self._collect(code)
            return key, waiting
        finally:
            listener.close()

    async def _collect(self, code: str) -> tuple[str | None, bool]:
        kept = await self.secrets.read_alive(code)
        if kept is None:
            return None, False
        if kept.value.key is None:
            return None, True
        spent = await self.secrets.spend(code)
        return (None if spent is None else spent.key), False


# ── sign-up ──


class SignUps:
    """Sign-ups waiting for the six digits that were mailed."""

    def __init__(self, secrets_: OneTimeSecrets[PendingSignUp]) -> None:
        self.secrets = secrets_

    async def begin(self, pending: PendingSignUp) -> tuple[str, float]:
        """Keep the sign-up under a fresh code and hand the code back, with when it dies."""
        code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
        salt = secrets.token_bytes(16)
        kept = replace(pending, code_hash=_hashed(salt, code).hex(), salt=salt.hex())
        return code, await self.secrets.keep(_signing_up(pending.email), kept)

    async def renew(self, email: str) -> tuple[PendingSignUp, str] | None:
        """A new code for a sign-up still waiting; None for nobody's."""
        kept = await self.secrets.read_alive(_signing_up(email))
        if kept is None:
            return None
        code, _ = await self.begin(kept.value)
        return kept.value, code

    async def verify(self, email: str, code: str) -> PendingSignUp | Refusal:
        """The sign-up, taken out, when the code is its own; else why not."""
        word = _signing_up(email)
        kept = await self.secrets.read(word)
        if kept is None:
            return "wrong"
        if kept.expires_at <= self.secrets.clock():
            await self.secrets.forget(word)
            return "expired"
        if kept.attempts >= CODE_ATTEMPTS:
            return "burned"
        wanted = _hashed(bytes.fromhex(kept.value.salt), code).hex()
        if not hmac.compare_digest(kept.value.code_hash, wanted):
            return "burned" if await self.secrets.count_attempt(word) >= CODE_ATTEMPTS else "wrong"
        await self.secrets.forget(word)
        return kept.value


async def found_org(session: AsyncSession, signup: PendingSignUp, codes: OneTimeSecrets[CodeHolder]) -> Founded:
    """The org of a verified sign-up, its admin seated, their key, and the console's code."""
    already = len(await members.memberships_of(session, signup.email))
    org = await orgs.create_org(session, signup.slug, signup.name or signup.slug, already=already)
    invitee = members.Invitee(signup.email, signup.person, Role.admin)
    link = await members.invite(session, org.id, invitee, seats=None)
    admin = await members.seat_founder(session, link.token, signup.hashed) or link.member
    key, secret = await issue_person_key(session, admin, label=signup.device or SIGNED_UP)
    code, code_expires_at = await codes.mint(holder_of_member(admin))
    return Founded(org.id, org.slug, admin, SignedIn(key, secret, admin), code, code_expires_at)


# ── a forgotten password ──


async def mail_password_reset(
    session: AsyncSession, outbox: Outbox, email: str, base_url: str, brand: platform.Brand
) -> None:
    """Mail a one-time link that sets the person's password, through the box's own mailbox."""
    if await outbox.mailbox_for(None) is None:
        return
    sso = SsoRepository(session)
    for row in await members.memberships_of(session, email):
        if row.status is not MemberStatus.active or await sso.is_required(row.org):
            continue
        link = await members.reset_link(session, row.org, row.id, vouched=True)
        if link is None:
            continue
        org = await orgs.find_org(session, row.org)
        details = emails.LinkDetails(
            org=org.name if org else row.org, link=emails.card_link(base_url, link.token), dies=link.expires_at
        )
        await outbox.post(None, emails.forgotten_password_email(row.email, details, brand))
        return


# ── private ──


async def _membership_for(session: AsyncSession, asking: PasswordSignIn) -> Member | None:
    if asking.org is not None:
        org = await orgs.find_org(session, asking.org)
        if org is None:
            return None
        with box_wide():
            return await MemberRepository(session).get_by_email(org.id, asking.email.strip().lower())
    rows = await members.memberships_of(session, asking.email)
    enabled = [row for row in rows if row.status is not MemberStatus.disabled]
    # A sign-in that names no org opens one the person took; an org that signs in only with its
    # provider comes after one a password opens.
    taken = [row for row in enabled if row.status is MemberStatus.active] or enabled
    sso = SsoRepository(session)
    for row in taken:
        if not await sso.is_required(row.org):
            return row
    return next(iter(taken), rows[0] if rows else None)


def _hashed(salt: bytes, code: str) -> bytes:
    return hashlib.sha256(salt + code.encode()).digest()


def _signing_up(email: str) -> str:
    return f"{SIGNUP[0]}{email}"


# The code is the terminal's secret: the channel every gateway hears is its hash.
def _approval_channel(code: str) -> str:
    return f"pairing:{hashlib.sha256(code.encode()).hexdigest()}"
