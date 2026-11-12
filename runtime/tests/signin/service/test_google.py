"""Continue with Google: only a verified address of this sign-in passes, and it opens the account it already has."""

import ipaddress
import json
import os
import secrets
import time
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlsplit

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import actor, invitations, members, people
from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import MemberStatus, Role
from runtime.exceptions import Forbidden, Unauthorized
from runtime.kit import dns
from runtime.kit.crypto import Vault
from runtime.signin.service import google
from runtime.signin.service.oidc import Handshake, Oidc
from tests.conftest import Tenant, needs_the_database

CLIENT = google.GoogleClient(client_id="suite.apps.googleusercontent.com", client_secret="a-secret")
DISCOVERY = f"{google.ISSUER}/.well-known/openid-configuration"
TOKEN = "https://oauth2.googleapis.com/token"
JWKS = "https://www.googleapis.com/oauth2/v3/certs"
SIGNING = rsa.generate_private_key(public_exponent=65537, key_size=2048)
BEGUN = Handshake(state="st_x", org=None, nonce="the-nonce", verifier="v" * 43, redirect_uri="https://voice.test/cb")


# Google's names are faked here, so they are said to resolve to an address of Google's own: the
# provider's endpoints read as public, as Google's do.
async def resolves_to_the_internet(url: str) -> dns.Resolved:
    """The URL's host, on an address of Google's own."""
    return dns.Resolved(urlsplit(url).hostname or "", (ipaddress.ip_address("142.250.64.100"),))


@pytest.fixture
async def oidc(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[Oidc]:
    """The gateway as an OpenID client, its names resolved onto the internet."""
    async with httpx.AsyncClient() as http:
        yield Oidc(http, sessions, Vault(os.environ["PINECALL_VAULT_KEY"]), resolve=resolves_to_the_internet)


@pytest.fixture
def at_google() -> Iterator[respx.MockRouter]:
    """Google's discovery, token endpoint and keys, faked."""
    public: dict[str, object] = json.loads(RSAAlgorithm.to_jwk(SIGNING.public_key()))
    with respx.mock(assert_all_called=False) as router:
        router.get(DISCOVERY).respond(
            json={
                "issuer": google.ISSUER,
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_endpoint": TOKEN,
                "jwks_uri": JWKS,
                "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            }
        )
        router.get(JWKS).respond(json={"keys": [{**public, "kid": "k1", "alg": "RS256", "use": "sig"}]})
        yield router


def google_answers(router: respx.MockRouter, **claims: object) -> None:
    """Google's token endpoint hands back an id_token saying these claims over a verified address."""
    now = int(time.time())
    said = {
        "iss": "accounts.google.com",
        "aud": CLIENT.client_id,
        "sub": "1077",
        "iat": now,
        "exp": now + 600,
        "nonce": BEGUN.nonce,
        "email": "Ana@Gmail.com",
        "email_verified": True,
        "name": "Ana Pérez",
        **claims,
    }
    signed = jwt.encode(said, SIGNING, algorithm="RS256", headers={"kid": "k1"})
    router.post(TOKEN).respond(json={"id_token": signed, "access_token": "unused"})


async def test_a_verified_address_passes_under_either_spelling_of_googles_issuer(
    at_google: respx.MockRouter, oidc: Oidc
) -> None:
    """Google writes `iss` with or without https://; both are Google's, and the address comes back folded."""
    google_answers(at_google)
    vouched = await google.exchange_code(oidc, CLIENT, BEGUN, "a-code")
    assert vouched == google.Vouched("ana@gmail.com", "Ana Pérez")


async def test_an_address_google_has_not_verified_is_refused(at_google: respx.MockRouter, oidc: Oidc) -> None:
    google_answers(at_google, email_verified=False)
    with pytest.raises(Unauthorized, match="not verified"):
        await google.exchange_code(oidc, CLIENT, BEGUN, "a-code")


async def test_an_id_token_of_another_sign_in_is_refused(at_google: respx.MockRouter, oidc: Oidc) -> None:
    google_answers(at_google, nonce="somebody-elses")
    with pytest.raises(Unauthorized, match="nonce"):
        await google.exchange_code(oidc, CLIENT, BEGUN, "a-code")


async def test_an_id_token_for_another_client_is_refused(at_google: respx.MockRouter, oidc: Oidc) -> None:
    google_answers(at_google, aud="another.apps.googleusercontent.com")
    with pytest.raises(Unauthorized, match="did not check out"):
        await google.exchange_code(oidc, CLIENT, BEGUN, "a-code")


# ── whom the address opens ──


@needs_the_database
async def test_an_address_nobody_knows_opens_nothing(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache
) -> None:
    async with sessions.begin() as session:
        assert await google.member_for(session, key_cache, f"nobody-{secrets.token_hex(4)}@gmail.test") is None


@needs_the_database
async def test_a_member_who_proved_their_address_signs_in_and_keeps_their_password(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """Linking is automatic: the account the password opens is the one Google opens, the password untouched."""
    email = f"admin@{tenant.slug}.test"
    async with sessions.begin() as session:
        person = await people.find_person(session, email)
        assert person is not None
        await people.prove_mailbox(session, key_cache, person, presented_password=True)
    async with sessions.begin() as session:
        before = await password_hash_of(session, email)
        member = await google.member_for(session, key_cache, email)
        assert member is not None and member.id == tenant.member
    async with sessions() as session:
        assert await password_hash_of(session, email) == before is not None


# Until 2026-11-11 Google opened the account and left the password as it was. A password set while
# the address was unproven may be somebody else's (an admin of another org typed it): Google's proof,
# which presented no password, ends it and the keys it opened.
@needs_the_database
async def test_a_password_set_while_the_address_was_unproven_ends_when_google_proves_it(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    email = f"admin@{tenant.slug}.test"
    async with sessions.begin() as session:
        member = await google.member_for(session, key_cache, email)
        assert member is not None and member.id == tenant.member
    async with sessions() as session:
        assert await password_hash_of(session, email) is None
        assert await actor.verify_key(session, tenant.person_key) is None


@needs_the_database
async def test_somebody_invited_is_seated(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """Google proved the address, as an org's own provider does: the invitation is taken, verified."""
    email = f"ben-{secrets.token_hex(3)}@{tenant.slug}.test"
    async with sessions.begin() as session:
        await invitations.invite(session, tenant.org, invitations.Invitee(email, "Ben", Role.qa), held_to_seats=False)
    async with sessions.begin() as session:
        assert await google.member_for(session, key_cache, email) is not None
    async with sessions() as session:
        seated = await members.get_member_by_email(session, tenant.org, email)
        assert seated.status is MemberStatus.active and seated.verified


@needs_the_database
async def test_a_member_disabled_everywhere_is_refused(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    email = f"cleo-{secrets.token_hex(3)}@{tenant.slug}.test"
    async with sessions.begin() as session:
        invitee = invitations.Invitee(email, "Cleo", Role.qa)
        invited = (await invitations.invite(session, tenant.org, invitee, held_to_seats=False)).membership
        await members.update_member(session, key_cache, invited, members.Change(status=MemberStatus.disabled))
    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="disabled"):
            await google.member_for(session, key_cache, email)


async def password_hash_of(session: AsyncSession, email: str) -> str | None:
    """The hash of the password the address's person keeps, or None."""
    person = await people.find_person(session, email)
    return None if person is None else person.password_hash
