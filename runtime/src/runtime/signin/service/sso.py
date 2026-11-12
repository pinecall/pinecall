"""An org's own identity provider: kept sealed, its domains proven by DNS, a sign-in through it, whom it seats."""

import asyncio
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.accounts.models import Org
from runtime.actor import Actor
from runtime.enums import MemberStatus, Role
from runtime.exceptions import Conflict, Forbidden, NotFound, PinecallError, UpstreamError, ValidationError
from runtime.kit import dns
from runtime.kit.crypto import Vault, random_token
from runtime.kit.time import now
from runtime.platform import service as platform
from runtime.scoping import box_wide
from runtime.signin.models import OrgSso, SsoDomainProof
from runtime.signin.repository import SsoRepository
from runtime.signin.service.codes import LoginCodes, holder_of_member
from runtime.signin.service.oidc import Answer, Claims, Handshake, Landing, Oidc

TXT_PREFIX = "pinecall-verify="

# No query or fragment: it is compared with every id_token's `iss` as a string.
AN_ISSUER = re.compile(r"^https://[^\s?#]+[^/\s?#]$")
A_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class NoProvider(NotFound):
    """The org signs in with no identity provider."""

    def __init__(self, org: str | None = None) -> None:
        whose = "this org" if org is None else f"org {org}"
        super().__init__(f"{whose} signs in with no identity provider")


@dataclass(frozen=True, slots=True)
class Provider:
    """An org's own identity provider, as the service holds it: secret opened."""

    org: str
    issuer: str
    client_id: str
    client_secret: str
    domains: tuple[str, ...]
    role: Role | None = None
    required: bool = False

    def __post_init__(self) -> None:
        if not AN_ISSUER.match(self.issuer):
            raise ValidationError(f"an issuer is an https URL with no query and no trailing slash, not {self.issuer!r}")
        if not self.client_id.strip() or not self.client_secret.strip():
            raise ValidationError("a provider's client carries its id and its secret")
        if not self.domains:
            raise ValidationError("an SSO configuration names at least one email domain")
        for domain in self.domains:
            if not A_DOMAIN.match(domain):
                raise ValidationError(f"{domain!r} is not an email domain, folded and bare")

    def admits(self, email: str) -> bool:
        """Whether the address is of one of the org's domains."""
        return email.rpartition("@")[2].strip().lower() in self.domains


@dataclass(frozen=True, slots=True)
class Wanted:
    """The provider an org's admin asks for, as typed: the client whole, the domains, the role, whether required."""

    issuer: str
    client_id: str
    client_secret: str
    domains: Sequence[str]
    role: Role | None = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class Proof:
    """One domain of an org's provider: the TXT record that proves it the org's, and whether it was seen."""

    domain: str
    txt: str
    verified: bool


# Flat, as the page that shows a provider reads it; never its secret.
@dataclass(frozen=True, slots=True)
class Wiring:
    """An org's provider as its settings show it: the client, the domains with their proofs, the URI to register."""

    provider: Provider | None
    proofs: Sequence[Proof]
    redirect_uri: str

    @property
    def configured(self) -> bool:
        """Whether the org has a provider."""
        return self.provider is not None

    @property
    def issuer(self) -> str | None:
        """The provider, as its id_tokens name it."""
        return None if self.provider is None else self.provider.issuer

    @property
    def client_id(self) -> str | None:
        """This gateway, as the provider knows it."""
        return None if self.provider is None else self.provider.client_id

    @property
    def domains(self) -> list[str]:
        """The email domains the provider signs in."""
        return [] if self.provider is None else list(self.provider.domains)

    @property
    def role(self) -> Role | None:
        """The role somebody the provider vouches for is seated with; none seats nobody new."""
        return None if self.provider is None else self.provider.role

    @property
    def required(self) -> bool:
        """Whether a password is refused for this org."""
        return self.provider is not None and self.provider.required


# ── the org's provider ──


def fold_domains(written: Iterable[str]) -> tuple[str, ...]:
    """Email domains as they are kept and compared: trimmed, lowercased, with no leading `@`."""
    return tuple(domain.strip().lower().removeprefix("@") for domain in written)


async def find_provider(session: AsyncSession, vault: Vault, org: str) -> Provider | None:
    """The org's provider, its secret opened; None when it has none."""
    row = await SsoRepository(session).find(org)
    return None if row is None else _provider(vault, row)


async def put_provider(session: AsyncSession, vault: Vault, provider: Provider) -> Sequence[SsoDomainProof]:
    """Keep the org's provider whole, the secret sealed; a proof per domain, the rest forgotten."""
    sso = SsoRepository(session)
    row = await sso.find(provider.org)
    values = {
        "issuer": provider.issuer,
        "client_id": provider.client_id,
        "ciphertext": vault.seal(provider.client_secret),
        "domains": list(provider.domains),
        "role": None if provider.role is None else provider.role.value,
        "required": provider.required,
        "set_at": now(),
    }
    if row is None:
        await sso.add(OrgSso(org=provider.org, **values))
    else:
        await sso.update(row, **values)
    for domain in provider.domains:
        if await sso.find_proof(provider.org, domain) is None:
            await sso.add_proof(SsoDomainProof(org=provider.org, domain=domain, token=random_token(16)))
    await sso.delete_proofs_not_in(provider.org, provider.domains)
    return await sso.list_proofs(provider.org)


async def delete_provider(session: AsyncSession, org: str) -> None:
    """Forget the org's provider: passwords open it again; NoProvider when it had none."""
    sso = SsoRepository(session)
    row = await sso.find(org)
    if row is None:
        raise NoProvider()
    await sso.delete(row)


# No foreign key reaches a proof from its org: the org's erasure calls this.
async def delete_proofs(session: AsyncSession, org: str) -> int:
    """Forget every domain proof of an org that is being erased; how many went."""
    return await SsoRepository(session).delete_proofs(org)


async def list_verified_domains(session: AsyncSession, org: str) -> frozenset[str]:
    """The domains whose TXT record was seen."""
    proofs = await SsoRepository(session).list_proofs(org)
    return frozenset(proof.domain for proof in proofs if proof.verified_at is not None)


def txt_of(proof: SsoDomainProof) -> str:
    """The TXT record the org publishes at the domain."""
    return f"{TXT_PREFIX}{proof.token}"


async def verify_domain(session: AsyncSession, org: str, written: str) -> Proof:
    """Look for the domain's TXT record now; the proof verified, or refused saying what was found."""
    (domain,) = fold_domains([written])
    sso = SsoRepository(session)
    proof = await sso.find_proof(org, domain)
    if proof is None:
        raise NotFound(f"{domain} is not a domain of this org's SSO: PUT /v1/org/sso names them")
    if proof.verified_at is not None:
        return _proof(proof)
    records = await asyncio.to_thread(dns.txt_records, domain)
    if txt_of(proof) not in records:
        ours = ", ".join(f"`{r}`" for r in records if r.startswith(TXT_PREFIX)) or "no pinecall-verify record"
        raise ValidationError(
            f"no TXT record `{txt_of(proof)}` at {domain}: publish it there (what is there now: {ours}), "
            "then ask again; a record takes minutes to hours to be seen, by its TTL"
        )
    await sso.verify_proof(proof, now())
    return _proof(proof)


async def wiring_of(session: AsyncSession, vault: Vault, org: str, *, redirect_uri: str) -> Wiring:
    """The org's provider, never its secret, its domains' proofs, and the redirect URI to register there."""
    provider = await find_provider(session, vault, org)
    return _wiring(provider, await SsoRepository(session).list_proofs(org), redirect_uri)


# A provider seats whom it vouches for with the role named here, so a key names only a role it could
# grant; and it is asked for its discovery before anything is kept, so a typo locks nobody out.
async def put_provider_as_admin(
    session: AsyncSession, vault: Vault, oidc: Oidc, actor: Actor, wanted: Wanted, *, redirect_uri: str
) -> Wiring:
    """Replace the actor's org's provider whole, once its issuer answered as one."""
    accounts.check_may_grant(actor, wanted.role, production=False)
    provider = Provider(
        org=actor.org,
        issuer=wanted.issuer,
        client_id=wanted.client_id,
        client_secret=wanted.client_secret,
        domains=fold_domains(wanted.domains),
        role=wanted.role,
        required=wanted.required,
    )
    try:
        await oidc.discover(provider.issuer)
    except UpstreamError as unanswered:
        raise ValidationError(f"{unanswered}: nothing was kept") from unanswered
    if provider.required and not await list_verified_domains(session, actor.org) & frozenset(provider.domains):
        raise Conflict(
            "no domain of this SSO is verified yet: publish each domain's TXT record and verify it, then require it"
        )
    return _wiring(provider, await put_provider(session, vault, provider), redirect_uri)


# The operator's break-glass: a password opens the org again while its provider is down. Never the
# other way: requiring the provider is the org's own call.
async def set_required(session: AsyncSession, vault: Vault, org: Org, *, required: bool, redirect_uri: str) -> Wiring:
    """Whether a password may still open the org beside its provider."""
    wired = await find_provider(session, vault, org.id)
    if wired is None:
        raise NoProvider(org.slug)
    changed = replace(wired, required=required)
    return _wiring(changed, await put_provider(session, vault, changed), redirect_uri)


# ── signing in through it ──


async def list_orgs_for_address(
    session: AsyncSession, attempts: platform.AttemptThrottle, email: str, *, client: str
) -> list[Org]:
    """The orgs whose provider signs in this address's domain, a verified domain alone, oldest first."""
    await attempts.check(f"{client} sso/{email}", email)
    domain = email.rpartition("@")[2]
    if not A_DOMAIN.match(domain):
        return []
    with box_wide():
        rows = await SsoRepository(session).list_for_domain(domain)
    found = [await accounts.find_org(session, row.org) for row in rows]
    return [org for org in found if org is not None]


async def begin(
    session: AsyncSession,
    vault: Vault,
    oidc: Oidc,
    attempts: platform.AttemptThrottle,
    named: str,
    *,
    client: str,
    redirect_uri: str,
    pairing: str | None,
) -> str:
    """Where the browser goes to sign in at the org's provider, with a state, a nonce and a PKCE challenge."""
    owner = await accounts.find_org(session, named)
    provider = None if owner is None else await find_provider(session, vault, owner.id)
    if owner is None or provider is None:
        raise NoProvider(named)
    await attempts.check(f"{client} sso/{owner.slug}", "sign-ins from here")
    return await oidc.begin(session, provider, redirect_uri, org=owner.id, pairing=pairing)


# What refuses a person here is shown to them by the console, not answered as an error: the browser
# came back from the provider and has no page of ours to read a status on.
async def finish(
    session: AsyncSession, cache: accounts.KeyCache, vault: Vault, oidc: Oidc, codes: LoginCodes, answer: Answer
) -> Landing:
    """The whole callback: the code exchanged, the person seated, and a login code for the console."""
    begun = await oidc.resume(answer.state)
    if answer.error is not None:
        return Landing(refused=f"the sign-in was refused at the provider: {answer.error}")
    if not answer.code:
        return Landing(refused="the provider sent no authorization code back")
    try:
        membership = await _seat_from_callback(session, cache, vault, oidc, begun, answer.code)
    except PinecallError as refusal:
        return Landing(refused=str(refusal))
    minted = await codes.mint_on(session, holder_of_member(membership))
    return Landing(login=minted.code, pairing=begun.pairing)


# The provider proved the address without the password: `accounts.seat_vouched` ends whatever was set
# while the address was unproven. A person the org never invited is made one with the provider's role,
# within the org's seats.
async def seat_vouched(
    session: AsyncSession, cache: accounts.KeyCache, org: Org, provider: Provider, claims: Claims
) -> accounts.Membership:
    """The org's member for the address its provider vouched for: seated, invited or made."""
    email = claims.email
    nobody = Forbidden(f"nobody in {org.slug} answers to {email}, and it seats nobody it was not told to")
    membership = await _seat_in(session, org, email)
    if membership is not None and membership.status is MemberStatus.disabled:
        raise Forbidden(f"{email} is disabled in {org.slug}")
    if membership is None:
        if provider.role is None:
            raise nobody
        name = claims.name or email.partition("@")[0]
        membership = (await accounts.invite(session, org.id, accounts.Invitee(email, name, provider.role))).membership
    seated = await accounts.seat_vouched(session, cache, membership)
    if seated is None:
        raise nobody
    return seated


# ── private ──


async def _seat_from_callback(
    session: AsyncSession, cache: accounts.KeyCache, vault: Vault, oidc: Oidc, begun: Handshake, code: str
) -> accounts.Membership:
    named = begun.org or ""
    provider = await find_provider(session, vault, named)
    org = await accounts.find_org(session, named)
    if provider is None or org is None:
        raise NoProvider(named)
    claims = await oidc.claims_for_code(provider, begun, code)
    proven = await list_verified_domains(session, org.id)
    if not provider.admits(claims.email) or claims.email.rpartition("@")[2] not in proven:
        raise Forbidden(f"{claims.email} is not in a domain {org.slug} signs in with")
    return await seat_vouched(session, cache, org, provider, claims)


async def _seat_in(session: AsyncSession, org: Org, email: str) -> accounts.Membership | None:
    person = await accounts.find_person(session, email)
    if person is None:
        return None
    seat = next((each for each in await accounts.memberships_of(session, person) if each.org == org.id), None)
    return None if seat is None else accounts.Membership(seat, person)


def _provider(vault: Vault, row: OrgSso) -> Provider:
    role = None if row.role is None or row.role not in Role.__members__ else Role(row.role)
    return Provider(
        org=row.org,
        issuer=row.issuer,
        client_id=row.client_id,
        client_secret=vault.open(row.ciphertext),
        domains=tuple(row.domains),
        role=role,
        required=row.required,
    )


def _proof(proof: SsoDomainProof) -> Proof:
    return Proof(domain=proof.domain, txt=txt_of(proof), verified=proof.verified_at is not None)


def _wiring(provider: Provider | None, proofs: Sequence[SsoDomainProof], redirect_uri: str) -> Wiring:
    return Wiring(provider, [_proof(proof) for proof in proofs], redirect_uri)
