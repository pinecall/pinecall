"""The SFU's side of a number: a trunk per fence, a rule per env, the rebuild, trunks pointed."""

import asyncio
import logging
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx
from livekit import api
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    CreateSIPInboundTrunkRequest,
    DeleteSIPDispatchRuleRequest,
    DeleteSIPTrunkRequest,
    ListSIPDispatchRuleRequest,
    ListSIPInboundTrunkRequest,
    SIPDispatchRule,
    SIPDispatchRuleIndividual,
    SIPDispatchRuleInfo,
    SIPInboundTrunkInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.livekit import NO_LIVEKIT
from pinecall_runtime.telephony.schemas import LegTrunk
from pinecall_runtime.telephony.service import accounts, hand_over, networks, records
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.fence import (
    Fence,
    declared_networks,
    fence_of,
    own_networks,
)
from pinecall_runtime.telephony.service.records import RouteRecord
from pinecall_runtime.telephony.service.twilio import origination_uri, twilio_of
from pinecall_runtime.wire.dispatch import Dispatch

logger = logging.getLogger(__name__)

ROOM_PREFIX = "call-"
NO_DOMAIN = "this box has no PINECALL_DOMAIN: a carrier has nowhere to send a call"
# A LiveKit still starting beside the gateway answers in seconds; one that is down, in minutes.
FIRST_WAIT_S = 2.0
LONGEST_WAIT_S = 60.0
# How long the start waits for production's SIP name to say its address.
RESOLVED_WITHIN_S = 5.0


@dataclass(frozen=True, slots=True)
class EnvRule:
    """An org's env on the SFU: its rule, and the fleet the rule dispatches."""

    org: str
    env: Env
    fleet: str


@dataclass(frozen=True, slots=True)
class Fencing:
    """What fences an org's numbers now: its carriers by id, and the networks approved."""

    carriers: dict[str, CarrierAccount]
    approved: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Rebuilt:
    """What the reconcile found: numbers existing on the SFU, orgs it could not rebuild."""

    numbers: int
    refused: list[str]
    # Whether the sandbox's own LiveKit admits the rings production hands over to it.
    hand_over: bool = False


@dataclass(frozen=True, slots=True)
class Repointed:
    """A trunk of an account that sent an env's calls to one URI and now sends them to another."""

    account: str
    trunk: str
    world: Env
    was: str
    now: str


def domain_of(handles: Handles) -> str:
    """The box's name, or ServiceUnavailable: a carrier has nowhere to send a call."""
    name = handles.settings.domain
    if not name:
        raise ServiceUnavailable(NO_DOMAIN)
    return name


def sip_domain_of(handles: Handles, env: Env) -> str:
    """The name a carrier sends that env's calls to, or ServiceUnavailable: it has none."""
    name = handles.settings.sip_domain_of(env)
    if not name:
        raise ServiceUnavailable(NO_DOMAIN)
    return name


# Both envs hold the one client when the sandbox has no LiveKit of its own.
def elsewhere(handles: Handles, env: Env) -> api.LiveKitAPI | None:
    """The other env's LiveKit when it is not this env's too; None where both share one."""
    other = handles.servers[_other(env)]
    return None if other is handles.servers[env] else other


def rule_name(org: str, env: Env) -> str:
    """The name of an org's dispatch rule in an env."""
    return f"{org}:{env}"


# An org id holds no colon, so `{org}` and `{org}:…` can never be another org's.
def belongs_to(name: str, org: str) -> bool:
    """Whether a trunk or rule name is the org's."""
    return name == org or name.startswith(f"{org}:")


async def trunks_admitting(server: api.LiveKitAPI, number: str) -> list[SIPInboundTrunkInfo]:
    """Every trunk on the SFU that lists the number."""
    listed = await server.sip.list_inbound_trunk(ListSIPInboundTrunkRequest(numbers=[number]))
    return [trunk for trunk in listed.items if number in trunk.numbers]


async def trunk_named(server: api.LiveKitAPI, name: str) -> SIPInboundTrunkInfo | None:
    """The trunk of that name, or None."""
    listed = await server.sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
    return next((trunk for trunk in listed.items if trunk.name == name), None)


async def rule_named(server: api.LiveKitAPI, name: str) -> SIPDispatchRuleInfo | None:
    """The dispatch rule of that name, or None."""
    listed = await server.sip.list_dispatch_rule(ListSIPDispatchRuleRequest())
    return next((rule for rule in listed.items if rule.name == name), None)


async def admit(server: api.LiveKitAPI, fence: Fence, existing: SIPInboundTrunkInfo | None, number: str) -> str:
    """Make the fence's trunk list the number, made or updated; its id."""
    if existing is None:
        info = SIPInboundTrunkInfo(
            name=fence.trunk,
            numbers=[number],
            allowed_addresses=list(fence.networks),
            auth_username=fence.username,
            auth_password=fence.password,
        )
        made = await server.sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=info))
        return made.sip_trunk_id
    fenced = sorted(existing.allowed_addresses) == sorted(fence.networks)
    if number in existing.numbers and fenced and existing.auth_username == fence.username:
        return existing.sip_trunk_id
    existing.numbers[:] = sorted({*existing.numbers, number})
    existing.allowed_addresses[:] = list(fence.networks)
    existing.auth_username, existing.auth_password = fence.username, fence.password
    await server.sip.update_inbound_trunk(existing.sip_trunk_id, existing)
    return existing.sip_trunk_id


# A trunk or a rule that lists no number takes every number: one emptied is deleted, and so is
# a rule left with no trunk.
async def renumber_trunk(server: api.LiveKitAPI, org: str, trunk: SIPInboundTrunkInfo, numbers: list[str]) -> None:
    """Leave the trunk these numbers; emptied, it goes, and so does a rule left with no trunk."""
    if numbers:
        await server.sip.update_inbound_trunk_fields(trunk.sip_trunk_id, numbers=numbers)
        return
    await server.sip.delete_trunk(DeleteSIPTrunkRequest(sip_trunk_id=trunk.sip_trunk_id))
    listed = await server.sip.list_dispatch_rule(ListSIPDispatchRuleRequest())
    for rule in listed.items:
        if not belongs_to(rule.name, org) or trunk.sip_trunk_id not in rule.trunk_ids:
            continue
        kept = [trunk_id for trunk_id in rule.trunk_ids if trunk_id != trunk.sip_trunk_id]
        if not kept:
            await renumber_rule(server, rule, [])
            continue
        rule.trunk_ids[:] = kept
        await server.sip.update_dispatch_rule(rule.sip_dispatch_rule_id, rule)


# One rule per env: its `numbers` are that env's, so a number changes env between two lists and
# never between trunks. livekit refuses two rules of one trunk listing one number.
async def rule_in(server: api.LiveKitAPI, env_rule: EnvRule, trunks: Sequence[str], number: str) -> None:
    """Have the env's rule list the number and the trunks, made or updated."""
    # A rule with no trunk dispatches every trunk's calls.
    if not trunks:
        return
    name, fleet_name = rule_name(env_rule.org, env_rule.env), env_rule.fleet
    existing = await rule_named(server, name)
    agent_dispatch = RoomAgentDispatch(
        agent_name=fleet_name, metadata=Dispatch(org=env_rule.org, env=env_rule.env).dump()
    )
    if existing is None:
        info = SIPDispatchRuleInfo(
            name=name,
            trunk_ids=sorted(set(trunks)),
            numbers=[number],
            rule=SIPDispatchRule(dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix=ROOM_PREFIX)),
            room_config=RoomConfiguration(agents=[agent_dispatch]),
        )
        await server.sip.create_dispatch_rule(CreateSIPDispatchRuleRequest(dispatch_rule=info))
        return
    wanted_trunks = sorted({*existing.trunk_ids, *trunks})
    fleets = [agent.agent_name for agent in existing.room_config.agents]
    if number in existing.numbers and list(existing.trunk_ids) == wanted_trunks and fleets == [fleet_name]:
        return
    existing.trunk_ids[:] = wanted_trunks
    existing.numbers[:] = sorted({*existing.numbers, number})
    existing.room_config.CopyFrom(RoomConfiguration(agents=[agent_dispatch]))
    await server.sip.update_dispatch_rule(existing.sip_dispatch_rule_id, existing)


async def renumber_rule(server: api.LiveKitAPI, rule: SIPDispatchRuleInfo, numbers: list[str]) -> None:
    """Leave the rule these numbers; emptied, it goes."""
    if not numbers:
        await server.sip.delete_dispatch_rule(
            DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule.sip_dispatch_rule_id)
        )
        return
    rule.numbers[:] = numbers
    await server.sip.update_dispatch_rule(rule.sip_dispatch_rule_id, rule)


# The rules are listed after the trunks: a trunk emptied takes a rule left with none with it.
async def let_go(server: api.LiveKitAPI, org: str, number: str) -> None:
    """Take the number off the org's trunks and off both of its envs' rules on this LiveKit."""
    await _unlisted(server, org, number)
    names = {rule_name(org, env) for env in Env}
    listed = await server.sip.list_dispatch_rule(ListSIPDispatchRuleRequest())
    for rule in listed.items:
        if rule.name in names and number in rule.numbers:
            await renumber_rule(server, rule, [item for item in rule.numbers if item != number])


# LiveKit keeps its trunks and rules in Redis, which can be emptied; the tables are the truth.
# Nothing is deleted but a number the other env's LiveKit still lists, and the carrier's side is
# never touched.
async def rebuild(session: AsyncSession, handles: Handles) -> Rebuilt:
    """Admit every routed phone number again on the SFU, with its fence and its env's rule."""
    readmitted_count, refused = 0, list[str]()
    for org in await channels.orgs_with_phones(session):
        try:
            readmitted_count += await readmit(session, handles, org)
        except (api.TwirpError, httpx.HTTPError):
            logger.warning("the SFU refused org %s's numbers: the others go on", org, exc_info=True)
            refused.append(org)
    try:
        handing = await _hand_overs_admitted(session, handles)
    except (api.TwirpError, httpx.HTTPError):
        logger.warning("the sandbox's SFU refused the hand-over trunk", exc_info=True)
        handing = False
    logger.info(
        "SIP rebuilt from the tables: %d numbers stand, %d orgs refused, hand-overs admitted: %s",
        readmitted_count,
        len(refused),
        handing,
    )
    return Rebuilt(numbers=readmitted_count, refused=refused, hand_over=handing)


# A gateway started beside a LiveKit that is still starting, or down, would otherwise leave every
# number of that env unadmitted until its own next start: it tries again until the rebuild is
# whole, waiting twice as long each time, a minute at most.
async def rebuilt_until_whole(handles: Handles, wait_s: float = FIRST_WAIT_S) -> Rebuilt:
    """The rebuild, again after a wait while an org is refused or a LiveKit cannot be reached."""
    while True:
        try:
            async with handles.sessions() as session:
                rebuilt = await rebuild(session, handles)
                await session.commit()
        except (api.TwirpError, httpx.HTTPError, OSError, TimeoutError):
            rebuilt = None
        if rebuilt is not None and not rebuilt.refused:
            return rebuilt
        logger.warning("SIP not rebuilt whole (an org refused, or a LiveKit unreachable): again in %.0f s", wait_s)
        await asyncio.sleep(wait_s)
        wait_s = min(wait_s * 2, LONGEST_WAIT_S)


# After the operator approves or refuses a network: the org's trunks follow what is approved now.
async def readmit(session: AsyncSession, handles: Handles, org: str) -> int:
    """Admit the org's phone numbers again with the fences they have now; how many stand."""
    fleets = await fleet.fleets(session)
    fencing = await fencing_of(session, handles, org)
    admitted = 0
    for record in await records.phone_records_of(session, org):
        admitted += await readmitted(handles, record, fencing, fleets)
    return admitted


async def fencing_of(session: AsyncSession, handles: Handles, org: str) -> Fencing:
    """The org's carriers and approved networks, which fence its numbers now."""
    carriers = await accounts.carriers_of(session, handles.vault, org)
    return Fencing(
        carriers={carrier.id: carrier for carrier in carriers}, approved=await networks.approved(session, org)
    )


# A number lives on its env's LiveKit alone: the other env's, when it has its own, lets it go (a
# number moved, or one admitted there before the envs had a LiveKit each). On its own LiveKit the
# other env's rule lets it go first: two rules of one trunk never list one number.
async def readmitted(handles: Handles, record: RouteRecord, fencing: Fencing, fleets: fleet.Fleets) -> bool:
    """Admit the number on its env's LiveKit with the fence it has now; whether it stands."""
    route = record.route
    org, number, env = route.org, route.number, route.env
    server, other = handles.servers[env], elsewhere(handles, env)
    if other is not None:
        await let_go(other, org, number)
    fence = fence_now(record, fencing.carriers.get(route.account or ""), fencing.approved)
    if fence is None:
        await _unlisted(server, org, number)
        return False
    trunk_id = await admit(server, fence, await trunk_named(server, fence.trunk), number)
    left = await rule_named(server, rule_name(org, _other(env)))
    if left is not None and number in left.numbers:
        await renumber_rule(server, left, [listed for listed in left.numbers if listed != number])
    await rule_in(server, EnvRule(org, env, fleet.fleet_of(fleets, env)), [trunk_id], number)
    return True


# Where each env has a LiveKit of its own, a developer's own phone at a production number is
# dialled from production's room to the sandbox's SIP (hand_over.py), with a pair drawn from
# LiveKit's secret; where both share one, the sandbox's fleet is sent into the room instead.
def hand_over_trunk(handles: Handles, caller: str) -> LegTrunk | None:
    """The trunk a ring is handed to the sandbox's SIP through; None where the envs share one."""
    if elsewhere(handles, Env.production) is None:
        return None
    return LegTrunk(
        hostname=sip_domain_of(handles, Env.sandbox),
        transport="udp",
        username=hand_over.USERNAME,
        password=_hand_over_password(handles),
        shown=caller,
    )


def fence_now(
    record: RouteRecord, carrier: CarrierAccount | None, approved: dict[str, tuple[str, ...]]
) -> Fence | None:
    """The fence a routed number has with what is approved now; None while nothing fences it."""
    route = record.route
    declared = (tuple(route.networks) or None) if carrier is None else declared_networks(carrier)
    source = route.number if carrier is None else carrier.id
    own, _ = own_networks(declared, approved.get(source, ()))
    return fence_of(route.org, route.number, carrier, route.via, own)


# Once, when a box's SIP moves off its names (a cluster: the names are the HTTPS load balancer's) or
# a name is retired for another (`former`, the names an env was reached at before): the runtime
# never touches a carrier on its own, so the operator asks for it.
async def repointed(
    session: AsyncSession, handles: Handles, former: Mapping[Env, Sequence[str]] | None = None
) -> list[Repointed]:
    """Each trunk of the box's and the orgs' Twilio accounts moved to its env's SIP name."""
    moves = _moves(handles, former or {})
    if not moves:
        return []
    done: list[Repointed] = []
    for account in await accounts.every_twilio_account(session, handles.vault):
        twilio = twilio_of(handles.http, account)
        for env, was, now in moves:
            for trunk in await twilio.trunks_pointing_at(was):
                await twilio.repointed(trunk.sid, was, now)
                done.append(Repointed(account.account_sid, trunk.sid, env, was, now))
    return done


def _other(env: Env) -> Env:
    return Env.sandbox if env is Env.production else Env.production


async def _unlisted(server: api.LiveKitAPI, org: str, number: str) -> None:
    for trunk in await trunks_admitting(server, number):
        if belongs_to(trunk.name, org):
            await renumber_trunk(server, org, trunk, [n for n in trunk.numbers if n != number])


# The trunk lists no number: it admits whatever production dials, from production's media
# address alone (the one its SIP name names, and livekit-sip sends from) and with the pair. Its
# rule sends each ring to the sandbox's fleet as one diverted from production.
async def _hand_overs_admitted(session: AsyncSession, handles: Handles) -> bool:
    server = elsewhere(handles, Env.production)
    named = handles.settings.sip_domain
    if server is None or not named:
        return False
    addresses = await _addresses_of(named)
    if not addresses:
        logger.warning("production's SIP name %s names no address: the sandbox admits no hand-over", named)
        return False
    wanted = SIPInboundTrunkInfo(
        name=hand_over.HAND_OVER,
        allowed_addresses=addresses,
        auth_username=hand_over.USERNAME,
        auth_password=_hand_over_password(handles),
        headers_to_attributes=hand_over.ATTRIBUTE_OF,
    )
    trunk_id = await _hand_over_trunk_kept(server, wanted)
    await _hand_over_rule_kept(server, trunk_id, fleet.fleet_of(await fleet.fleets(session), Env.sandbox))
    return True


def _hand_over_password(handles: Handles) -> str:
    secret = handles.settings.livekit_api_secret
    if secret is None:
        raise ServiceUnavailable(NO_LIVEKIT)
    return hand_over.password_of(secret.get_secret_value())


async def _addresses_of(name: str) -> list[str]:
    try:
        async with asyncio.timeout(RESOLVED_WITHIN_S):
            found = await asyncio.get_running_loop().getaddrinfo(
                name, None, family=socket.AF_INET, type=socket.SOCK_DGRAM
            )
    except (OSError, TimeoutError):
        return []
    return sorted({str(address[4][0]) for address in found})


async def _hand_over_trunk_kept(server: api.LiveKitAPI, wanted: SIPInboundTrunkInfo) -> str:
    existing = await trunk_named(server, wanted.name)
    if existing is None:
        made = await server.sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=wanted))
        return made.sip_trunk_id
    if (
        list(existing.allowed_addresses) == list(wanted.allowed_addresses)
        and existing.auth_username == wanted.auth_username
        and existing.auth_password == wanted.auth_password
        and dict(existing.headers_to_attributes) == dict(wanted.headers_to_attributes)
    ):
        return existing.sip_trunk_id
    await server.sip.update_inbound_trunk(existing.sip_trunk_id, wanted)
    return existing.sip_trunk_id


async def _hand_over_rule_kept(server: api.LiveKitAPI, trunk_id: str, fleet_name: str) -> None:
    metadata = Dispatch(env=Env.sandbox, diverted_from=Env.production).dump()
    wanted = SIPDispatchRuleInfo(
        name=hand_over.HAND_OVER,
        trunk_ids=[trunk_id],
        rule=SIPDispatchRule(dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix=ROOM_PREFIX)),
        room_config=RoomConfiguration(agents=[RoomAgentDispatch(agent_name=fleet_name, metadata=metadata)]),
    )
    existing = await rule_named(server, hand_over.HAND_OVER)
    if existing is None:
        await server.sip.create_dispatch_rule(CreateSIPDispatchRuleRequest(dispatch_rule=wanted))
        return
    if list(existing.trunk_ids) == [trunk_id] and existing.room_config == wanted.room_config:
        return
    await server.sip.update_dispatch_rule(existing.sip_dispatch_rule_id, wanted)


# From the env's own name when SIP has a name of its own, and from every former name given.
def _moves(handles: Handles, former: Mapping[Env, Sequence[str]]) -> list[tuple[Env, str, str]]:
    settings = handles.settings
    moves: list[tuple[Env, str, str]] = []
    for env in Env:
        sip_name = settings.sip_domain_of(env)
        if not sip_name:
            continue
        names = dict.fromkeys([settings.domain or "", *former.get(env, ())])
        moves.extend(
            (env, origination_uri(name), origination_uri(sip_name)) for name in names if name and name != sip_name
        )
    return moves
