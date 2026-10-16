"""The networks an org asks the box to open 5060 to, and the operator's answer to each."""

from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv4Network, ip_network

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import NetworkState
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.telephony.models import CarrierNetwork
from pinecall_runtime.telephony.repository import CarrierNetworkRepository

# A carrier's edge is a few addresses; anything wider is a network nobody vouches for.
WIDEST = 24


@dataclass(frozen=True, slots=True)
class NetworkAsk:
    """A network an org asked for: what asked, the network, and where the operator stands on it."""

    id: int
    org: str
    source: str
    network: str
    state: NetworkState
    asked_at: float
    decided_by: str | None
    decided_at: float | None


def checked(network: str) -> str:
    """The network written the one way, or ValidationError saying why it cannot be admitted."""
    try:
        parsed = ip_network(network.strip(), strict=False)
    except ValueError:
        raise ValidationError(f"{network} is not an IPv4 address or network, like 198.51.100.7/32") from None
    if not isinstance(parsed, IPv4Network):
        raise ValidationError(f"{network} is not an IPv4 address or network, like 198.51.100.7/32")
    if parsed.prefixlen < WIDEST:
        raise ValidationError(f"{parsed} is wider than a /{WIDEST}: name the addresses your PBX or carrier calls from")
    if not parsed.is_global:
        raise ValidationError(f"{parsed} is not a public address: a carrier reaches the box from the internet")
    return str(parsed)


def network_text(network: str) -> str:
    """The network as the table writes it (an address is a /32), or as given when it is none."""
    try:
        return str(ip_network(network.strip(), strict=False))
    except ValueError:
        return network


async def ask(session: AsyncSession, org: str, source: str, networks: Sequence[str]) -> list[NetworkAsk]:
    """Ask for these networks for the source, forgetting the ones it no longer names; its rows."""
    wanted = [checked(network) for network in networks]
    return [_ask(row) for row in await CarrierNetworkRepository(session).ask(org, source, wanted)]


async def of_org(session: AsyncSession, org: str) -> list[NetworkAsk]:
    """Every network the org asked for, oldest first."""
    return [_ask(row) for row in await CarrierNetworkRepository(session).of_org(org)]


async def approved(session: AsyncSession, org: str) -> dict[str, tuple[str, ...]]:
    """The networks approved for each source of the org."""
    found: dict[str, tuple[str, ...]] = {}
    for row in await of_org(session, org):
        if row.state is NetworkState.approved:
            found[row.source] = (*found.get(row.source, ()), row.network)
    return found


async def listed(session: AsyncSession, state: NetworkState | None = None) -> list[NetworkAsk]:
    """Every network asked for on the box, or those in one state, oldest first."""
    return [_ask(row) for row in await CarrierNetworkRepository(session).listed(state)]


async def decide(session: AsyncSession, ask_id: int, state: NetworkState, by: str) -> NetworkAsk:
    """Approve or refuse a network asked for; NotFound for an id nobody asked with."""
    repository = CarrierNetworkRepository(session)
    row = await repository.get(ask_id)
    if row is None:
        raise NotFound(f"no network was asked for with id {ask_id}")
    return _ask(await repository.decide(row, state, by))


def _ask(row: CarrierNetwork) -> NetworkAsk:
    return NetworkAsk(
        id=row.id,
        org=row.org,
        source=row.source,
        network=str(row.network),
        state=row.state,
        asked_at=row.asked_at.timestamp(),
        decided_by=row.decided_by,
        decided_at=None if row.decided_at is None else row.decided_at.timestamp(),
    )
