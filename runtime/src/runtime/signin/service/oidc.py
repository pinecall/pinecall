"""The OpenID Connect client: a sign-in begun at a provider, kept until its callback, and the answer checked."""

import base64
import hashlib
import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import httpx
import jwt
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import Forbidden, Unauthorized, UpstreamError, ValidationError
from runtime.kit import dns
from runtime.kit.crypto import Vault
from runtime.signin.service.one_time import Kind, OneTimeSecrets

CONFIGURATION = "/.well-known/openid-configuration"
SCOPE = "openid email profile"
# Asymmetric only: `none`, and HMAC forged with a secret this gateway holds, never pass.
ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"]
REQUIRED_CLAIMS = ["iss", "aud", "exp", "iat", "sub"]
TIMEOUT_S = 5.0
# A provider's handshake waits ten minutes for its callback.
HANDSHAKE = Kind("st_", 600.0)

# A provider whose id_tokens name it in another spelling too: Google writes `iss` as
# `https://accounts.google.com` or as `accounts.google.com`, both its own (OpenID Connect at Google,
# "Validate an ID token").
ALSO_ISSUED_AS = {"https://accounts.google.com": ("accounts.google.com",)}


class NoSuchSignIn(ValidationError):
    """The state answers no sign-in begun here: a handshake is finished once, and dies in ten minutes."""

    def __init__(self) -> None:
        super().__init__("no sign-in answers to that: it was finished already, it expired, or it never started")


class OidcClient(Protocol):
    """What a sign-in at an OpenID provider needs of its client: an org's provider, or the platform's Google."""

    @property
    def issuer(self) -> str:
        """The provider, as its id_tokens name it."""
        ...

    @property
    def client_id(self) -> str:
        """This gateway, as the provider knows it."""
        ...

    @property
    def client_secret(self) -> str:
        """What proves the code exchange is this gateway's."""
        ...


@dataclass(frozen=True, slots=True)
class Handshake:
    """A sign-in at a provider, in flight: its state, nonce, verifier and where it returns."""

    state: str
    org: str | None
    nonce: str
    verifier: str
    redirect_uri: str
    pairing: str | None = None


def _load_handshake(value: Mapping[str, Any]) -> Handshake:
    return Handshake(
        state=str(value["state"]),
        org=value.get("org"),
        nonce=str(value["nonce"]),
        verifier=str(value["verifier"]),
        redirect_uri=str(value["redirect_uri"]),
        pairing=value.get("pairing"),
    )


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
    """Who a provider vouched for, from an id_token that checked out; the address folded."""

    subject: str
    email: str
    email_verified: bool
    name: str | None


@dataclass(frozen=True, slots=True)
class Answer:
    """What a provider's redirect brought back: the state it was sent, and a code or why there is none."""

    state: str
    code: str | None = None
    error: str | None = None


# One of four: signed in (a login code, and the terminal waiting if one is), refused (the sentence the
# console shows), or somebody nobody knows yet, sent to name their workspace.
@dataclass(frozen=True, slots=True)
class Landing:
    """Where a provider's callback leaves the browser."""

    login: str | None = None
    pairing: str | None = None
    refused: str | None = None
    newcomer: str | None = None


# What a provider answers, read here beside the client that asks it: its discovery document, its
# token endpoint's grant, and the claims of an id_token.
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


class Oidc:
    """The gateway as an OpenID Connect client: the handshakes in flight, and the HTTP it asks providers with."""

    # `resolve` is where a provider's names are checked to resolve onto the internet: the DNS, or a test's.
    def __init__(
        self,
        http: httpx.AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        vault: Vault,
        resolve: dns.ResolveUrl = dns.resolve_url,
    ) -> None:
        self.http = http
        self.resolve = resolve
        self.handshakes = OneTimeSecrets(HANDSHAKE, sessions, vault, load=_load_handshake, dump=asdict)

    async def discover(self, issuer: str) -> Endpoints:
        """The provider's endpoints, from its own discovery document."""
        address = await _public_address(self.resolve, issuer, issuer=issuer, field="issuer")
        try:
            answer = await dns.ask_at(self.http, "GET", f"{issuer}{CONFIGURATION}", address, timeout=TIMEOUT_S)
            answer.raise_for_status()
            payload = _Discovery.model_validate(answer.json())
        except (httpx.HTTPError, ValueError, PydanticValidationError):
            raise UpstreamError(
                f"{issuer} does not answer {CONFIGURATION}: not an OpenID provider, or down", vendor=issuer
            ) from None
        if payload.issuer != issuer:
            raise UpstreamError(
                f"{issuer} publishes a configuration naming {payload.issuer}: one of the two is wrong", vendor=issuer
            )
        methods = payload.token_endpoint_auth_methods_supported
        return Endpoints(
            issuer=issuer,
            authorization_endpoint=_endpoint(payload.authorization_endpoint, issuer, "authorization_endpoint"),
            token_endpoint=_endpoint(payload.token_endpoint, issuer, "token_endpoint"),
            jwks_uri=_endpoint(payload.jwks_uri, issuer, "jwks_uri"),
            basic_auth="client_secret_basic" in methods and "client_secret_post" not in methods,
        )

    async def begin(
        self,
        session: AsyncSession,
        client: OidcClient,
        redirect_uri: str,
        *,
        org: str | None,
        pairing: str | None,
        prompt: str | None = None,
    ) -> str:
        """A sign-in at a provider begun: a fresh state, nonce and PKCE verifier kept, and where the browser goes."""
        endpoints = await self.discover(client.issuer)
        begun = Handshake(
            state=self.handshakes.new_secret(),
            org=org,
            nonce=secrets.token_urlsafe(24),
            verifier=secrets.token_urlsafe(32),
            redirect_uri=redirect_uri,
            pairing=pairing,
        )
        await self.handshakes.keep_on(session, begun.state, begun)
        return authorization_url(endpoints, client, begun, prompt=prompt)

    async def resume(self, state: str) -> Handshake:
        """The handshake the state began, spent; NoSuchSignIn when it answers none."""
        begun = await self.handshakes.spend(state)
        if begun is None:
            raise NoSuchSignIn()
        return begun

    async def claims_for_code(self, client: OidcClient, begun: Handshake, code: str) -> Claims:
        """The person the provider signed in, their address verified, from the code it returned."""
        endpoints = await self.discover(client.issuer)
        id_token = await _exchange(self.http, self.resolve, endpoints, client, begun, code)
        claims = await _claims(self.http, self.resolve, endpoints, id_token, client.client_id, begun.nonce)
        if not claims.email:
            raise Unauthorized(f"{client.issuer} vouched for somebody it gave no email address for")
        if not claims.email_verified:
            raise Unauthorized(
                f"{client.issuer} has not verified {claims.email}: nobody is seated on an unverified address"
            )
        return claims


def authorization_url(endpoints: Endpoints, client: OidcClient, begun: Handshake, *, prompt: str | None = None) -> str:
    """Where the browser goes to sign in, with the state and the PKCE challenge."""
    challenge = base64.urlsafe_b64encode(hashlib.sha256(begun.verifier.encode()).digest()).decode().rstrip("=")
    asked = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": begun.redirect_uri,
        "scope": SCOPE,
        "state": begun.state,
        "nonce": begun.nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if prompt is not None:
        asked["prompt"] = prompt
    return str(httpx.URL(endpoints.authorization_endpoint).copy_merge_params(httpx.QueryParams(asked)))


def _reachable(url: str, *, issuer: str, field: str) -> str:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        raise Forbidden(f"{issuer}'s {field} is {url!r}: an endpoint is https, at a public name") from None
    if parsed.scheme != "https" or dns.is_local_name(parsed.host):
        raise Forbidden(f"{issuer}'s {field} is {url!r}: an endpoint is https, at a public name, never an address")
    return url


# A provider's name is resolved once, here, and asked at the address checked: until 2026-11 it was
# checked and then connected to by name, which a second answer of its DNS could point inside.
async def _public_address(resolve: dns.ResolveUrl, url: str, *, issuer: str, field: str) -> dns.Address:
    resolved = await resolve(_reachable(url, issuer=issuer, field=field))
    if not resolved.is_a_public_name:
        raise Forbidden(f"{issuer}'s {field} is {url!r}: it resolves inside, not on the internet")
    return resolved.addresses[0]


def _endpoint(found: str, issuer: str, field: str) -> str:
    if not found:
        raise UpstreamError(f"{issuer}'s configuration names no {field}", vendor=issuer)
    return _reachable(found, issuer=issuer, field=field)


async def _exchange(
    http: httpx.AsyncClient,
    resolve: dns.ResolveUrl,
    endpoints: Endpoints,
    client: OidcClient,
    begun: Handshake,
    code: str,
) -> str:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": begun.redirect_uri,
        "client_id": client.client_id,
        "code_verifier": begun.verifier,
    }
    if not endpoints.basic_auth:
        form["client_secret"] = client.client_secret
    token = endpoints.token_endpoint
    address = await _public_address(resolve, token, issuer=endpoints.issuer, field="token_endpoint")
    try:
        answer = await dns.ask_at(
            http,
            "POST",
            token,
            address,
            data=form,
            timeout=TIMEOUT_S,
            auth=(client.client_id, client.client_secret) if endpoints.basic_auth else None,
        )
    except httpx.HTTPError as unreachable:
        raise UpstreamError(
            f"{endpoints.issuer} refused the code exchange: {unreachable}", vendor=endpoints.issuer
        ) from None
    if answer.status_code >= httpx.codes.BAD_REQUEST:
        raise Unauthorized(f"{endpoints.issuer} refused the code exchange: HTTP {answer.status_code}")
    try:
        granted = _Granted.model_validate(answer.json())
    except (ValueError, PydanticValidationError):
        raise UpstreamError(
            f"{endpoints.issuer} answered the exchange without an id_token", vendor=endpoints.issuer
        ) from None
    if not granted.id_token:
        raise UpstreamError(f"{endpoints.issuer} answered the exchange without an id_token", vendor=endpoints.issuer)
    return granted.id_token


async def _claims(
    http: httpx.AsyncClient, resolve: dns.ResolveUrl, endpoints: Endpoints, id_token: str, client_id: str, nonce: str
) -> Claims:
    key = await _signing_key(http, resolve, endpoints, id_token)
    try:
        decoded = jwt.decode(
            id_token,
            key=key,
            algorithms=ALGORITHMS,
            audience=client_id,
            issuer=(endpoints.issuer, *ALSO_ISSUED_AS.get(endpoints.issuer, ())),
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
    # The address is folded here, once: nothing after the provider's answer spells it another way.
    return Claims(
        subject=data.sub,
        email=data.email.strip().lower(),
        email_verified=verified,
        name=data.name or data.given_name,
    )


async def _signing_key(
    http: httpx.AsyncClient, resolve: dns.ResolveUrl, endpoints: Endpoints, id_token: str
) -> jwt.PyJWK:
    address = await _public_address(resolve, endpoints.jwks_uri, issuer=endpoints.issuer, field="jwks_uri")
    try:
        answer = await dns.ask_at(http, "GET", endpoints.jwks_uri, address, timeout=TIMEOUT_S)
        answer.raise_for_status()
        published = jwt.PyJWKSet.from_dict(answer.json())
        kid = jwt.get_unverified_header(id_token).get("kid")
    except (httpx.HTTPError, ValueError, jwt.PyJWTError):
        raise UpstreamError(
            f"{endpoints.issuer} signed the id_token with a key its JWKS does not publish", vendor=endpoints.issuer
        ) from None
    matching = [key for key in published.keys if kid is None or key.key_id == kid]
    if len(matching) != 1:
        raise UpstreamError(
            f"{endpoints.issuer} signed the id_token with a key its JWKS does not publish", vendor=endpoints.issuer
        )
    return matching[0]
