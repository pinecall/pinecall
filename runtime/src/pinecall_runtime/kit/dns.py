"""Names resolved, so what the box reaches on a tenant's word is held to the public internet."""

import ipaddress
import socket

import dns.exception
import dns.rdatatype
import dns.rdtypes.ANY.TXT
import dns.resolver

type Address = ipaddress.IPv4Address | ipaddress.IPv6Address

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
