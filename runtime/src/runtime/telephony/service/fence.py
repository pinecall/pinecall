"""Who the SFU admits a number's INVITE from: a number's fence, and the networks the cloud's firewall opens 5060 to."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv4Network, ip_network

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.scoping import box_wide
from runtime.telephony.models import NetworkState
from runtime.telephony.service import catalog, networks
from runtime.telephony.service.catalog import BOX_CARRIER, KNOWN
from runtime.telephony.service.networks import Standing

logger = logging.getLogger(__name__)

# Twilio's signalling edges, from the catalog: the fence of every Twilio number on the SFU, and the
# set the cloud firewall opens 5060 to. A test holds them equal.
TWILIO_SIGNALLING: tuple[str, ...] = KNOWN[BOX_CARRIER].networks
# Checked again at the list's end: a row the gateway let through still opens nothing this wide.
WIDEST_FOR_A_CARRIER = 16


@dataclass(frozen=True, slots=True)
class Fence:
    """Who the SFU admits a number's INVITE from: one trunk per fence."""

    trunk: str
    networks: tuple[str, ...]
    username: str = ""
    password: str = ""


# A trunk that lists no address admits every source: a fence with none approved is no trunk at all.
@dataclass(frozen=True, slots=True)
class Fenced:
    """The fence a number has with what is approved now, or what keeps it without one."""

    fence: Fence | None
    # The networks named for it that the operator has not answered, and the ones he refused.
    waiting: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()
    # Imported from an account the org has since let go, or one this box no longer opens: nothing
    # says where its calls come from, and it is admitted from nowhere until it is imported again.
    orphaned: bool = False


@dataclass(frozen=True, slots=True)
class Opening:
    """A network 5060 opens to, and why: a carrier's kind, or the org and what it asked for."""

    network: str
    reason: str


# No account holds it: bought on the box's account, hooked by the org or typed by the operator. It is
# no kind of carrier (it is not verified, not sealed, and has no id): with networks of its own, they
# are its fence once approved; with none, its catalog carrier's are, and Twilio's when it names none.
def fence_unaccounted(org: str, number: str, via: str | None, named: Sequence[str], standing: Standing) -> Fenced:
    """The fence of a number that lives in no account of the org."""
    if named:
        own = standing.sort(named)
        fence = Fence(trunk=f"{org}:{number}", networks=own.approved) if own.approved else None
        return Fenced(fence, waiting=own.waiting, refused=own.refused)
    kind = via or BOX_CARRIER
    trunk = org if kind == BOX_CARRIER else f"{org}:{kind}"
    return Fenced(Fence(trunk=trunk, networks=catalog.get_known(kind).networks))


async def list_openings(session: AsyncSession) -> list[Opening]:
    """Every network beyond Twilio's the fence opens to now, the catalog's first."""
    kinds = await catalog.list_admitted(session)
    found = [
        Opening(network=network, reason=carrier.kind)
        for carrier in catalog.CATALOG
        if carrier.kind in kinds and carrier.kind != BOX_CARRIER
        for network in carrier.networks
    ]
    with box_wide():
        slugs = {org.id: org.slug for org in await accounts.list_orgs(session)}
    found += [
        Opening(network=str(ask.network), reason=f"{slugs.get(ask.org, ask.org)}: {ask.source}")
        for ask in await networks.list_networks(session, NetworkState.approved)
    ]
    return [opening for opening in found if _is_narrow_enough(opening)]


def list_every_network(found: Sequence[Opening]) -> list[str]:
    """Twilio's networks and every opening: what the cloud's firewall admits to 5060."""
    return list(dict.fromkeys([*TWILIO_SIGNALLING, *(opening.network for opening in found)]))


def _is_narrow_enough(opening: Opening) -> bool:
    parsed = ip_network(opening.network, strict=False)
    widest = WIDEST_FOR_A_CARRIER if opening.reason in KNOWN else networks.WIDEST
    if not isinstance(parsed, IPv4Network) or parsed.prefixlen < widest:
        logger.warning("%s (%s) is not opened: wider than a /%d", opening.network, opening.reason, widest)
        return False
    return True
