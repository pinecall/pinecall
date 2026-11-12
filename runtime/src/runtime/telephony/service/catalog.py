"""The carriers a box knows, each with its published networks, and which of them its operator admits."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import Conflict, NotFound
from runtime.kit.text import a_list
from runtime.platform import service as platform

# The box's own carrier: always admitted, its networks are the cloud firewall's own set.
BOX_CARRIER = "twilio"


@dataclass(frozen=True, slots=True)
class KnownCarrier:
    """A carrier of the catalog: its published signalling networks, and whether it has an API."""

    kind: str
    name: str
    # The box has a client for its API (lists, points, buys numbers); the rest is SIP terms.
    has_api: bool
    networks: tuple[str, ...]
    # The carrier's own page the networks were read from, and the day they were.
    source: str
    read_on: date

    @property
    def how(self) -> str:
        """How an org brings a number through it: the box drives its API, or the org pastes SIP terms."""
        return "automatic" if self.has_api else "guided"


@dataclass(frozen=True, slots=True)
class Admission:
    """A carrier of the catalog as the box stands with it: admitted or not, and the numbers it brings."""

    carrier: KnownCarrier
    admitted: bool
    # The platform's own carrier: admitted always, its networks in the cloud firewall.
    fixed: bool
    # The numbers of every org that reach the box through it.
    numbers: int


# The catalog the box ships with, each carrier's networks as its page published them that day.
CATALOG = (
    KnownCarrier(
        kind="twilio",
        name="Twilio",
        has_api=True,
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
        has_api=False,
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
        has_api=False,
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
        has_api=False,
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


def get_known(kind: str) -> KnownCarrier:
    """The catalog's carrier of that kind; NotFound naming the ones there are."""
    found = KNOWN.get(kind)
    if found is None:
        raise NotFound(f"this box knows no carrier {kind}: one of {', '.join(KNOWN)}")
    return found


# The box's own carrier is admitted whatever the row says, and a kind the catalog lost is dropped.
def _load_admitted(value: Mapping[str, Any]) -> frozenset[str]:
    kinds = value.get("kinds")
    named = {kind for kind in (kinds if a_list(kinds) else []) if isinstance(kind, str) and kind in KNOWN}
    return frozenset(named | {BOX_CARRIER})


def _dump_admitted(kinds: frozenset[str]) -> dict[str, Any]:
    return {"kinds": sorted(kinds)}


# The box_settings row that says which carriers of the catalog the operator admits.
ADMITTED: platform.Setting[frozenset[str]] = platform.Setting("carriers/admitted", _load_admitted, _dump_admitted)


async def list_admitted(session: AsyncSession) -> frozenset[str]:
    """The kinds the operator admits, the box's own carrier always among them."""
    return await platform.find_setting(session, ADMITTED) or frozenset({BOX_CARRIER})


async def list_offered(session: AsyncSession) -> list[KnownCarrier]:
    """The carriers an org may bring a number through: the catalog's, admitted, in its order."""
    admitted = await list_admitted(session)
    return [carrier for carrier in CATALOG if carrier.kind in admitted]


# On, every org sees it under Add a number, and its networks join the fence's list for the cloud's
# firewall (`fence export`, then Terraform).
async def admit(session: AsyncSession, kind: str, *, on: bool) -> frozenset[str]:
    """Admit the carrier or stop admitting it; the kinds admitted after."""
    carrier = get_known(kind)
    if kind == BOX_CARRIER and not on:
        raise Conflict(f"{carrier.name} is the box's own carrier: it is always admitted")
    kinds = await list_admitted(session)
    after = frozenset(kinds | {kind} if on else kinds - {kind})
    await platform.put_setting(session, ADMITTED, after)
    return after
