"""Calling out through an account: whether the org can, the account made dialable, a leg's trunk, trunks repointed."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.compliance import service as compliance
from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, NotFound
from runtime.kit.crypto import Vault
from runtime.telephony.models import Route
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service import accounts, twilio
from runtime.telephony.service.carrier import Carrier, Outbound, SipNames, origination_uri
from runtime.wire.worker import LegTrunk


@dataclass(frozen=True, slots=True)
class Readiness:
    """Whether the org can place a call through an account, what is still missing, and its dial guards."""

    ready: bool
    kind: str | None
    from_numbers: list[str]
    steps_missing: list[str]
    guards: compliance.Guards


@dataclass(frozen=True, slots=True)
class Provisioned:
    """What provisioning did, or would do: one sentence a step, and whether the account can place a call."""

    steps: list[str]
    dry_run: bool
    ready: bool
    trunk: str | None = None
    address: str | None = None


@dataclass(frozen=True, slots=True)
class Repointed:
    """A trunk of an account that sent an env's calls to one URI and now sends them to another."""

    account: str
    trunk: str
    env: Env
    was: str
    now: str


async def list_phone_routes(session: AsyncSession, scope: Scope, *, agent: str | None = None) -> list[Route]:
    """The org's phone numbers in the scope's env, each with the agent that answers it; one agent's when named."""
    found = await RouteRepository(session).list_of_org(scope.org, scope.env, agent=agent, channel=Channel.phone)
    return [numbered.route for numbered in found]


async def get_readiness(session: AsyncSession, vault: Vault, scope: Scope, account: str | None = None) -> Readiness:
    """Whether the org can dial out in the env, one sentence per thing missing, in order."""
    guards = await compliance.guards_of(session, scope.org)
    numbers = [route.number for route in await list_phone_routes(session, scope)]
    try:
        carrier = await accounts.get_carrier(session, vault, scope.org, account)
    except NotFound as absent:
        return Readiness(ready=False, kind=None, from_numbers=numbers, steps_missing=[str(absent)], guards=guards)
    missing = carrier.list_missing_to_dial()
    if not numbers:
        missing.append(f"the org answers at no phone number in the {scope.env}: a call shows one")
    return Readiness(
        ready=not missing, kind=carrier.kind.value, from_numbers=numbers, steps_missing=missing, guards=guards
    )


# Until 2026-11 a dry run answered `ready: false` whatever the account held, and a peer, which needs
# nothing made, read as not ready: `ready` is whether every step stands, said by the account itself.
async def plan_outbound(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, names: SipNames, scope: Scope, account: str | None
) -> Provisioned:
    """What provisioning would write, and nothing written."""
    carrier = await accounts.get_carrier(session, vault, scope.org, account)
    return _provision_of(await carrier.survey_outbound(http, names, scope.env), dry_run=True)


async def provision_outbound(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, names: SipNames, scope: Scope, account: str | None
) -> Provisioned:
    """Make the account dialable: Twilio's termination and a credential; a peer needs nothing."""
    carrier = await accounts.get_carrier(session, vault, scope.org, account)
    done, kept = await carrier.provision_outbound(http, names, scope.env)
    await accounts.seal_carrier(session, vault, kept)
    return _provision_of(done, dry_run=False)


# The worker's, for a leg into a live call and for the leg a dial placed. A refused leg's row is
# written in a transaction of its own (`compliance.guard_second_leg`), so `sessions` is asked for.
async def leg_trunk(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession], vault: Vault, dial: compliance.DialAsk
) -> LegTrunk:
    """How a leg of a live call is dialled, after its guards: the account of the number shown."""
    await compliance.guard_second_leg(session, sessions, dial)
    shown = dial.shown
    if shown is None:
        routes = await list_phone_routes(session, dial.scope, agent=dial.agent)
        if not routes:
            raise NotFound(
                f"agent {dial.agent} answers at no phone number in the {dial.scope.env}: a call back shows one"
            )
        shown = routes[0].number
    return (await get_carrier_for_number(session, vault, dial.scope, shown)).leg_trunk(shown)


async def get_carrier_for_number(session: AsyncSession, vault: Vault, scope: Scope, shown: str) -> Carrier:
    """The org's account the number shown dials through, ready to dial; Conflict says what is missing."""
    routes = await list_phone_routes(session, scope)
    account = next((route.account for route in routes if route.number == shown), None)
    if account is None:
        raise Conflict(f"{shown} was hooked by the org or bought by the box: it dials through no account of the org")
    carrier = await accounts.get_carrier(session, vault, scope.org, account)
    missing = carrier.list_missing_to_dial()
    if missing:
        raise Conflict(missing[0])
    return carrier


# Once, when a box's SIP moves off its names (a cluster: the names are the HTTPS load balancer's) or
# a name is retired for another (`former`, the names an env was reached at before): the runtime
# never touches a carrier on its own, so the operator asks for it.
async def repoint_trunks(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    names: SipNames,
    former: Mapping[Env, Sequence[str]] | None = None,
) -> list[Repointed]:
    """Each trunk of the box's and the orgs' Twilio accounts moved to its env's SIP name."""
    moves = _list_moves(names, former or {})
    if not moves:
        return []
    done: list[Repointed] = []
    for account in await accounts.list_twilio_accounts(session, vault):
        api = twilio.twilio_of(http, account)
        for env, was, now in moves:
            for trunk in await api.list_trunks_pointing_at(was):
                await api.repoint(trunk.sid, was, now)
                done.append(Repointed(account.account_sid, trunk.sid, env, was, now))
    return done


def _provision_of(outbound: Outbound, *, dry_run: bool) -> Provisioned:
    return Provisioned(
        steps=outbound.steps, dry_run=dry_run, ready=outbound.ready, trunk=outbound.trunk, address=outbound.address
    )


# From the env's own name when SIP has a name of its own, and from every former name given.
def _list_moves(names: SipNames, former: Mapping[Env, Sequence[str]]) -> list[tuple[Env, str, str]]:
    moves: list[tuple[Env, str, str]] = []
    for env in Env:
        sip_name = names.sip_domains.get(env)
        if not sip_name:
            continue
        candidates = dict.fromkeys([names.domain or "", *former.get(env, ())])
        moves.extend(
            (env, origination_uri(name), origination_uri(sip_name)) for name in candidates if name and name != sip_name
        )
    return moves
