"""Connections: an app a person lets act as them, the code it is sent back with, the key that code is exchanged for."""

import base64
import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.exceptions import OAuthRefusal
from runtime.kit.crypto import Vault, fingerprint
from runtime.signin.service import codes
from runtime.signin.service.clients import Client, Clients, check_redirect, host_of
from runtime.signin.service.one_time import Kind, OneTimeSecrets

# An app exchanges its code within the second it is sent back with it; five minutes covers a slow one.
AUTHORIZATION = Kind("pca_", 300.0)
# The one way a code is bound to the app that asked for it (RFC 7636): a hash, never the plain verifier.
THE_CHALLENGE_METHOD = "S256"
# What a connection opens: whatever the person's own key does. One word, so a consent screen has one to say.
SCOPE = "pinecall"


class InvalidRequest(OAuthRefusal):
    """The request lacks something every connection carries, or carries what none does."""

    def __init__(self, why: str) -> None:
        super().__init__("invalid_request", why)


class InvalidGrant(OAuthRefusal):
    """The code opens nothing: spent, expired, another app's, or not this verifier's."""

    def __init__(self, why: str) -> None:
        super().__init__("invalid_grant", why)


class UnsupportedGrant(OAuthRefusal):
    """A grant this gateway never gives: a connection is a person's approval, exchanged once."""

    def __init__(self, grant: str) -> None:
        super().__init__("unsupported_grant_type", f"{grant!r} is no grant of this gateway's: authorization_code alone")


@dataclass(frozen=True, slots=True)
class Asking:
    """What an app asks for: who it is, where it is sent back, the challenge its code is bound to, its own state."""

    client_id: str
    redirect_uri: str
    challenge: str
    method: str = THE_CHALLENGE_METHOD
    state: str | None = None


@dataclass(frozen=True, slots=True)
class Asked:
    """An app's request as the person approving reads it: its name, and where the approval lands."""

    client_name: str
    redirect_host: str


@dataclass(frozen=True, slots=True)
class Approval:
    """What a code holds until it is exchanged: the app it was given to, and the key the person's approval minted."""

    client_id: str
    redirect_uri: str
    challenge: str
    key: str


@dataclass(frozen=True, slots=True)
class Approved:
    """An approval on its way back: the app's address with the code, its state and this gateway's name."""

    redirect: str
    org: str


def _load_approval(value: Mapping[str, Any]) -> Approval:
    return Approval(value["client_id"], value["redirect_uri"], value["challenge"], value["key"])


class Connections:
    """The approvals waiting to be exchanged, each under the code its app was sent back with."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: Vault) -> None:
        self.codes = OneTimeSecrets(AUTHORIZATION, sessions, vault, load=_load_approval, dump=asdict)


async def read_asking(clients: Clients, asking: Asking) -> Asked:
    """Who is asking and where an approval would land, checked, for the person to read before approving."""
    client = await _check(clients, asking)
    return Asked(client.name, host_of(asking.redirect_uri))


# The key is written under the code in the transaction that mints it: an app sent back with a code
# whose approval was rolled back exchanges it for nothing.
async def approve(
    session: AsyncSession,
    connections: Connections,
    clients: Clients,
    asking: Asking,
    actor: Actor,
    *,
    issuer: str,
    org: str | None = None,
) -> Approved:
    """Let the app act as the person this browser is, in the org named or this one: where to send it, with its code."""
    client = await _check(clients, asking)
    if org is None or org == actor.org or actor.person is None:
        issued = await codes.another_device_key(session, actor, device=client.name)
    else:
        issued = await codes.key_into_org(session, actor.person, org, label=client.name)
    approval = Approval(asking.client_id, asking.redirect_uri, asking.challenge, issued.secret)
    minted = await connections.codes.mint_on(session, approval)
    answer = {"code": minted.code, "iss": issuer} | ({} if asking.state is None else {"state": asking.state})
    return Approved(_with(asking.redirect_uri, answer), issued.org)


async def exchange_form(connections: Connections, form: Mapping[str, str]) -> str:
    """The key for what an app posted to the token endpoint: its grant, its code, its verifier, who it is."""
    if form.get("grant_type") != "authorization_code":
        raise UnsupportedGrant(form.get("grant_type", ""))
    code, verifier, client_id = form.get("code"), form.get("code_verifier"), form.get("client_id")
    if not code or not verifier or not client_id:
        raise InvalidRequest("the exchange takes a code, its code_verifier and the client_id it was given to")
    return await exchange(connections, code, verifier, client_id, form.get("redirect_uri"))


async def exchange(connections: Connections, code: str, verifier: str, client_id: str, redirect_uri: str | None) -> str:
    """The key an approval minted, for the app the code was given to and the verifier of its challenge; once."""
    kept = await connections.codes.read_alive(code)
    if kept is None:
        raise InvalidGrant("that code opens nothing: it was exchanged already, it expired, or it never existed")
    approval = kept.value
    if approval.client_id != client_id or redirect_uri not in (None, approval.redirect_uri):
        raise InvalidGrant("that code was given to another app, or to another address of this one")
    if not hmac.compare_digest(challenge_of(verifier), approval.challenge):
        raise InvalidGrant("the code_verifier is not the one this code's challenge was made of")
    spent = await connections.codes.spend(code)
    if spent is None:
        raise InvalidGrant("that code opens nothing: it was exchanged already")
    return spent.key


async def disconnect(session: AsyncSession, cache: accounts.KeyCache, token: str) -> None:
    """The key an app holds, stopped at the app's own word; a token that is no key stops nothing (RFC 7009)."""
    await accounts.revoke_fingerprint(session, cache, fingerprint(token))


def challenge_of(verifier: str) -> str:
    """The S256 challenge a verifier answers to."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


async def _check(clients: Clients, asking: Asking) -> Client:
    if asking.method != THE_CHALLENGE_METHOD or not asking.challenge:
        raise InvalidRequest("a connection is asked for with a code_challenge, and code_challenge_method=S256")
    client = await clients.get_client(asking.client_id)
    check_redirect(client, asking.redirect_uri)
    return client


# The app's own query is kept: what an approval adds goes after it.
def _with(redirect_uri: str, answer: Mapping[str, str]) -> str:
    parts = urlsplit(redirect_uri)
    query = urlencode([*parse_qsl(parts.query, keep_blank_values=True), *answer.items()])
    return urlunsplit(parts._replace(query=query))
