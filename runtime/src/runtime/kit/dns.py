"""Names resolved, so what the box reaches on a tenant's word is held to the public internet."""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import dns.exception
import dns.rdatatype
import dns.rdtypes.ANY.TXT
import dns.resolver
import httpx

type Address = ipaddress.IPv4Address | ipaddress.IPv6Address

# Every address a name resolves to now: the box's DNS, or what a test hands in for a name of its own.
type Resolve = Callable[[str], list[Address]]

# `.svc`: a cluster's own services.
LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".arpa", ".home", ".lan", ".svc")
# A TXT lookup waits this long in all, over every nameserver tried.
TXT_WITHIN_S = 5.0


def resolve(host: str) -> list[Address]:
    """Every address the name resolves to now; OSError when it resolves to none."""
    found = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [ipaddress.ip_address(str(item[4][0]).partition("%")[0]) for item in found]


def all_public(addresses: list[Address]) -> bool:
    """Whether there is at least one address and every one is on the public internet."""
    return bool(addresses) and all(address.is_global for address in addresses)


def all_private(addresses: list[Address]) -> bool:
    """Whether there is at least one address and every one is private or loopback."""
    return bool(addresses) and all(a.is_private or a.is_loopback for a in addresses)


def is_an_address(host: str) -> bool:
    """Whether the host is an IP address rather than a name."""
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def is_local_name(host: str) -> bool:
    """A name the box itself answers to, or an address: never fetched on a tenant's word."""
    folded = host.lower().rstrip(".")
    return folded in {"localhost", ""} or folded.endswith(LOCAL_SUFFIXES) or is_an_address(folded)


# The one resolution before the box reaches a URL on a tenant's word (a webhook, a collector, a sign-in
# provider). Whoever asked decides on what this answers and refuses in its own sentence; and whoever
# then connects, connects to an address this returned (`post_at`), never to the name again, or a
# second resolution could answer with the inside.
@dataclass(frozen=True, slots=True)
class Resolved:
    """A URL's host, and every address it resolves to now: none when it resolves to nothing."""

    host: str
    addresses: tuple[Address, ...]

    @property
    def is_public(self) -> bool:
        """Whether the host resolves, and to the public internet alone."""
        return all_public(list(self.addresses))

    @property
    def is_a_public_name(self) -> bool:
        """Whether the host is a name, none of the box's own and no address, that resolves to the internet alone."""
        return not is_local_name(self.host) and self.is_public


# What finds where a URL's host resolves now: `resolve_url`, or what a test hands in its place.
type ResolveUrl = Callable[[str], Awaitable[Resolved]]


async def resolve_url(url: str) -> Resolved:
    """The host a URL names and what it resolves to now, resolved off the event loop."""
    host = (urlsplit(url).hostname or "").lower()
    try:
        found = await asyncio.to_thread(resolve, host) if host else []
    except OSError:
        found = []
    return Resolved(host, tuple(found))


# The address was checked; the name was not asked again. The name rides the Host header, and TLS is
# still asked for it and verified against it (`sni_hostname`). The connection is closed after the
# answer, so one verified for a name is never reused for another name at the same address. A client
# that follows no redirect is the caller's to bring.
async def ask_at(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    address: Address,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    content: bytes | None = None,
    data: Mapping[str, str] | None = None,
    auth: tuple[str, str] | None = None,
) -> httpx.Response:
    """Ask the URL at the address its host was checked to resolve to, never at the name again."""
    named = httpx.URL(url)
    return await http.request(
        method,
        named.copy_with(host=str(address)),
        content=content,
        data=data,
        auth=httpx.USE_CLIENT_DEFAULT if auth is None else auth,
        headers={**(headers or {}), "host": named.netloc.decode("ascii"), "connection": "close"},
        extensions={"sni_hostname": named.raw_host.decode("ascii")},
        timeout=timeout,
    )


async def post_at(
    http: httpx.AsyncClient, url: str, address: Address, *, content: bytes, headers: Mapping[str, str], timeout: float
) -> httpx.Response:
    """POST to the URL at the address its host was checked to resolve to."""
    return await ask_at(http, "POST", url, address, timeout=timeout, headers=headers, content=content)


# A record of several strings is one text, as the RFC reads it.
def txt_records(name: str) -> list[str]:
    """Every TXT record at the name, each as one string; none when there is none or no answer."""
    try:
        answer = dns.resolver.resolve(name, dns.rdatatype.TXT, lifetime=TXT_WITHIN_S)
    except dns.exception.DNSException:
        return []
    return [
        b"".join(rdata.strings).decode("utf-8", errors="replace")
        for rdata in answer
        if isinstance(rdata, dns.rdtypes.ANY.TXT.TXT)
    ]
