"""The apps that ask to act as a person: one registered here, or one named by the document its id is the address of."""

import json
from dataclasses import dataclass
from typing import cast
from urllib.parse import SplitResult, urlsplit

import httpx

from runtime.exceptions import OAuthRefusal, ServiceUnavailable
from runtime.kit import dns
from runtime.kit.crypto import Vault

# A registration is its own id, sealed: the gateway keeps no row of an app nobody has approved yet,
# so a stranger registering a million of them writes nothing.
REGISTERED = "pcc_"
MOST_REDIRECTS = 10
LONGEST_NAME = 100
LONGEST_URI = 1000
LARGEST_DOCUMENT = 64 * 1024
TIMEOUT_S = 5.0
AN_UNNAMED_APP = "An app"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
# A browser runs what these name on the page that follows them: never where an approval is sent.
NEVER_A_REDIRECT = frozenset({"javascript", "data", "vbscript", "file", "about", "blob"})


class InvalidClient(OAuthRefusal):
    """The client id names no app: not one registered here, and no document that names itself."""

    def __init__(self, why: str) -> None:
        super().__init__("invalid_client", why)


class InvalidRedirect(OAuthRefusal):
    """The app may not be sent back there: an address it never registered, or one no approval goes to."""

    def __init__(self, why: str) -> None:
        super().__init__("invalid_redirect_uri", why)


@dataclass(frozen=True, slots=True)
class Client:
    """An app that asks to act as a person: its id, what it calls itself, and where it may be sent back."""

    id: str
    name: str
    redirect_uris: tuple[str, ...]


class Clients:
    """The apps that may ask: the ones registered here read from their own id, the others from their document."""

    # `resolve` is where a document's name is checked to resolve onto the internet: the DNS, or a test's.
    def __init__(self, http: httpx.AsyncClient, vault: Vault, resolve: dns.ResolveUrl = dns.resolve_url) -> None:
        self.http = http
        self.vault = vault
        self.resolve = resolve

    def register(self, name: str | None, redirect_uris: list[str]) -> Client:
        """An app registered: its id is its registration, sealed, and nothing is kept."""
        name, uris = _check_registration(name, redirect_uris)
        sealed = self.vault.seal(json.dumps({"name": name, "redirect_uris": list(uris)}))
        return Client(f"{REGISTERED}{sealed}", name, uris)

    async def get_client(self, client_id: str) -> Client:
        """The app an id names: a registration opened, or the document at the address the id is."""
        if client_id.startswith(REGISTERED):
            return self._open(client_id)
        if client_id.startswith("https://"):
            return await self._read_document(client_id)
        raise InvalidClient("no app answers to that client_id: register one, or name a client metadata document")

    def _open(self, client_id: str) -> Client:
        try:
            kept = json.loads(self.vault.open(client_id.removeprefix(REGISTERED)))
        except (ServiceUnavailable, ValueError):
            raise InvalidClient("that client_id is no registration of this gateway's: register again") from None
        return Client(client_id, kept["name"], tuple(kept["redirect_uris"]))

    # The name is resolved once and asked at the address checked, as an OpenID provider's is.
    async def _read_document(self, url: str) -> Client:
        if not urlsplit(url).path.strip("/"):
            raise InvalidClient("a client metadata document's address has a path: https://app.example/client.json")
        resolved = await self.resolve(url)
        if not resolved.is_a_public_name:
            raise InvalidClient(f"{url} resolves inside, not on the internet")
        try:
            answer = await dns.ask_at(self.http, "GET", url, resolved.addresses[0], timeout=TIMEOUT_S)
            answer.raise_for_status()
            if len(answer.content) > LARGEST_DOCUMENT:
                raise ValueError
            document: object = answer.json()
        except (httpx.HTTPError, ValueError):
            raise InvalidClient(f"{url} did not answer a client metadata document") from None
        said = cast("dict[str, object]", document) if isinstance(document, dict) else {}
        if said.get("client_id") != url:
            raise InvalidClient(f"the document at {url} does not say that address is its client_id")
        listed = said.get("redirect_uris")
        uris = [uri for uri in cast("list[object]", listed) if isinstance(uri, str)] if isinstance(listed, list) else []
        name = said.get("client_name")
        name, checked = _check_registration(name if isinstance(name, str) else None, uris)
        return Client(url, name, checked)


def check_redirect(client: Client, redirect_uri: str) -> str:
    """The address an approval is sent back to, when the app registered it; InvalidRedirect otherwise."""
    if redirect_uri in client.redirect_uris:
        return redirect_uri
    # An app on the person's own machine listens on whichever port was free (RFC 8252 section 7.3).
    asked = _split(redirect_uri)
    if asked.scheme == "http" and asked.hostname in LOOPBACK:
        for registered in map(_split, client.redirect_uris):
            if (registered.scheme, registered.hostname, registered.path) == (asked.scheme, asked.hostname, asked.path):
                return redirect_uri
    raise InvalidRedirect(f"{client.name} never registered {redirect_uri} as an address to be sent back to")


def host_of(redirect_uri: str) -> str:
    """Where an approval lands, as the person approving reads it: the host, or the app's own scheme."""
    parts = _split(redirect_uri)
    return parts.hostname or f"{parts.scheme}:"


def _check_registration(name: str | None, redirect_uris: list[str]) -> tuple[str, tuple[str, ...]]:
    if not redirect_uris or len(redirect_uris) > MOST_REDIRECTS:
        raise InvalidRedirect(f"an app registers between one and {MOST_REDIRECTS} redirect_uris")
    for uri in redirect_uris:
        _check_uri(uri)
    return (name or AN_UNNAMED_APP).strip()[:LONGEST_NAME] or AN_UNNAMED_APP, tuple(redirect_uris)


# https anywhere, http on the person's own machine alone, and an app's own scheme (cursor://, vscode://).
def _check_uri(uri: str) -> None:
    parts = _split(uri)
    plain = uri.isprintable() and " " not in uri and len(uri) <= LONGEST_URI
    if not plain or not parts.scheme or parts.fragment or parts.scheme in NEVER_A_REDIRECT:
        raise InvalidRedirect(f"{uri!r} is no address an approval can be sent to")
    if parts.scheme == "http" and parts.hostname not in LOOPBACK:
        raise InvalidRedirect(f"{uri} is plain http: only an app on the person's own machine is reached that way")
    if parts.scheme in ("http", "https") and not parts.hostname:
        raise InvalidRedirect(f"{uri!r} names no host")


def _split(uri: str) -> SplitResult:
    try:
        return urlsplit(uri)
    except ValueError:
        raise InvalidRedirect(f"{uri!r} is no address an approval can be sent to") from None
