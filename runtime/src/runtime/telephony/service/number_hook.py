"""A number imported, bought or typed: everything read first, then one list of steps, said or run."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

import httpx
from livekit import api
from livekit.protocol.sip import SIPDispatchRuleInfo, SIPInboundTrunkInfo
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.enums import Channel, RouteOrigin
from runtime.exceptions import Conflict, ValidationError
from runtime.fleet import service as fleet
from runtime.kit.crypto import Vault
from runtime.kit.text import parse_e164
from runtime.kit.time import now
from runtime.livekit import Servers
from runtime.scoping import box_wide
from runtime.telephony.repository import Numbered, RouteRepository, RouteToWrite
from runtime.telephony.service import accounts, catalog, networks, sfu, twilio_carrier
from runtime.telephony.service import fence as fences
from runtime.telephony.service.carrier import SipNames, Step
from runtime.telephony.service.fence import Fenced
from runtime.telephony.service.networks import NOTHING_ASKED, Standing
from runtime.telephony.service.sfu import EnvRule


@dataclass(frozen=True, slots=True)
class NumberImport:
    """A number wanted: where it answers, and how it reaches the box."""

    scope: Scope
    agent: str
    number: str
    channel: Channel = Channel.phone
    # The account it lives in; unsaid, the org's only one.
    account: str | None = None
    # The org points the number here itself: no account is touched.
    hooked: bool = False
    # A self-hooked number's own networks, which the operator approves; unsaid, its carrier's.
    networks: tuple[str, ...] = ()
    # The catalog carrier a self-hooked number comes through; unsaid, Twilio.
    via: str | None = None
    # Take the number off another trunk of its account first.
    move: bool = False


@dataclass(frozen=True, slots=True)
class NumberPurchase:
    """A number wanted from the box's own account."""

    scope: Scope
    agent: str
    country: str
    area_code: str | None = None
    channel: Channel = Channel.phone


@dataclass(frozen=True, slots=True)
class OnSfu:
    """What LiveKit holds of the number, read once: its env's, and the other env's where that is another."""

    # The org's own other trunks that list the number and must let it go.
    leaving: tuple[SIPInboundTrunkInfo, ...] = ()
    # The org's trunks and rules on the other env's own LiveKit that list it: it lives on one LiveKit.
    elsewhere: tuple[str, ...] = ()
    trunk: SIPInboundTrunkInfo | None = None
    rule: SIPDispatchRuleInfo | None = None
    other_rule: SIPDispatchRuleInfo | None = None


# Read before anything is written, and never changed after: a dry run and a hook see the same.
@dataclass(frozen=True, slots=True)
class Survey:
    """Everything a hook needs: the row it ends in, the number's fence, and how its carrier and the SFU stand."""

    route: RouteToWrite
    fenced: Fenced
    fleet: str
    at_carrier: tuple[Step, ...]
    on_sfu: OnSfu
    # Where the operator stands on the networks the number itself named.
    asked: Standing
    # The org's row at the number as it stands, when it has one.
    existing: Numbered | None


@dataclass(frozen=True, slots=True)
class Plan:
    """What a hook does, one sentence a step, and the route it ends in."""

    route: RouteToWrite
    steps: list[str]
    dry_run: bool


# The trunk the number is admitted on, as the step that admits it leaves it for the step that rules it.
@dataclass(slots=True)
class _Admitted:
    trunk_id: str | None


# ── the use cases ──


async def plan_import(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberImport,
) -> Plan:
    """What importing the number would do, writing nothing."""
    survey = await survey_import(session, vault, http, servers, names, wanted)
    return _plan(survey, _steps_of(session, servers, survey), done=False)


async def import_number(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberImport,
) -> Plan:
    """Hook the number at its account, admit it on the SFU in its env, route it."""
    survey = await survey_import(session, vault, http, servers, names, wanted)
    return await _hook(survey, _steps_of(session, servers, survey))


# The operator's row is admitted like a hooked number, at once, and says who wrote it. One row per
# number per org: a number added again moves. The carrier is never touched, so it rings only where
# the carrier already points it here.
async def type_route(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberImport,
) -> Plan:
    """Route a number the box's operator names: on the SFU and in the table, no account touched."""
    hooked = replace(wanted, hooked=True, account=None)
    survey = await survey_import(session, vault, http, servers, names, hooked, origin=RouteOrigin.typed)
    return await _hook(survey, _steps_of(session, servers, survey))


async def plan_buy(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberPurchase,
) -> Plan:
    """What buying would do: the number Twilio would sell, and nothing bought."""
    survey = await survey_purchase(session, vault, http, servers, names, wanted)
    return _plan(survey, _steps_of(session, servers, survey), done=False)


# The purchase is the first step, and it costs money and is not undone: a step after it that LiveKit
# or Twilio refuses leaves the number on the box's account with no row (the request's transaction is
# rolled back), and nothing lists a number of the box's that no route names.
async def buy_number(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberPurchase,
) -> Plan:
    """Buy a number on the box's account and hook it as an import, counted as the box's."""
    survey = await survey_purchase(session, vault, http, servers, names, wanted)
    return await _hook(survey, _steps_of(session, servers, survey))


# ── the surveys ──


async def survey_import(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberImport,
    *,
    origin: RouteOrigin | None = None,
) -> Survey:
    """Everything importing a number needs, read before anything is written."""
    number = parse_e164(wanted.number)
    if wanted.channel not in {Channel.phone, Channel.whatsapp}:
        raise ValidationError(f"a number is imported to answer phone or whatsapp, not {wanted.channel}")
    org, env = wanted.scope.org, wanted.scope.env
    # A box with no name cannot be pointed at.
    names.get_domain()
    names.origination_of(env)
    repository = RouteRepository(session)
    with box_wide():
        if await repository.is_held_elsewhere(org, number):
            # Whose it is stays theirs: the sentence names no org and no trunk.
            raise Conflict(
                f"{number} is held by another org on this box, so nothing was written: if it is yours, ask the "
                "box's operator"
            )
    fleets = await fleet.get_fleets(session)
    await _check_via(session, wanted)
    account = None if wanted.hooked else await accounts.get_carrier(session, vault, org, wanted.account)
    if account is not None:
        await account.check_number(http, wanted.channel, number)
    if account is not None and wanted.networks:
        raise ValidationError(f"a {account.kind} account takes no networks: they are the fence of a number you hook")
    named = tuple(networks.check_network(network) for network in wanted.networks)
    standings = await networks.standings_of(session, org)
    asked = standings.get(number, NOTHING_ASKED)
    fenced = Fenced(None)
    if wanted.channel is Channel.phone and account is not None:
        fenced = account.fence(number, standings.get(account.id, NOTHING_ASKED))
    elif wanted.channel is Channel.phone:
        fenced = fences.fence_unaccounted(org, number, wanted.via, named, asked)
    came = origin or (RouteOrigin.hooked if account is None else RouteOrigin.imported)
    existing = await repository.find(org, number)
    # A hooked number waits for the operator only where the box asks (PINECALL_APPROVE_HOOKED); one
    # approved once stays approved however it comes again.
    waits = came is RouteOrigin.hooked and names.approve_hooked
    approved_at = (None if existing is None else existing.route.approved_at) or (None if waits else now())
    route = RouteToWrite(
        org=org,
        number=number,
        agent=wanted.agent,
        channel=wanted.channel,
        env=env,
        account=None if account is None else account.id,
        networks=named,
        origin=came,
        via=wanted.via,
        approved_at=approved_at,
    )
    at_carrier: Sequence[Step] = ()
    if account is not None and wanted.channel is Channel.phone:
        at_carrier = await account.survey_hook(http, names, number, env, move=wanted.move)
    on_sfu = await _survey_sfu(servers, route, fenced)
    return Survey(route, fenced, fleet.fleet_of(fleets, env), tuple(at_carrier), on_sfu, asked, existing)


async def survey_purchase(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    wanted: NumberPurchase,
) -> Survey:
    """Everything buying a number needs, the number Twilio would sell among it, read before anything is written."""
    org, env = wanted.scope.org, wanted.scope.env
    names.get_domain()
    names.origination_of(env)
    boxs = await accounts.box_twilio(session, vault)
    repository = RouteRepository(session)
    # The stock is held before it is counted: of two purchases at the limit, the second is refused.
    await billing.hold_stock(session, org, env, "numbers")
    await billing.admit_number(session, org, env, bought=await repository.count_managed(org, env))
    for_sale, at_carrier = await twilio_carrier.survey_purchase(
        http, boxs, names, env, wanted.country, wanted.area_code
    )
    fenced = Fenced(None)
    if wanted.channel is Channel.phone:
        fenced = fences.fence_unaccounted(org, for_sale, None, (), NOTHING_ASKED)
    existing = await repository.find(org, for_sale)
    route = RouteToWrite(
        org=org,
        number=for_sale,
        agent=wanted.agent,
        channel=wanted.channel,
        env=env,
        managed=True,
        origin=RouteOrigin.bought,
        approved_at=(None if existing is None else existing.route.approved_at) or now(),
    )
    fleets = await fleet.get_fleets(session)
    on_sfu = await _survey_sfu(servers, route, fenced)
    return Survey(route, fenced, fleet.fleet_of(fleets, env), tuple(at_carrier), on_sfu, NOTHING_ASKED, existing)


# A catalog carrier is the operator's to admit; its networks are the number's whole fence.
async def _check_via(session: AsyncSession, wanted: NumberImport) -> None:
    if wanted.via is None:
        return
    if not wanted.hooked or wanted.networks or wanted.channel is not Channel.phone:
        raise ValidationError(
            "a number comes via a carrier of the box's catalog when the org hooks it, on the phone, with no "
            "networks of its own: that carrier's are its fence"
        )
    carrier = catalog.get_known(wanted.via)
    if wanted.via not in await catalog.list_admitted(session):
        raise Conflict(f"this box does not admit {carrier.name}: its operator turns it on under Carriers")


async def _survey_sfu(servers: Servers, route: RouteToWrite, fenced: Fenced) -> OnSfu:
    if route.channel is not Channel.phone:
        return OnSfu()
    org, number, fence = route.org, route.number, fenced.fence
    server, other = servers[route.env], sfu.other_server(servers, route.env)
    listing = await sfu.list_trunks_admitting(server, number)
    if any(not sfu.belongs_to(trunk.name, org) for trunk in listing):
        raise Conflict(
            f"{number} is held by another org on this box, so nothing was written: if it is yours, ask the "
            "box's operator"
        )
    leaving = tuple(trunk for trunk in listing if fence is None or trunk.name != fence.trunk)
    elsewhere = () if other is None else await _list_elsewhere(other, org, number)
    if fence is None:
        return OnSfu(leaving, elsewhere)
    return OnSfu(
        leaving,
        elsewhere,
        trunk=await sfu.find_trunk(server, fence.trunk),
        rule=await sfu.find_rule(server, sfu.rule_name(org, route.env)),
        other_rule=await sfu.find_rule(server, sfu.rule_name(org, route.env.other)),
    )


async def _list_elsewhere(other: api.LiveKitAPI, org: str, number: str) -> tuple[str, ...]:
    trunks = [trunk.name for trunk in await sfu.list_trunks_admitting(other, number) if sfu.belongs_to(trunk.name, org)]
    rules = [
        rule.name for rule in await sfu.list_rules(other) if sfu.belongs_to(rule.name, org) and number in rule.numbers
    ]
    return (*(f"trunk {name}" for name in trunks), *(f"rule {name}" for name in rules))


# ── the steps ──


async def _nothing() -> None:
    return


# In the order they are written: the carrier first, the networks asked, the number off wherever else
# it is listed, then admitted and ruled, and the row last, so a refusal leaves no row behind.
def _steps_of(session: AsyncSession, servers: Servers, survey: Survey) -> list[Step]:
    route, fence, on_sfu = survey.route, survey.fenced.fence, survey.on_sfu
    org, number, env = route.org, route.number, route.env
    server, other = servers[env], sfu.other_server(servers, env)
    steps = list(survey.at_carrier)
    if route.origin is RouteOrigin.hooked and route.networks:
        steps.append(_ask_step(session, survey))
    if other is not None:
        elsewhere = other

        async def leave_the_other() -> None:
            await sfu.let_go(elsewhere, org, number)

        steps += [
            Step(f"LiveKit of the {env.other}: {number} off {listed}", stands=False, write=leave_the_other)
            for listed in on_sfu.elsewhere
        ]
    steps += [_leave_step(server, org, number, trunk) for trunk in on_sfu.leaving]
    if fence is None and route.channel is Channel.phone:
        steps += _waiting_steps(survey)
    if fence is not None:
        steps += _admit_steps(server, survey, fence)
    steps.append(_route_step(session, survey))
    return steps


def _ask_step(session: AsyncSession, survey: Survey) -> Step:
    route, asked = survey.route, survey.asked

    async def ask() -> None:
        await networks.ask(session, route.org, route.number, route.networks)

    stands = set(route.networks) == {*asked.approved, *asked.waiting, *asked.refused}
    return Step(f"networks: {', '.join(route.networks)} asked of the box's operator", stands=stands, write=ask)


def _leave_step(server: api.LiveKitAPI, org: str, number: str, trunk: SIPInboundTrunkInfo) -> Step:
    async def leave() -> None:
        await sfu.renumber_trunk(server, org, trunk, [listed for listed in trunk.numbers if listed != number])

    return Step(f"LiveKit: {number} off trunk {trunk.name}", stands=False, write=leave)


# Nothing is written for a number with no fence: the sentences say what it waits for.
def _waiting_steps(survey: Survey) -> list[Step]:
    number, fenced = survey.route.number, survey.fenced
    steps: list[Step] = []
    if fenced.waiting:
        waiting = ", ".join(fenced.waiting)
        says = f"LiveKit: {number} waits for the box's operator to approve {waiting}"
        steps.append(Step(says, stands=False, write=_nothing))
    if fenced.refused:
        says = f"LiveKit: {number} is admitted from nowhere: the box's operator refused {', '.join(fenced.refused)}"
        steps.append(Step(says, stands=True, write=_nothing))
    return steps


def _admit_steps(server: api.LiveKitAPI, survey: Survey, fence: fences.Fence) -> list[Step]:
    route, on_sfu = survey.route, survey.on_sfu
    org, number, env = route.org, route.number, route.env
    env_rule = EnvRule(org, env, survey.fleet)
    admitted = _Admitted(None if on_sfu.trunk is None else on_sfu.trunk.sip_trunk_id)
    steps: list[Step] = []
    # Off the other env's rule first: two rules of one trunk never list one number.
    other_rule = on_sfu.other_rule
    if other_rule is not None and number in other_rule.numbers:

        async def leave_the_other_rule() -> None:
            await sfu.renumber_rule(server, other_rule, [listed for listed in other_rule.numbers if listed != number])

        steps.append(Step(f"LiveKit: {number} off rule {other_rule.name}", stands=False, write=leave_the_other_rule))

    async def admit() -> None:
        admitted.trunk_id = await sfu.admit(server, fence, on_sfu.trunk, number)

    async def rule() -> None:
        await sfu.rule_in(server, env_rule, [] if admitted.trunk_id is None else [admitted.trunk_id], number)

    listed = [] if admitted.trunk_id is None else [admitted.trunk_id]
    ruled = on_sfu.trunk is not None and sfu.rules_in(on_sfu.rule, env_rule, listed, number)
    steps.append(
        Step(
            f"LiveKit: trunk {fence.trunk} admits {number}", stands=sfu.admits(on_sfu.trunk, fence, number), write=admit
        )
    )
    steps.append(
        Step(f"LiveKit: rule {sfu.rule_name(org, env)} sends it to fleet {survey.fleet}", stands=ruled, write=rule)
    )
    return steps


def _route_step(session: AsyncSession, survey: Survey) -> Step:
    route, existing = survey.route, survey.existing

    async def put() -> None:
        await RouteRepository(session).put(route)

    stands = existing is not None and _is_written(existing, route)
    return Step(f"route: {route.number} to {route.agent} in the {route.env}", stands=stands, write=put)


def _is_written(existing: Numbered, wanted: RouteToWrite) -> bool:
    kept = existing.route
    return (
        kept.agent,
        kept.channel,
        kept.env,
        kept.managed,
        kept.account,
        tuple(kept.networks),
        kept.origin,
        kept.via,
        kept.approved_at,
    ) == (
        wanted.agent,
        wanted.channel,
        wanted.env,
        wanted.managed,
        wanted.account,
        wanted.networks,
        wanted.origin,
        wanted.via,
        wanted.approved_at,
    )


def _plan(survey: Survey, steps: Sequence[Step], *, done: bool) -> Plan:
    return Plan(route=survey.route, steps=[step.say(done=done) for step in steps], dry_run=not done)


# Each step that does not stand already, in order: the first that raises ends the hook, and what the
# database was told goes back with the request's transaction.
async def _hook(survey: Survey, steps: Sequence[Step]) -> Plan:
    plan = _plan(survey, steps, done=True)
    for step in steps:
        if not step.stands:
            await step.write()
    return plan
