"""The SFU brought level with the tables: every org at the start, one org when what fences its numbers changes."""

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import PinecallError
from runtime.fleet import service as fleet
from runtime.kit.crypto import Vault
from runtime.kit.loops import survive
from runtime.livekit import Servers
from runtime.scoping import box_wide
from runtime.telephony.models import NetworkState, Route
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service import accounts, carrier, hand_over, networks, sfu
from runtime.telephony.service.carrier import Carrier, SipNames
from runtime.telephony.service.fence import Fenced
from runtime.telephony.service.networks import Standing
from runtime.telephony.service.sfu import EnvRule

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Fencing:
    """What fences an org's numbers now: its accounts by id, and where the operator stands on its networks."""

    carriers: dict[str, Carrier]
    standings: dict[str, Standing]

    def fence_route(self, route: Route) -> Fenced:
        """The fence the org's number has now."""
        return carrier.fence_route(route, self.carriers.get(route.account or ""), self.standings)


@dataclass(frozen=True, slots=True)
class Rebuilt:
    """What a pass found: the numbers standing on the SFU, the orgs LiveKit refused."""

    numbers: int
    refused: list[str]
    # Whether the sandbox's own LiveKit admits the rings production hands over to it.
    hand_over: bool = False


class NotWhole(PinecallError):
    """A pass left orgs LiveKit refused: the loop says it, waits longer, and passes again."""

    status = 503


# A gateway started beside a LiveKit that is still starting, or down, would otherwise leave every
# number of that env unadmitted until its own next start: its loop passes again until nothing is
# owed. Until 2026-11 a pass that left one org refused rebuilt every org of the box again, once a
# minute, for ever: only what is owed is tried again, and a number this box cannot fence (its rows,
# not LiveKit, refuse it) is said once and owed by nobody.
@dataclass
class Owed:
    """What the SFU still owes the tables: every org at the start, then the ones LiveKit refused."""

    # None: every org that answers at a phone number, which nobody listed yet.
    orgs: list[str] | None = None

    @property
    def nothing(self) -> bool:
        """Whether the SFU stands as the tables say."""
        return self.orgs == []

    def settle(self, rebuilt: Rebuilt) -> None:
        """Keep what a pass left undone; NotWhole while an org is owed."""
        self.orgs = list(rebuilt.refused)
        if self.orgs:
            raise NotWhole(
                f"SIP is not rebuilt whole: LiveKit refused {len(self.orgs)} orgs, or cannot be reached; they "
                "are tried again"
            )


async def list_orgs_with_phones(session: AsyncSession) -> list[str]:
    """Every org that answers at a phone number, by id."""
    with box_wide():
        return await RouteRepository(session).list_orgs_with_phones()


# LiveKit keeps its trunks and rules in Redis, which can be emptied; the tables are the truth.
# Nothing is deleted but a number the other env's LiveKit still lists, and the carrier's side is
# never touched.
async def rebuild(session: AsyncSession, vault: Vault, servers: Servers, names: SipNames, owed: Owed) -> Rebuilt:
    """Admit the owed orgs' routed phone numbers again on the SFU, each with its fence and its env's rule."""
    standing, refused = 0, list[str]()
    orgs = await list_orgs_with_phones(session) if owed.orgs is None else owed.orgs
    for org in orgs:
        # An org LiveKit refuses is refused alone: the others' numbers are admitted all the same.
        with survive("admitting an org's numbers on the SFU", org) as admitting:
            standing += await readmit(session, vault, servers, org)
        if admitting.failed:
            refused.append(org)
    handing = False
    with survive("admitting the sandbox's hand-over trunk"):
        handing = await hand_over.admit_hand_overs(session, servers, names)
    logger.info(
        "SIP rebuilt from the tables: %d numbers stand, %d orgs refused, hand-overs admitted: %s",
        standing,
        len(refused),
        handing,
    )
    return Rebuilt(numbers=standing, refused=refused, hand_over=handing)


async def fencing_of(session: AsyncSession, vault: Vault, org: str) -> Fencing:
    """The org's accounts and where the operator stands on its networks, which fence its numbers now."""
    carriers = await accounts.list_carriers(session, vault, org)
    return Fencing(
        carriers={account.id: account for account in carriers}, standings=await networks.standings_of(session, org)
    )


# After the operator approves or refuses a network, or an account is brought: the org's trunks follow.
async def readmit(session: AsyncSession, vault: Vault, servers: Servers, org: str) -> int:
    """Admit the org's phone numbers again with the fences they have now; how many stand."""
    fleets = await fleet.get_fleets(session)
    fencing = await fencing_of(session, vault, org)
    admitted = 0
    for numbered in await RouteRepository(session).list_phones_of(org):
        admitted += await readmit_number(servers, numbered.route, fencing, fleets)
    return admitted


# A number lives on its env's LiveKit alone: the other env's, when it has its own, lets it go (a
# number moved, or one admitted there before the envs had a LiveKit each). On its own LiveKit the
# other env's rule lets it go first: two rules of one trunk never list one number. A number whose
# rows say no fence (a carrier the catalog lost) is said and left as it stands: asking LiveKit
# again would not mend it.
async def readmit_number(servers: Servers, route: Route, fencing: Fencing, fleets: fleet.Fleets) -> bool:
    """Admit the number on its env's LiveKit with the fence it has now; whether it stands."""
    org, number, env = route.org, route.number, route.env
    server, other = servers[env], sfu.other_server(servers, env)
    if other is not None:
        await sfu.let_go(other, org, number)
    try:
        fenced = fencing.fence_route(route)
    except PinecallError as unfenced:
        logger.warning("%s of org %s has no fence this box can read: %s", number, org, unfenced)
        return False
    if fenced.orphaned:
        logger.warning("%s of org %s was imported from an account that is gone: admitted from nowhere", number, org)
    if fenced.fence is None:
        await sfu.unlist(server, org, number)
        return False
    trunk_id = await sfu.admit(server, fenced.fence, await sfu.find_trunk(server, fenced.fence.trunk), number)
    left = await sfu.find_rule(server, sfu.rule_name(org, env.other))
    if left is not None and number in left.numbers:
        await sfu.renumber_rule(server, left, [listed for listed in left.numbers if listed != number])
    await sfu.rule_in(server, EnvRule(org, env, fleet.fleet_of(fleets, env)), [trunk_id], number)
    return True


# Bringing an account the org already holds replaces its secret; its party is asked first. A peer's
# networks are asked of the operator, and until he approves one the peer has no trunk.
async def bring_carrier(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, servers: Servers, brought: Carrier
) -> accounts.CarrierListed:
    """Keep an account of the org, verified; the networks it calls from asked for, and its trunks following."""
    calling = brought.calling_networks()
    for network in calling or ():
        networks.check_network(network)
    await brought.verify(http)
    kept = await accounts.put_carrier(session, vault, brought)
    if calling is not None:
        await networks.ask(session, kept.org, kept.id, calling)
        await readmit(session, vault, servers, kept.org)
    return await accounts.describe_carrier(session, kept)


async def approve_network(
    session: AsyncSession, vault: Vault, servers: Servers, ask_id: int, by: str
) -> networks.Asked:
    """Put the network on the firewall's list, and admit the org's numbers it fences."""
    return await decide_network(session, vault, servers, ask_id, NetworkState.approved, by)


async def refuse_network(session: AsyncSession, vault: Vault, servers: Servers, ask_id: int, by: str) -> networks.Asked:
    """Keep the network off the fence's list; numbers it alone fenced are let go of on the SFU."""
    return await decide_network(session, vault, servers, ask_id, NetworkState.refused, by)


async def decide_network(
    session: AsyncSession, vault: Vault, servers: Servers, ask_id: int, state: NetworkState, by: str
) -> networks.Asked:
    """The operator's answer to a network asked for, and the org's numbers it fences admitted or let go."""
    decided = await networks.decide(session, ask_id, state, by)
    with box_wide():
        await readmit(session, vault, servers, decided.org)
    return (await networks.name_orgs(session, [decided]))[0]
