"""Dialling out: an account made dialable, the account a number dials through, a leg's trunk."""

import logging
import secrets
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.channels import service as channels
from pinecall_runtime.channels.models import Route
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.telephony.schemas import LegTrunk, Termination
from pinecall_runtime.telephony.service import accounts
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.dial_policy import Dial, Guards, guard_second_leg, guards_of
from pinecall_runtime.telephony.service.fence import dialled_of, missing_to_dial
from pinecall_runtime.telephony.service.sip import domain_of, sip_domain_of
from pinecall_runtime.telephony.service.twilio import (
    TERMINATION_SUFFIX,
    Twilio,
    TwilioTrunk,
    origination_uri,
    termination_host,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutboundReadiness:
    """Whether the org can place a call through an account, and what is still missing."""

    ready: bool
    kind: str | None
    from_numbers: list[str]
    steps_missing: list[str]
    guards: Guards


@dataclass(frozen=True, slots=True)
class Provisioned:
    """What provisioning did, or would do."""

    steps: list[str]
    dry_run: bool
    ready: bool
    trunk: str | None = None
    address: str | None = None


@dataclass(frozen=True, slots=True)
class TwilioSurvey:
    """What the account holds today: the trunk, its termination host, the list, the credential."""

    twilio: Twilio
    trunk: TwilioTrunk | None
    host: str
    list_name: str
    listed: str | None
    username: str
    # Whether the list already holds the org's credential; else one is made and sealed.
    holds: bool
    on_trunk: bool


@dataclass(frozen=True, slots=True)
class OutboundSurvey:
    """How an account stands before anything is written: the steps read, and Twilio's own."""

    steps: list[str]
    address: str | None = None
    twilio: TwilioSurvey | None = None


async def outbound_readiness(
    session: AsyncSession, handles: Handles, scope: Scope, account: str | None = None
) -> OutboundReadiness:
    """Whether the org can dial out in the env, one sentence per thing missing, in order."""
    guards = await guards_of(session, scope.org)
    numbers = [route.number for route in await phone_routes_of(session, scope)]
    try:
        carrier = await accounts.carrier_named(session, handles.vault, scope.org, account)
    except NotFound as absent:
        return OutboundReadiness(
            ready=False, kind=None, from_numbers=numbers, steps_missing=[str(absent)], guards=guards
        )
    missing = missing_to_dial(carrier)
    if not numbers:
        missing.append(f"the org answers at no phone number in the {scope.env}: a call shows one")
    return OutboundReadiness(
        ready=not missing, kind=carrier.account.kind, from_numbers=numbers, steps_missing=missing, guards=guards
    )


async def plan_outbound(
    session: AsyncSession, handles: Handles, org: str, env: Env, account: str | None = None
) -> Provisioned:
    """What provisioning would write, and nothing written."""
    carrier = await accounts.carrier_named(session, handles.vault, org, account)
    survey = await _surveyed(handles, carrier, env)
    return Provisioned(steps=survey.steps, dry_run=True, ready=survey.twilio is None, address=survey.address)


async def provision_outbound(
    session: AsyncSession, handles: Handles, org: str, env: Env, account: str | None = None
) -> Provisioned:
    """Make the account dialable: Twilio's termination and a credential; a peer needs nothing."""
    carrier = await accounts.carrier_named(session, handles.vault, org, account)
    survey = await _surveyed(handles, carrier, env)
    if survey.twilio is None:
        return Provisioned(steps=survey.steps, dry_run=False, ready=True, address=survey.address)
    trunk = await _twilio_provisioned(session, handles, carrier, survey.twilio, env)
    return Provisioned(steps=survey.steps, dry_run=False, ready=True, trunk=trunk, address=survey.address)


async def leg_trunk(session: AsyncSession, handles: Handles, dial: Dial) -> LegTrunk:
    """How a leg of a live call is dialled, after its guards: the account of the number shown."""
    await guard_second_leg(session, dial)
    scope = dial.scope
    shown = dial.shown
    if shown is None:
        routes = [route for route in await phone_routes_of(session, scope) if route.agent == dial.agent]
        if not routes:
            raise NotFound(f"agent {dial.agent} answers at no phone number in the {scope.env}: a call back shows one")
        shown = routes[0].number
    return _leg_through(await carrier_for_number(session, handles, scope, shown), shown)


# This box makes nothing on somebody else's switch: a peer is dialled where it said.
async def _surveyed(handles: Handles, carrier: CarrierAccount, env: Env) -> OutboundSurvey:
    control = accounts.control_of(handles.http, carrier)
    if control is not None:
        return await _twilio_surveyed(handles, carrier, control, env)
    dialled = dialled_of(carrier)
    return OutboundSurvey(
        steps=[f"SIP peer: dialled at {dialled.hostname} over {dialled.transport}: stands"], address=dialled.hostname
    )


# Read before anything is written, so a plan and a provisioning see the same account.
async def _twilio_surveyed(handles: Handles, carrier: CarrierAccount, twilio: Twilio, env: Env) -> OutboundSurvey:
    domain = domain_of(handles)
    origination = origination_uri(sip_domain_of(handles, env))
    trunk = await twilio.trunk_pointing_at(origination)
    host = termination_host(domain, twilio.sid)
    # One list per trunk, as the trunk is per account and box; one credential per org on it,
    # so two orgs that brought the same account each dial with their own.
    name = host.removesuffix(TERMINATION_SUFFIX)
    username = f"pinecall-{carrier.org}".replace("_", "-")
    listed = await twilio.credential_list(name)
    holds = listed is not None and username in await twilio.usernames_in(listed)
    if holds and carrier.outbound is None:
        raise Conflict(
            f"Twilio account {twilio.sid} holds the credential {username} on list {name}, whose password this "
            f"box no longer has: "
            "delete that credential in Twilio's console and provision again"
        )
    on_trunk = trunk is not None and listed is not None and listed in await twilio.lists_on(trunk.sid)
    terminated = trunk is not None and trunk.domain_name == host
    steps = [
        f"Twilio: a trunk sending calls to {origination}: {'stands' if trunk else 'to do'}",
        f"Twilio: dialled at {host}: {'stands' if terminated else 'to do'}",
        f"Twilio: credential list {name}: {'stands' if listed else 'to do'}",
        f"Twilio: the org's credential {username} on it: {'stands' if holds else 'to do'}",
        f"Twilio: the trunk asks for it: {'stands' if on_trunk else 'to do'}",
    ]
    at_twilio = TwilioSurvey(
        twilio=twilio,
        trunk=trunk,
        host=host,
        list_name=name,
        listed=listed,
        username=username,
        holds=holds,
        on_trunk=on_trunk,
    )
    return OutboundSurvey(steps=steps, address=host, twilio=at_twilio)


async def _twilio_provisioned(
    session: AsyncSession, handles: Handles, carrier: CarrierAccount, survey: TwilioSurvey, env: Env
) -> str:
    twilio = survey.twilio
    trunk = survey.trunk or await twilio.trunk_made(domain_of(handles), origination_uri(sip_domain_of(handles, env)))
    if trunk.domain_name != survey.host:
        await twilio.terminated(trunk.sid, survey.host)
    listed = survey.listed or await twilio.credential_list_made(survey.list_name)
    outbound = carrier.outbound
    if not survey.holds:
        outbound = Termination(host=survey.host, username=survey.username, password=secrets.token_urlsafe(24))
        await twilio.credential_added(listed, outbound.username, outbound.password)
    elif outbound is not None and outbound.host != survey.host:
        # The trunk was given the box's host just now (its name changed): dial where it answers.
        outbound = outbound.model_copy(update={"host": survey.host})
    if not survey.on_trunk:
        await twilio.list_attached(trunk.sid, listed)
    await accounts.seal_carrier(session, handles.vault, replace(carrier, outbound=outbound))
    return trunk.sid


async def carrier_for_number(session: AsyncSession, handles: Handles, scope: Scope, shown: str) -> CarrierAccount:
    """The org's account the number shown dials through, ready to dial; Conflict says what is missing."""
    account = next((route.account for route in await phone_routes_of(session, scope) if route.number == shown), None)
    if account is None:
        raise Conflict(f"{shown} was hooked by the org or bought by the box: it dials through no account of the org")
    carrier = await accounts.carrier_named(session, handles.vault, scope.org, account)
    missing = missing_to_dial(carrier)
    if missing:
        raise Conflict(missing[0])
    return carrier


def _leg_through(carrier: CarrierAccount, shown: str) -> LegTrunk:
    dialled = dialled_of(carrier)
    return LegTrunk(
        hostname=dialled.hostname,
        transport=dialled.transport,
        username=dialled.username,
        password=dialled.password,
        shown=shown,
    )


async def phone_routes_of(session: AsyncSession, scope: Scope) -> list[Route]:
    """The org's phone numbers in the scope's env, each with the agent that answers it."""
    return [
        route for route in await channels.routes_of_org(session, scope.org, scope.env) if route.channel is Channel.phone
    ]
