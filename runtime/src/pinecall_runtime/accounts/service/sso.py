"""Sign-in with the org's identity provider over OpenID Connect, and the proof a domain is the org's."""

import asyncio
import base64
import hashlib
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass

import httpx
import jwt
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.models import Member, Org, OrgSso, SsoDomainProof
from pinecall_runtime.accounts.repository import MemberRepository, SsoRepository
from pinecall_runtime.accounts.schemas import SsoDomainProofRow, SsoRow
from pinecall_runtime.accounts.service import members, orgs
from pinecall_runtime.accounts.service.one_time import OneTimeSecrets
from pinecall_runtime.accounts.service.signin import Handshake
from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env, MemberStatus, Role
from pinecall_runtime.exceptions import (
    Forbidden,
    NotFound,
    Unauthorized,
    UpstreamError,
    ValidationError,
)
from pinecall_runtime.kit import dns
from pinecall_runtime.kit.crypto import Vault, random_token
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide

CALLBACK = "/v1/login/sso/callback"
CONFIGURATION = "/.well-known/openid-configuration"
SCOPE = "openid email profile"
# Asymmetric only: `none`, and HMAC forged with a secret this gateway holds, never pass.
ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"]
REQUIRED_CLAIMS = ["iss", "aud", "exp", "iat", "sub"]
TIMEOUT_S = 5.0
TXT_PREFIX = "pinecall-verify="

# No query or fragment: it is compared with every id_token's `iss` as a string.
AN_ISSUER = re.compile(r"^https://[^\s?#]+[^/\s?#]$")
A_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class NoProvider(NotFound):
    """The org signs in with no identity provider."""

    def __init__(self, org: str) -> None:
        super().__init__(f"org {org} signs in with no identity provider")


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
class Endpoints:
    """What a provider's discovery names."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    basic_auth: bool = False


@dataclass(frozen=True, slots=True)
class Claims:
    """Who a provider vouched for, from an id_token that checked out."""

    subject: str
    email: str
    email_verified: bool
    name: str | None


class _Discovery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    issuer: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""
    token_endpoint_auth_methods_supported: list[str] = []


class _Granted(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id_token: str = ""


class _IdToken(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sub: str
    aud: str | list[str]
    azp: str | None = None
    nonce: str = ""
    email: str = ""
    email_verified: bool | str | None = None
    name: str | None = None
    given_name: str | None = None


# ── the org's provider ──


async def get_provider(session: AsyncSession, vault: Vault, org: str) -> Provider | None:
    """The org's provider, its secret opened; None when it has none."""
    row = await SsoRepository(session).get(org)
    return None if row is None else _provider(vault, row)


async def providers_for_domain(session: AsyncSession, vault: Vault, domain: str) -> list[Provider]:
    """Every org that signs in the domain's addresses with its provider, a verified domain alone."""
    with box_wide():
        rows = await SsoRepository(session).list_for_domain(domain)
    return [_provider(vault, row) for row in rows]


async def put_provider(session: AsyncSession, vault: Vault, provider: Provider) -> Sequence[SsoDomainProof]:
    """Keep the org's provider whole, the secret sealed; a proof per domain, the rest forgotten."""
    sso = SsoRepository(session)
    row = await sso.get(provider.org)
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
        if await sso.proof_of(provider.org, domain) is None:
            await sso.add_proof(SsoDomainProof(org=provider.org, domain=domain, token=random_token(16)))
    await sso.drop_proofs_not_in(provider.org, provider.domains)
    return await sso.proofs_of(provider.org)


async def delete_provider(session: AsyncSession, org: str) -> bool:
    """Forget the org's provider: passwords open it again. Whether it had one."""
    sso = SsoRepository(session)
    row = await sso.get(org)
    if row is None:
        return False
    await sso.delete(row)
    return True


async def proofs_of(session: AsyncSession, org: str) -> Sequence[SsoDomainProof]:
    """Every domain of the org's SSO with its proof."""
    return await SsoRepository(session).proofs_of(org)


async def verified_domains(session: AsyncSession, org: str) -> frozenset[str]:
    """The domains whose TXT record was seen."""
    return frozenset(p.domain for p in await proofs_of(session, org) if p.verified_at is not None)


def txt_of(proof: SsoDomainProof) -> str:
    """The TXT record the org publishes at the domain."""
    return f"{TXT_PREFIX}{proof.token}"


async def verify_domain(session: AsyncSession, org: str, domain: str) -> SsoDomainProof:
    """Look for the domain's TXT record now; the proof verified, or refused saying what was found."""
    sso = SsoRepository(session)
    proof = await sso.proof_of(org, domain)
    if proof is None:
        raise NotFound(f"{domain} is not a domain of this org's SSO: PUT /v1/org/sso names them")
    if proof.verified_at is not None:
        return proof
    records = await asyncio.to_thread(dns.txt_records, domain)
    if txt_of(proof) not in records:
        ours = ", ".join(f"`{r}`" for r in records if r.startswith(TXT_PREFIX)) or "no pinecall-verify record"
        raise ValidationError(
            f"no TXT record `{txt_of(proof)}` at {domain}: publish it there (what is there now: {ours}), "
            "then ask again; a record takes minutes to hours to be seen, by its TTL"
        )
    await sso.verify_proof(proof, now())
    return proof


# ── the handshake ──


async def begin_handshake(
    handshakes: OneTimeSecrets[Handshake], redirect_uri: str, *, org: str | None, pairing: str | None
) -> Handshake:
    """A sign-in at a provider begun: a fresh state, nonce and PKCE verifier, kept here."""
    begun = Handshake(
        state=handshakes.new_secret(),
        org=org,
        nonce=secrets.token_urlsafe(24),
        verifier=secrets.token_urlsafe(32),
        redirect_uri=redirect_uri,
        pairing=pairing,
    )
    await handshakes.keep(begun.state, begun)
    return begun


async def discover(http: httpx.AsyncClient, issuer: str) -> Endpoints:
    """The provider's endpoints, from its own discovery document."""
    url = f"{await _public_url(issuer, issuer=issuer, field='issuer')}{CONFIGURATION}"
    try:
        answer = await http.get(url, timeout=TIMEOUT_S)
        answer.raise_for_status()
        payload = _Discovery.model_validate(answer.json())
    except (httpx.HTTPError, ValueError, PydanticValidationError):
        raise UpstreamError(f"{issuer} does not answer {CONFIGURATION}: not an OpenID provider, or down") from None
    if payload.issuer != issuer:
        raise UpstreamError(f"{issuer} publishes a configuration naming {payload.issuer}: one of the two is wrong")
    methods = payload.token_endpoint_auth_methods_supported
    return Endpoints(
        issuer=issuer,
        authorization_endpoint=_endpoint(payload.authorization_endpoint, issuer, "authorization_endpoint"),
        token_endpoint=_endpoint(payload.token_endpoint, issuer, "token_endpoint"),
        jwks_uri=_endpoint(payload.jwks_uri, issuer, "jwks_uri"),
        basic_auth="client_secret_basic" in methods and "client_secret_post" not in methods,
    )


def authorization_url(endpoints: Endpoints, provider: Provider, begun: Handshake) -> str:
    """Where the browser goes to sign in, with the state and the PKCE challenge."""
    challenge = base64.urlsafe_b64encode(hashlib.sha256(begun.verifier.encode()).digest()).decode().rstrip("=")
    params = httpx.QueryParams(
        {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": begun.redirect_uri,
            "scope": SCOPE,
            "state": begun.state,
            "nonce": begun.nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return str(httpx.URL(endpoints.authorization_endpoint).copy_merge_params(params))


async def claims_for_code(http: httpx.AsyncClient, provider: Provider, begun: Handshake, code: str) -> Claims:
    """The person the provider signed in, their address verified, from the code it returned."""
    endpoints = await discover(http, provider.issuer)
    id_token = await _exchange(http, endpoints, provider, begun, code)
    claims = await _claims(http, endpoints, id_token, provider.client_id, begun.nonce)
    if not claims.email:
        raise Unauthorized(f"{provider.issuer} vouched for somebody it gave no email address for")
    if not claims.email_verified:
        raise Unauthorized(
            f"{provider.issuer} has not verified {claims.email}: nobody is seated on an unverified address"
        )
    return claims


async def seat_vouched(session: AsyncSession, org: Org, provider: Provider, claims: Claims) -> Member:
    """The org's member for the address its provider vouched for: seated, invited or made."""
    email = claims.email.strip().lower()
    people = MemberRepository(session)
    kept = await people.get_by_email(org.id, email)
    if kept is not None and kept.status is MemberStatus.disabled:
        raise Forbidden(f"{email} is disabled in {org.slug}")
    if kept is None:
        if provider.role is None:
            raise Forbidden(f"nobody in {org.slug} answers to {email}, and it seats nobody it was not told to")
        quotas = await billing.get_quotas(session, org.id, Env.production)
        await billing.admit_seat(session, org.id, Env.production, seated=await people.count_seated(org.id))
        name = claims.name or email.partition("@")[0]
        kept = (
            await members.invite(session, org.id, members.Invitee(email, name, provider.role), seats=quotas.seats)
        ).member
    seated = await members.seat_vouched(session, kept)
    if seated is None:
        raise Forbidden(f"nobody in {org.slug} answers to {email}, and it seats nobody it was not told to")
    return seated


async def seat_from_callback(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, begun: Handshake, code: str
) -> Member:
    """The whole callback: the provider, the claims, the domain check, the seat."""
    named = begun.org or ""
    provider = await get_provider(session, vault, named)
    org = await orgs.find_org(session, named)
    if provider is None or org is None:
        raise NoProvider(named)
    claims = await claims_for_code(http, provider, begun, code)
    proven = await verified_domains(session, org.id)
    if not provider.admits(claims.email) or claims.email.rpartition("@")[2].lower() not in proven:
        raise Forbidden(f"{claims.email} is not in a domain {org.slug} signs in with")
    return await seat_vouched(session, org, provider, claims)


# ── private ──


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


def _reachable(url: str, *, issuer: str, field: str) -> str:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        raise Forbidden(f"{issuer}'s {field} is {url!r}: an endpoint is https, at a public name") from None
    if parsed.scheme != "https" or dns.is_local_name(parsed.host):
        raise Forbidden(f"{issuer}'s {field} is {url!r}: an endpoint is https, at a public name, never an address")
    return url


async def _public_url(url: str, *, issuer: str, field: str) -> str:
    host = httpx.URL(_reachable(url, issuer=issuer, field=field)).host
    try:
        addresses = await asyncio.to_thread(dns.resolve, host)
    except OSError:
        addresses = []
    if not dns.all_public(addresses):
        raise Forbidden(f"{issuer}'s {field} is {url!r}: it resolves inside, not on the internet")
    return url


def _endpoint(found: str, issuer: str, field: str) -> str:
    if not found:
        raise UpstreamError(f"{issuer}'s configuration names no {field}")
    return _reachable(found, issuer=issuer, field=field)


async def _exchange(
    http: httpx.AsyncClient, endpoints: Endpoints, provider: Provider, begun: Handshake, code: str
) -> str:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": begun.redirect_uri,
        "client_id": provider.client_id,
        "code_verifier": begun.verifier,
    }
    if not endpoints.basic_auth:
        form["client_secret"] = provider.client_secret
    await _public_url(endpoints.token_endpoint, issuer=endpoints.issuer, field="token_endpoint")
    try:
        answer = await http.post(
            endpoints.token_endpoint,
            data=form,
            timeout=TIMEOUT_S,
            auth=(provider.client_id, provider.client_secret) if endpoints.basic_auth else httpx.USE_CLIENT_DEFAULT,
        )
    except httpx.HTTPError as unreachable:
        raise UpstreamError(f"{endpoints.issuer} refused the code exchange: {unreachable}") from None
    if answer.status_code >= httpx.codes.BAD_REQUEST:
        raise Unauthorized(f"{endpoints.issuer} refused the code exchange: HTTP {answer.status_code}")
    try:
        granted = _Granted.model_validate(answer.json())
    except (ValueError, PydanticValidationError):
        raise UpstreamError(f"{endpoints.issuer} answered the exchange without an id_token") from None
    if not granted.id_token:
        raise UpstreamError(f"{endpoints.issuer} answered the exchange without an id_token")
    return granted.id_token


async def _claims(http: httpx.AsyncClient, endpoints: Endpoints, id_token: str, client_id: str, nonce: str) -> Claims:
    key = await _signing_key(http, endpoints, id_token)
    try:
        decoded = jwt.decode(
            id_token,
            key=key,
            algorithms=ALGORITHMS,
            audience=client_id,
            issuer=endpoints.issuer,
            options={"require": REQUIRED_CLAIMS},
        )
        data = _IdToken.model_validate(decoded)
    except (jwt.InvalidTokenError, PydanticValidationError) as refused:
        raise Unauthorized(f"the id_token did not check out: {refused}") from None
    if not secrets.compare_digest(data.nonce, nonce):
        raise Unauthorized("the id_token answers a different sign-in: its nonce is not this one's")
    # OIDC Core 3.1.3.7: with several audiences `azp` is required, and it names this client.
    if isinstance(data.aud, list) and len(data.aud) > 1 and data.azp is None:
        raise Unauthorized(f"the id_token names no azp: this gateway is {client_id!r}")
    if data.azp is not None and data.azp != client_id:
        raise Unauthorized(f"the id_token was issued to {data.azp!r}: this gateway is {client_id!r}")
    verified = data.email_verified is True or str(data.email_verified).lower() == "true"
    return Claims(subject=data.sub, email=data.email, email_verified=verified, name=data.name or data.given_name)


async def _signing_key(http: httpx.AsyncClient, endpoints: Endpoints, id_token: str) -> jwt.PyJWK:
    await _public_url(endpoints.jwks_uri, issuer=endpoints.issuer, field="jwks_uri")
    try:
        answer = await http.get(endpoints.jwks_uri, timeout=TIMEOUT_S)
        answer.raise_for_status()
        published = jwt.PyJWKSet.from_dict(answer.json())
        kid = jwt.get_unverified_header(id_token).get("kid")
    except (httpx.HTTPError, ValueError, jwt.PyJWTError):
        raise UpstreamError(f"{endpoints.issuer} signed the id_token with a key its JWKS does not publish") from None
    matching = [key for key in published.keys if kid is None or key.key_id == kid]
    if len(matching) != 1:
        raise UpstreamError(f"{endpoints.issuer} signed the id_token with a key its JWKS does not publish")
    return matching[0]


def sso_row(provider: Provider | None, base: str, proofs: Sequence[SsoDomainProof]) -> SsoRow:
    """The org's provider as the endpoints answer it: never its secret, the redirect URI to register."""
    return SsoRow(
        configured=provider is not None,
        issuer=None if provider is None else provider.issuer,
        client_id=None if provider is None else provider.client_id,
        domains=[] if provider is None else list(provider.domains),
        role=None if provider is None else provider.role,
        required=provider is not None and provider.required,
        redirect_uri=f"{base}{CALLBACK}",
        proofs=[proof_row(proof) for proof in proofs],
    )


def proof_row(proof: SsoDomainProof) -> SsoDomainProofRow:
    """One domain's proof as the endpoints answer it."""
    return SsoDomainProofRow(domain=proof.domain, txt=txt_of(proof), verified=proof.verified_at is not None)
