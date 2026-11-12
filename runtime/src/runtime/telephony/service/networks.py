"""The networks an org asks the box to open 5060 to, and the operator's answer to each."""

from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv4Network, ip_network

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.exceptions import NotFound, ValidationError
from runtime.kit.time import now
from runtime.scoping import box_wide
from runtime.telephony.models import CarrierNetwork, NetworkState
from runtime.telephony.repository import CarrierNetworkRepository

# A carrier's edge is a few addresses; anything wider is a network nobody vouches for.
WIDEST = 24


@dataclass(frozen=True, slots=True)
class Standing:
    """Where the operator stands on the networks one source asked for."""

    approved: tuple[str, ...] = ()
    waiting: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()

    # A network named and never asked for waits too: nobody approved it.
    def sort(self, named: Sequence[str]) -> "Standing":
        """Of the networks named for a fence, written as the table writes them: approved, refused, and the rest."""
        written = tuple(network_text(network) for network in named)
        return Standing(
            approved=tuple(network for network in written if network in self.approved),
            waiting=tuple(network for network in written if network not in self.approved + self.refused),
            refused=tuple(network for network in written if network in self.refused),
        )


NOTHING_ASKED = Standing()


@dataclass(frozen=True, slots=True)
class NetworkListed:
    """A network a source of the org calls from, and whether the box's operator admitted it."""

    network: str
    state: str


@dataclass(frozen=True, slots=True)
class Asked:
    """A network an org asked 5060 to open to, and the org as the operator reads it: by its slug."""

    row: CarrierNetwork
    org: str


def check_network(network: str) -> str:
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


async def ask(session: AsyncSession, org: str, source: str, networks: Sequence[str]) -> Sequence[CarrierNetwork]:
    """Ask for these networks for the source, forgetting the ones it no longer names; its rows."""
    wanted = [check_network(network) for network in networks]
    return await CarrierNetworkRepository(session).ask(org, source, wanted)


async def list_of_org(session: AsyncSession, org: str) -> Sequence[CarrierNetwork]:
    """Every network the org asked for, oldest first."""
    return await CarrierNetworkRepository(session).list_of_org(org)


async def list_of_source(session: AsyncSession, org: str, source: str) -> list[NetworkListed]:
    """The networks one source of the org asked for, oldest first, each with the operator's answer."""
    rows = await CarrierNetworkRepository(session).list_of_source(org, source)
    return [NetworkListed(network=str(row.network), state=row.state.value) for row in rows]


async def standings_of(session: AsyncSession, org: str) -> dict[str, Standing]:
    """Where the operator stands on the networks of each source of the org."""
    found: dict[str, dict[NetworkState, tuple[str, ...]]] = {}
    for row in await list_of_org(session, org):
        of_source = found.setdefault(row.source, {})
        of_source[row.state] = (*of_source.get(row.state, ()), str(row.network))
    return {
        source: Standing(
            approved=states.get(NetworkState.approved, ()),
            waiting=states.get(NetworkState.waiting, ()),
            refused=states.get(NetworkState.refused, ()),
        )
        for source, states in found.items()
    }


async def list_networks(session: AsyncSession, state: str | None = None) -> Sequence[CarrierNetwork]:
    """Every network asked for on the box, or those in one state, oldest first, of every org."""
    with box_wide():
        return await CarrierNetworkRepository(session).list_in_state(None if state is None else NetworkState(state))


async def list_asked(session: AsyncSession, state: str | None = None) -> list[Asked]:
    """Every network asked for on the box, or those in one state, oldest first, each with its org's slug."""
    return await name_orgs(session, await list_networks(session, state))


async def name_orgs(session: AsyncSession, rows: Sequence[CarrierNetwork]) -> list[Asked]:
    """Each network asked for with the slug of the org that asked."""
    with box_wide():
        slugs = {org.id: org.slug for org in await accounts.list_orgs(session)}
    return [Asked(row, slugs.get(row.org, row.org)) for row in rows]


async def decide(session: AsyncSession, ask_id: int, state: NetworkState, by: str) -> CarrierNetwork:
    """Approve or refuse a network asked for, whatever org asked; NotFound for an id nobody asked with."""
    repository = CarrierNetworkRepository(session)
    with box_wide():
        row = await repository.find(ask_id)
        if row is None:
            raise NotFound(f"no network was asked for with id {ask_id}")
        return await repository.decide(row, state, by, now())
