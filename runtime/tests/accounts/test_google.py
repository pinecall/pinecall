"""Continue with Google: only a verified address of this sign-in passes, and it opens the account it already has."""

import ipaddress
import json
import os
import secrets
import time
from collections.abc import Iterator

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import google, members, orgs, signin
from pinecall_runtime.accounts.service.one_time import OneTimeSecrets
from pinecall_runtime.accounts.service.signin import Handshake
from pinecall_runtime.enums import MemberStatus, Role
from pinecall_runtime.exceptions import Forbidden, Unauthorized
from pinecall_runtime.kit import dns
from pinecall_runtime.kit.crypto import Vault
from tests.conftest import Tenant, needs_the_database

CLIENT = google.GoogleClient(client_id="suite.apps.googleusercontent.com", client_secret="a-secret")
DISCOVERY = f"{google.ISSUER}/.well-known/openid-configuration"
TOKEN = "https://oauth2.googleapis.com/token"
JWKS = "https://www.googleapis.com/oauth2/v3/certs"
SIGNING = rsa.generate_private_key(public_exponent=65537, key_size=2048)
BEGUN = Handshake(state="st_x", org=None, nonce="the-nonce", verifier="v" * 43, redirect_uri="https://voice.test/cb")


def resolves_to_the_internet(_host: str) -> list[dns.Address]:
    """Every name answers an address of Google's own, so the provider's endpoints read as public."""
    return [ipaddress.ip_address("142.250.64.100")]


@pytest.fixture
def at_google(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    """Google's discovery, token endpoint and keys, faked, at a name that resolves to the internet."""
    monkeypatch.setattr(dns, "resolve", resolves_to_the_internet)
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


async def test_a_verified_address_passes_under_either_spelling_of_googles_issuer(at_google: respx.MockRouter) -> None:
    """Google writes `iss` with or without https://; both are Google's, and the address comes back folded."""
    google_answers(at_google)
    vouched = await google.vouched_for(httpx.AsyncClient(), CLIENT, BEGUN, "a-code")
    assert vouched == google.Vouched("ana@gmail.com", "Ana Pérez")


async def test_an_address_google_has_not_verified_is_refused(at_google: respx.MockRouter) -> None:
    google_answers(at_google, email_verified=False)
    with pytest.raises(Unauthorized, match="not verified"):
        await google.vouched_for(httpx.AsyncClient(), CLIENT, BEGUN, "a-code")


async def test_an_id_token_of_another_sign_in_is_refused(at_google: respx.MockRouter) -> None:
    google_answers(at_google, nonce="somebody-elses")
    with pytest.raises(Unauthorized, match="nonce"):
        await google.vouched_for(httpx.AsyncClient(), CLIENT, BEGUN, "a-code")


async def test_an_id_token_for_another_client_is_refused(at_google: respx.MockRouter) -> None:
    google_answers(at_google, aud="another.apps.googleusercontent.com")
    with pytest.raises(Unauthorized, match="did not check out"):
        await google.vouched_for(httpx.AsyncClient(), CLIENT, BEGUN, "a-code")


# ── whom the address opens ──


@needs_the_database
async def test_an_address_nobody_knows_opens_nothing(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        assert await google.member_for(session, f"nobody-{secrets.token_hex(4)}@gmail.test") is None


@needs_the_database
async def test_a_member_with_a_password_signs_in_and_keeps_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Linking is automatic: the account the password opens is the one Google opens, the password untouched."""
    email = f"admin@{tenant.slug}.test"
    async with sessions.begin() as session:
        before = await members.password_hash_of(session, email)
        member = await google.member_for(session, email)
        assert member is not None and member.id == tenant.member
        assert await members.password_hash_of(session, email) == before is not None


@needs_the_database
async def test_somebody_invited_is_seated(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> None:
    """Google proved the address, as an org's own provider does: the invitation is taken, verified."""
    email = f"ben-{secrets.token_hex(3)}@{tenant.slug}.test"
    async with sessions.begin() as session:
        await members.invite(session, tenant.org, members.Invitee(email, "Ben", Role.qa), seats=None)
    async with sessions.begin() as session:
        member = await google.member_for(session, email)
        assert member is not None and member.status is MemberStatus.active and member.verified


@needs_the_database
async def test_a_member_disabled_everywhere_is_refused(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    email = f"cleo-{secrets.token_hex(3)}@{tenant.slug}.test"
    async with sessions.begin() as session:
        invited = (
            await members.invite(session, tenant.org, members.Invitee(email, "Cleo", Role.qa), seats=None)
        ).member
        await members.update_member(session, tenant.org, invited.id, members.Change(status=MemberStatus.disabled))
    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="disabled"):
            await google.member_for(session, email)


@needs_the_database
async def test_a_newcomers_org_is_made_with_no_password_and_a_verified_admin(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """What POST /v1/signup/google founds: the org, its admin seated verified, a key and the console's code."""
    email, slug = f"dana-{secrets.token_hex(3)}@gmail.test", f"dana-{secrets.token_hex(4)}"
    async with sessions.begin() as session:
        vault = Vault(os.environ["PINECALL_VAULT_KEY"])
        codes = OneTimeSecrets(*signin.LOGIN_CODE, TypeAdapter(signin.CodeHolder), sessions, vault)
        founding = signin.Founding(email, slug, "Dana", "Dana's workspace", hashed=None, vouched=True)
        founded = await signin.found_org(session, founding, codes)
        assert (founded.slug, founded.admin.status, founded.admin.verified) == (slug, MemberStatus.active, True)
        assert await members.password_hash_of(session, email) is None
        assert (await orgs.get_org(session, slug)).name == "Dana's workspace"
