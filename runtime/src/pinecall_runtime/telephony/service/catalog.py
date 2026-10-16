"""The carriers a box knows, which of them its operator admits, and the networks 5060 opens to."""

import logging
from dataclasses import dataclass
from datetime import date
from ipaddress import IPv4Network, ip_network

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.enums import NetworkState
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.text import a_list
from pinecall_runtime.platform import service as platform
from pinecall_runtime.telephony.service import networks

logger = logging.getLogger(__name__)

# The box_settings row that says which carriers of the catalog the operator admits.
ADMITTED = "carriers/admitted"
# The box's own carrier: always admitted, its networks are the cloud firewall's own set.
BOX_CARRIER = "twilio"
# Checked again at the list's end: a row the gateway let through still opens nothing this wide.
WIDEST_FOR_A_CARRIER = 16


@dataclass(frozen=True, slots=True)
class KnownCarrier:
    """A carrier of the catalog: its published signalling networks, and whether it has an API."""

    kind: str
    name: str
    # The box has a client for its API (lists, points, buys numbers); the rest is SIP terms.
    control: bool
    networks: tuple[str, ...]
    # The carrier's own page the networks were read from, and the day they were.
    source: str
    read_on: date


@dataclass(frozen=True, slots=True)
class Opening:
    """A network 5060 opens to, and why: a carrier's kind, or the org and what it asked for."""

    network: str
    reason: str


# The catalog the box ships with, each carrier's networks as its page published them that day.
CATALOG = (
    KnownCarrier(
        kind="twilio",
        name="Twilio",
        control=True,
        networks=(
            "54.172.60.0/30",
            "54.244.51.0/30",
            "54.171.127.192/30",
            "35.156.191.128/30",
            "54.65.63.192/30",
            "54.169.127.128/30",
            "54.252.254.64/30",
            "177.71.206.192/30",
        ),
        source="https://www.twilio.com/docs/sip-trunking/ip-addresses",
        read_on=date(2026, 10, 3),
    ),
    KnownCarrier(
        kind="telnyx",
        name="Telnyx",
        control=False,
        networks=(
            "192.76.120.10/32",
            "64.16.250.10/32",
            "185.246.41.140/32",
            "185.246.41.141/32",
            "103.115.244.145/32",
            "103.115.244.146/32",
            "192.76.120.31/32",
            "64.16.250.13/32",
            "185.246.42.128/32",
            "185.246.42.129/32",
            "103.115.244.158/32",
            "103.115.244.159/32",
        ),
        source="https://sip.telnyx.com/",
        read_on=date(2026, 10, 3),
    ),
    KnownCarrier(
        kind="vonage",
        name="Vonage",
        control=False,
        networks=(
            "216.147.0.1/32",
            "216.147.0.2/32",
            "216.147.1.1/32",
            "216.147.1.2/32",
            "216.147.2.1/32",
            "216.147.2.2/32",
            "216.147.3.1/32",
            "216.147.3.2/32",
            "216.147.4.1/32",
            "216.147.4.2/32",
            "216.147.5.1/32",
            "216.147.5.2/32",
        ),
        source="https://api.support.vonage.com/hc/en-us/articles/360035471331",
        read_on=date(2026, 10, 3),
    ),
    KnownCarrier(
        kind="plivo",
        name="Plivo",
        control=False,
        networks=(
            "13.52.9.0/25",
            "216.120.187.128/26",
            "18.214.109.128/25",
            "18.215.142.0/26",
            "204.89.148.128/26",
            "3.120.121.128/26",
            "18.228.70.64/26",
            "13.238.202.192/26",
        ),
        source="https://www.plivo.com/docs/sip-trunking/concepts/technical-specifications",
        read_on=date(2026, 10, 3),
    ),
)
KNOWN: dict[str, KnownCarrier] = {carrier.kind: carrier for carrier in CATALOG}


def known_carrier(kind: str) -> KnownCarrier:
    """The catalog's carrier of that kind; NotFound naming the ones there are."""
    found = KNOWN.get(kind)
    if found is None:
        raise NotFound(f"this box knows no carrier {kind}: one of {', '.join(KNOWN)}")
    return found


async def admitted_kinds(session: AsyncSession) -> frozenset[str]:
    """The kinds the operator admits, the box's own carrier always among them."""
    value = await platform.get_setting(session, ADMITTED)
    kinds = value.get("kinds") if value is not None else None
    chosen = {BOX_CARRIER}
    for kind in kinds if a_list(kinds) else []:
        if isinstance(kind, str) and kind in KNOWN:
            chosen.add(kind)
    return frozenset(chosen)


async def admit(session: AsyncSession, kind: str, *, on: bool) -> frozenset[str]:
    """Admit the carrier or stop admitting it; the kinds admitted after."""
    carrier = known_carrier(kind)
    if kind == BOX_CARRIER and not on:
        raise Conflict(f"{carrier.name} is the box's own carrier: it is always admitted")
    kinds = await admitted_kinds(session)
    after = sorted(kinds | {kind} if on else kinds - {kind})
    await platform.put_setting(session, ADMITTED, {"kinds": list(after)})
    return frozenset(after)


async def openings(session: AsyncSession) -> list[Opening]:
    """Every network beyond Twilio's the fence opens to now, the catalog's first."""
    kinds = await admitted_kinds(session)
    found = [
        Opening(network=network, reason=carrier.kind)
        for carrier in CATALOG
        if carrier.kind in kinds and carrier.kind != BOX_CARRIER
        for network in carrier.networks
    ]
    slugs = {org.id: org.slug for org in await orgs.list_orgs(session)}
    found += [
        Opening(network=ask.network, reason=f"{slugs.get(ask.org, ask.org)}: {ask.source}")
        for ask in await networks.listed(session, NetworkState.approved)
    ]
    return [opening for opening in found if _narrow_enough(opening)]


def every_network(found: list[Opening]) -> list[str]:
    """Twilio's networks and every opening: what the cloud's firewall admits to 5060."""
    return list(dict.fromkeys([*KNOWN[BOX_CARRIER].networks, *(opening.network for opening in found)]))


def _narrow_enough(opening: Opening) -> bool:
    parsed = ip_network(opening.network, strict=False)
    widest = WIDEST_FOR_A_CARRIER if opening.reason in KNOWN else networks.WIDEST
    if not isinstance(parsed, IPv4Network) or parsed.prefixlen < widest:
        logger.warning("%s (%s) is not opened: wider than a /%d", opening.network, opening.reason, widest)
        return False
    return True
