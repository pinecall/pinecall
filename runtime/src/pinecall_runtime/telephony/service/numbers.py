"""A number imported, bought, released or moved: at the carrier, on the SFU, in the routes table."""

import logging
from dataclasses import dataclass, field, replace

import httpx
from livekit.protocol.sip import SIPDispatchRuleInfo, SIPInboundTrunkInfo
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing import service as billing
from pinecall_runtime.channels import service as channels
from pinecall_runtime.channels.models import Route
from pinecall_runtime.enums import Channel, Env, RouteOrigin
from pinecall_runtime.exceptions import Conflict, NotFound, UpstreamError, ValidationError
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.telephony.schemas import WhatsappAccount
from pinecall_runtime.telephony.service import accounts, catalog, networks, records, sip
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.fence import (
    Fence,
    declared_networks,
    fence_of,
    own_networks,
)
from pinecall_runtime.telephony.service.records import RouteRecord
from pinecall_runtime.telephony.service.sip import EnvRule, domain_of, rule_name, sip_domain_of
from pinecall_runtime.telephony.service.twilio import (
    Twilio,
    TwilioNumber,
    TwilioTrunk,
    origination_uri,
    twilio_of,
)

logger = logging.getLogger(__name__)

# Whose it is stays theirs: the sentence names no org and no trunk.
NOT_A_WHATSAPP_ACCOUNT = (
    "a WhatsApp number comes through the org's WhatsApp Business account: `pinecall carriers add whatsapp` first, "
    "then import the number that account is"
)
NOT_THIS_ACCOUNTS_NUMBER = "{number} is not the number the WhatsApp Business account is: Meta says it is {display}"
HELD_ELSEWHERE = (
    "{number} is held by another org on this box, so nothing was written: if it is yours, ask the box's operator"
)


@dataclass(frozen=True, slots=True)
class NumberPurchase:
    """A number wanted from the box's own account."""

    scope: Scope
    agent: str
    country: str
    area_code: str | None = None
    channel: Channel = Channel.phone


@dataclass(frozen=True, slots=True)
class AtTwilio:
    """The number at its Twilio account, and the trunk that points it here."""

    twilio: Twilio
    number: TwilioNumber | None
    trunk: TwilioTrunk | None
    # Bought in this very request: a dry run names it and buys nothing.
    for_sale: str | None = None


@dataclass
class Survey:
    """Everything a hook needs, read before anything is written."""

    route: Route
    origin: RouteOrigin
    fence: Fence | None
    account: str | None
    networks: tuple[str, ...]
    fleet: str
    domain: str
    # Where a trunk of the account sends the env's calls: its SIP name, else its name.
    origination: str
    at_twilio: AtTwilio | None = None
    via: str | None = None
    # The networks named for the number that the operator has not approved: no trunk until he does.
    waiting: tuple[str, ...] = ()
    # The org's own other trunks that list the number and must let it go.
    leaving: list[SIPInboundTrunkInfo] = field(default_factory=list[SIPInboundTrunkInfo])
    # The org's trunks on the other env's own LiveKit that list it: it lives on one LiveKit.
    elsewhere: list[SIPInboundTrunkInfo] = field(default_factory=list[SIPInboundTrunkInfo])
    trunk: SIPInboundTrunkInfo | None = None
    rule: SIPDispatchRuleInfo | None = None
    other_rule: SIPDispatchRuleInfo | None = None
    routed: Route | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    """What a hook does, one sentence a step, and the route it ends in."""

    route: Route
    steps: list[str]
    dry_run: bool


@dataclass(frozen=True, slots=True)
class OwnedNumber:
    """A number one of the org's accounts owns: whether this env imported it, or another org holds it."""

    number: str
    name: str
    imported: bool
    # Routed by another org of this box: it cannot be imported here until that org lets it go.
    held_elsewhere: bool
    account: str


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


async def plan_buy(session: AsyncSession, handles: Handles, wanted: NumberPurchase) -> Plan:
    """What buying would do: the number Twilio would sell, and nothing bought."""
    survey = await _survey_purchase(session, handles, wanted)
    return Plan(route=survey.route, steps=_steps(survey, done=False), dry_run=True)


async def buy_number(session: AsyncSession, handles: Handles, wanted: NumberPurchase) -> Plan:
    """Buy a number on the box's account and hook it as an import, counted as the box's."""
    survey = await _survey_purchase(session, handles, wanted)
    steps = _steps(survey, done=True)
    at = survey.at_twilio
    if at is not None and at.for_sale is not None:
        survey.at_twilio = replace(at, number=await at.twilio.bought(at.for_sale), for_sale=None)
    await _write_hook(session, handles, survey)
    return Plan(route=survey.route, steps=steps, dry_run=False)


async def release_number(session: AsyncSession, handles: Handles, org: str, number: str, env: Env) -> None:
    """Let the number go: the route, its env's LiveKit's trunks and rule; the account keeps it."""
    route = await channels.get_route(session, org, number)
    if route is None or route.env is not env:
        raise NotFound(f"the org answers no {number} in the {env}")
    await channels.remove_route(session, org, number)
    await sip.let_go(handles.servers[env], org, number)


# Where both envs share a LiveKit the number keeps its trunk and changes rules; where each has
# its own, it leaves the old env's LiveKit and is admitted on the new one's.
async def move_number(session: AsyncSession, handles: Handles, org: str, number: str, env: Env) -> Route:
    """Move the number into the other env: its row, and its trunk and rule on that LiveKit."""
    record = await records.record_of(session, org, number)
    if record is None:
        raise NotFound(f"the org answers no {number} in either env")
    route = record.route
    if route.env is env:
        return route
    # A WhatsApp number is on no trunk: its env is its row alone.
    if route.channel is Channel.phone:
        moved = RouteRecord(_with_env(route, env), record.carrier)
        await sip.readmitted(handles, moved, await sip.fencing_of(session, handles, org), await fleet.fleets(session))
    await channels.move_route(session, org, number, env)
    return _with_env(route, env)


# A SIP peer owns what it owns and nobody here can list it: its import takes the number typed.
async def owned_numbers(
    session: AsyncSession, handles: Handles, scope: Scope, account: str | None = None
) -> tuple[str, list[OwnedNumber]]:
    """The kind of the org's accounts, and every number its Twilio accounts own."""
    if account is None:
        carriers = await accounts.carriers_of(session, handles.vault, scope.org)
    else:
        carriers = [await accounts.carrier_named(session, handles.vault, scope.org, account)]
    if not carriers:
        raise NotFound(accounts.NO_CARRIER)
    imported = {route.number for route in await channels.routes_of_org(session, scope.org, scope.env)}
    elsewhere = {route.number for route in await channels.routes_held_by_others(session, scope.org)}
    controlled = [
        (carrier, control)
        for carrier in carriers
        if (control := accounts.control_of(handles.http, carrier)) is not None
    ]
    owned = [
        OwnedNumber(
            number=number.phone_number,
            name=number.friendly_name or number.phone_number,
            imported=number.phone_number in imported,
            held_elsewhere=number.phone_number in elsewhere,
            account=carrier.id,
        )
        for carrier, control in controlled
        for number in await control.numbers()
    ]
    for carrier in carriers:
        meta = accounts.meta_of(carrier)
        if meta is not None:
            owned += await _at_meta(handles.http, meta, imported, elsewhere)
    lister = controlled[0][0] if controlled else carriers[0]
    return lister.account.kind, owned


async def import_number(session: AsyncSession, handles: Handles, wanted: NumberImport) -> Plan:
    """Hook the number at its account, admit it on the SFU in its env, route it."""
    survey = await _survey_import(session, handles, wanted)
    steps = _steps(survey, done=True)
    await _write_hook(session, handles, survey)
    return Plan(route=survey.route, steps=steps, dry_run=False)


# The operator's row is admitted like a hooked number, at once, and says who wrote it.
async def type_route(session: AsyncSession, handles: Handles, wanted: NumberImport) -> Plan:
    """Route a number the box's operator names: on the SFU and in the table, no account touched."""
    survey = await _survey_import(session, handles, replace(wanted, hooked=True, account=None))
    survey.origin = RouteOrigin.typed
    steps = _steps(survey, done=True)
    await _write_hook(session, handles, survey)
    return Plan(route=survey.route, steps=steps, dry_run=False)


async def plan_import(session: AsyncSession, handles: Handles, wanted: NumberImport) -> Plan:
    """What importing the number would do, writing nothing."""
    survey = await _survey_import(session, handles, wanted)
    return Plan(route=survey.route, steps=_steps(survey, done=False), dry_run=True)


async def _survey_import(session: AsyncSession, handles: Handles, wanted: NumberImport) -> Survey:
    number = parse_e164(wanted.number)
    if wanted.channel not in {Channel.phone, Channel.whatsapp}:
        raise ValidationError(f"a number is imported to answer phone or whatsapp, not {wanted.channel}")
    org, env = wanted.scope.org, wanted.scope.env
    domain = domain_of(handles)
    route = Route(org=org, agent=wanted.agent, channel=wanted.channel, number=number, env=env, managed=False)
    if await channels.held_elsewhere(session, org, number):
        raise Conflict(HELD_ELSEWHERE.format(number=number))
    fleets = await fleet.fleets(session)
    await _check_via(session, wanted)
    carrier = None if wanted.hooked else await accounts.carrier_named(session, handles.vault, org, wanted.account)
    if wanted.channel is Channel.whatsapp:
        await _a_whatsapp_number(handles, carrier, number)
    if carrier is not None and wanted.networks:
        raise ValidationError(
            f"a {carrier.account.kind} account takes no networks: they are the fence of a number you hook"
        )
    own_named = tuple(networks.checked(network) for network in wanted.networks)
    approved = await networks.approved(session, org)
    declared = (own_named or None) if carrier is None else declared_networks(carrier)
    source = number if carrier is None else carrier.id
    own, waiting = own_networks(declared, approved.get(source, ()))
    survey = Survey(
        route=route,
        origin=RouteOrigin.hooked if carrier is None else RouteOrigin.imported,
        fence=fence_of(org, number, carrier, wanted.via, own) if wanted.channel is Channel.phone else None,
        account=None if carrier is None else carrier.id,
        networks=own_named,
        fleet=fleet.fleet_of(fleets, env),
        domain=domain,
        origination=origination_uri(sip_domain_of(handles, env)),
        via=wanted.via,
        waiting=waiting,
    )
    control = None if carrier is None else accounts.control_of(handles.http, carrier)
    if control is not None and wanted.channel is Channel.phone:
        survey.at_twilio = await _at_twilio(handles, control, number, env, move=wanted.move)
    return await _survey_sfu(session, handles, survey)


# A WhatsApp route is Meta's: through an account, the number is the one the org's WhatsApp Business
# account is, as Meta names it, never a phone number typed with `--channel whatsapp`. Hooked, the org
# points Meta at the box itself and there is no account to ask.
async def _a_whatsapp_number(handles: Handles, carrier: CarrierAccount | None, number: str) -> None:
    if carrier is None:
        return
    meta = accounts.meta_of(carrier)
    if meta is None:
        raise ValidationError(NOT_A_WHATSAPP_ACCOUNT)
    display, _ = await channels.display_number(handles.http, meta.access_token, meta.phone_number_id)
    if display != number:
        raise ValidationError(NOT_THIS_ACCOUNTS_NUMBER.format(number=number, display=display))


# A catalog carrier is the operator's to admit; its networks are the number's whole fence.
async def _check_via(session: AsyncSession, wanted: NumberImport) -> None:
    if wanted.via is None:
        return
    if not wanted.hooked or wanted.networks or wanted.channel is not Channel.phone:
        raise ValidationError(
            "a number comes via a carrier of the box's catalog when the org hooks it, on the phone, with no "
            "networks of its own: "
            "that carrier's are its fence"
        )
    carrier = catalog.known_carrier(wanted.via)
    if wanted.via not in await catalog.admitted_kinds(session):
        raise Conflict(f"this box does not admit {carrier.name}: its operator turns it on under Carriers")


async def _survey_purchase(session: AsyncSession, handles: Handles, wanted: NumberPurchase) -> Survey:
    org, env = wanted.scope.org, wanted.scope.env
    domain = domain_of(handles)
    origination = origination_uri(sip_domain_of(handles, env))
    boxs = await accounts.box_twilio(session, handles.vault)
    await billing.admit_number(session, org, env, bought=await channels.managed_in(session, org, env))
    twilio = twilio_of(handles.http, boxs)
    for_sale = await twilio.for_sale(wanted.country, wanted.area_code)
    if for_sale is None:
        area = f", area code {wanted.area_code}" if wanted.area_code else ""
        raise NotFound(f"Twilio has no local voice number for sale in {wanted.country.upper()}{area}")
    route = Route(org=org, agent=wanted.agent, channel=wanted.channel, number=for_sale, env=env, managed=True)
    survey = Survey(
        route=route,
        origin=RouteOrigin.bought,
        fence=fence_of(org, for_sale, None, None, None),
        account=None,
        networks=(),
        fleet=fleet.fleet_of(await fleet.fleets(session), env),
        domain=domain,
        origination=origination,
        at_twilio=AtTwilio(
            twilio=twilio, number=None, trunk=await twilio.trunk_pointing_at(origination), for_sale=for_sale
        ),
    )
    return await _survey_sfu(session, handles, survey)


async def _at_twilio(handles: Handles, twilio: Twilio, number: str, env: Env, *, move: bool) -> AtTwilio:
    owned = await twilio.number(number)
    if owned is None:
        raise NotFound(f"{number} is not a number of Twilio account {twilio.sid}")
    trunk = await twilio.trunk_pointing_at(origination_uri(sip_domain_of(handles, env)))
    elsewhere = owned.trunk_sid is not None and (trunk is None or owned.trunk_sid != trunk.sid)
    if elsewhere and owned.trunk_sid is not None and not move:
        where = await twilio.originations(owned.trunk_sid)
        other = await twilio.trunk(owned.trunk_sid)
        raise Conflict(
            f"{number} is on Twilio trunk {other.friendly_name or other.sid} of {twilio.sid}, pointed at "
            f"{', '.join(where) or 'nowhere'}: "
            "moving it here takes it off there, so say move"
        )
    return AtTwilio(twilio=twilio, number=owned, trunk=trunk)


async def _survey_sfu(session: AsyncSession, handles: Handles, survey: Survey) -> Survey:
    route, fence = survey.route, survey.fence
    number = route.number
    survey.routed = await channels.get_route(session, route.org, number)
    if route.channel is not Channel.phone:
        return survey
    server, other = handles.servers[route.env], sip.elsewhere(handles, route.env)
    listing = await sip.trunks_admitting(server, number)
    if any(not sip.belongs_to(trunk.name, route.org) for trunk in listing):
        raise Conflict(HELD_ELSEWHERE.format(number=number))
    survey.leaving = [trunk for trunk in listing if fence is None or trunk.name != fence.trunk]
    if other is not None:
        survey.elsewhere = [
            trunk for trunk in await sip.trunks_admitting(other, number) if sip.belongs_to(trunk.name, route.org)
        ]
    if fence is None:
        return survey
    survey.trunk = await sip.trunk_named(server, fence.trunk)
    survey.rule = await sip.rule_named(server, rule_name(route.org, route.env))
    survey.other_rule = await sip.rule_named(server, rule_name(route.org, _other(route.env)))
    return survey


async def _write_hook(session: AsyncSession, handles: Handles, survey: Survey) -> None:
    route, number = survey.route, survey.route.number
    at = survey.at_twilio
    if at is not None and at.number is not None:
        trunk = at.trunk or await at.twilio.trunk_made(survey.domain, survey.origination)
        survey.at_twilio = replace(at, trunk=trunk)
        if at.number.trunk_sid not in {None, trunk.sid}:
            await at.twilio.detach(str(at.number.trunk_sid), at.number.sid)
        if at.number.trunk_sid != trunk.sid:
            await at.twilio.attach(trunk.sid, at.number.sid)
    if survey.origin is RouteOrigin.hooked and survey.networks:
        await networks.ask(session, route.org, number, survey.networks)
    server, other = handles.servers[route.env], sip.elsewhere(handles, route.env)
    if other is not None and route.channel is Channel.phone:
        await sip.let_go(other, route.org, number)
    for leaving in survey.leaving:
        await sip.renumber_trunk(server, route.org, leaving, [listed for listed in leaving.numbers if listed != number])
    if survey.fence is not None:
        # Off the other env's rule first: two rules of one trunk never list one number.
        if survey.other_rule is not None and number in survey.other_rule.numbers:
            await sip.renumber_rule(
                server, survey.other_rule, [listed for listed in survey.other_rule.numbers if listed != number]
            )
        trunk_id = await sip.admit(server, survey.fence, survey.trunk, number)
        await sip.rule_in(server, EnvRule(route.org, route.env, survey.fleet), [trunk_id], number)
    # A hooked number waits for the operator only where the box asks (PINECALL_APPROVE_HOOKED).
    waits = survey.origin is RouteOrigin.hooked and handles.settings.approve_hooked
    written = channels.RouteWrite(
        origin=survey.origin, account=survey.account, networks=survey.networks, via=survey.via, waits=waits
    )
    await channels.put_route(session, route, written)


def _steps(survey: Survey, *, done: bool) -> list[str]:
    route, number = survey.route, survey.route.number
    made = "done" if done else "to do"
    steps: list[str] = []
    at = survey.at_twilio
    if at is not None:
        if at.for_sale is not None:
            steps.append(f"Twilio: buy {at.for_sale} on the box's account: {made}")
        steps.append(f"Twilio: a trunk sending calls to {survey.origination}: {'stands' if at.trunk else made}")
        on_it = at.number is not None and at.trunk is not None and at.number.trunk_sid == at.trunk.sid
        steps.append(f"Twilio: {number} attached to it: {'stands' if on_it else made}")
    fence = survey.fence
    steps += [
        f"LiveKit of the {_other(route.env)}: {number} off trunk {trunk.name}: {made}" for trunk in survey.elsewhere
    ]
    steps += [f"LiveKit: {number} off trunk {trunk.name}: {made}" for trunk in survey.leaving]
    if fence is None and survey.waiting and route.channel is Channel.phone:
        steps.append(f"LiveKit: {number} waits for the box's operator to approve {', '.join(survey.waiting)}: {made}")
    if fence is not None:
        admits = survey.trunk is not None and number in survey.trunk.numbers
        steps.append(f"LiveKit: trunk {fence.trunk} admits {number}: {'stands' if admits else made}")
        ruled = survey.rule is not None and number in survey.rule.numbers
        steps.append(
            f"LiveKit: rule {rule_name(route.org, route.env)} sends it to fleet {survey.fleet}: "
            f"{'stands' if ruled else made}"
        )
    routed = survey.routed is not None and _same_route(survey.routed, route)
    steps.append(f"route: {number} to {route.agent} in the {route.env}: {'stands' if routed else made}")
    return steps


# A token Meta refuses (they expire) leaves the account listed with no number, said in the log.
async def _at_meta(
    http: httpx.AsyncClient, account: WhatsappAccount, imported: set[str], elsewhere: set[str]
) -> list[OwnedNumber]:
    try:
        number, name = await channels.display_number(http, account.access_token, account.phone_number_id)
    except UpstreamError:
        logger.warning("Meta did not say which number %s is", account.phone_number_id, exc_info=True)
        return []
    return [
        OwnedNumber(
            number=number,
            name=name or number,
            imported=number in imported,
            held_elsewhere=number in elsewhere,
            account=account.phone_number_id,
        )
    ]


def _same_route(kept: Route, wanted: Route) -> bool:
    return (kept.org, kept.agent, kept.channel, kept.number, kept.env, kept.managed) == (
        wanted.org,
        wanted.agent,
        wanted.channel,
        wanted.number,
        wanted.env,
        wanted.managed,
    )


def _with_env(route: Route, env: Env) -> Route:
    return Route(
        org=route.org,
        agent=route.agent,
        channel=route.channel,
        number=route.number,
        env=env,
        managed=route.managed,
        account=route.account,
        networks=list(route.networks),
        origin=route.origin,
        via=route.via,
        last_call_at=route.last_call_at,
        approved_at=route.approved_at,
        approved_by=route.approved_by,
    )


def _other(env: Env) -> Env:
    return Env.sandbox if env is Env.production else Env.production
