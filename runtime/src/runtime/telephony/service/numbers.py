"""An org's numbers as they stand: each with what a call to it does, what its accounts own, one let go or moved."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as org_accounts
from runtime.actor import Scope
from runtime.enums import Channel, Env, RouteOrigin
from runtime.exceptions import NotFound
from runtime.fleet import service as fleet
from runtime.kit.crypto import Vault
from runtime.kit.text import parse_e164
from runtime.kit.time import now
from runtime.livekit import Servers
from runtime.scoping import box_wide
from runtime.telephony.models import CarrierKind, Route
from runtime.telephony.repository import Numbered, RouteRepository
from runtime.telephony.service import accounts, catalog, fence, number_path, rebuild, sfu
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.catalog import BOX_CARRIER, Admission
from runtime.telephony.service.hand_over import AgentsHeld
from runtime.telephony.service.number_path import StepState

# `bought` on the box's account; `twilio`, `sip`, `whatsapp` the org's account it was imported
# from; `imported` from an account since forgotten; `hooked` pointed at the box by the org itself;
# `typed` a row the box's operator wrote.
type CameIn = Literal["bought", "twilio", "sip", "whatsapp", "imported", "hooked", "typed"]

IMPORTED_FROM: dict[CarrierKind, CameIn] = {
    CarrierKind.twilio: "twilio",
    CarrierKind.sip: "sip",
    CarrierKind.whatsapp: "whatsapp",
}
NOT_IN_THE_ENV = "the org answers at no {number} in the {env}"
NOT_IN_EITHER_ENV = "the org answers no {number} in either env"


@dataclass(frozen=True, slots=True)
class Listed:
    """A number of the org, the agent it reaches, how it was written, and what a call to it does now."""

    route: Route
    # Read off the tables; `number_path.path_of` says why.
    rings: StepState = "ok"

    @property
    def origin(self) -> RouteOrigin:
        """How its row was written."""
        return self.route.origin

    @property
    def last_call_at(self) -> datetime | None:
        """When a call to it last reached the box; None when none ever did."""
        return self.route.last_call_at

    @property
    def via(self) -> str | None:
        """The carrier of the box's catalog a hooked number comes through."""
        return self.route.via

    @property
    def account(self) -> str | None:
        """The org's account the number lives in; None for one with none."""
        return self.route.account


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
class Available:
    """What the org's accounts own, and the kind of the account that lists them."""

    kind: str
    numbers: list[OwnedNumber]


@dataclass(frozen=True, slots=True)
class Offered:
    """What Add a number offers beside the org's own accounts: the carriers admitted, and whether numbers are sold."""

    carriers: list[catalog.KnownCarrier]
    sells: bool
    # The name a carrier or a PBX sends the env's calls to, on port 5060; None where there is none.
    sip_domain: str | None


@dataclass(frozen=True, slots=True)
class BoxCarriers:
    """The catalog as the box stands with it, and the fence: what 5060 opens to beyond Twilio's, and every network."""

    carriers: list[Admission]
    openings: list[fence.Opening]
    # Twilio's first, then each opening: Terraform's `sip_sources` (`fence export`).
    networks: list[str]


@dataclass(frozen=True, slots=True)
class BoxNumber:
    """A number the box answers at, how it came, and who picks it up."""

    number: str
    channel: Channel
    # The org by its slug, as the operator reads it.
    org: str
    env: Env
    agent: str
    came_in: CameIn
    # A process holds the agent in the org and env now: a call to the number is answered.
    running: bool
    via: str | None
    # False for a number the org hooked that waits for the operator: no call to it opens.
    approved: bool


# ── an org's numbers ──


# Twilio drives its own numbers; a guided carrier is SIP terms, a number pasted into its portal.
async def get_offer(session: AsyncSession, vault: Vault, names: SipNames, env: Env) -> Offered:
    """The carriers this box admits, whether it sells numbers, and where a carrier sends the env's calls."""
    return Offered(
        carriers=await catalog.list_offered(session),
        sells=await accounts.sells_numbers(session, vault),
        sip_domain=names.sip_domains.get(env),
    )


async def list_numbers(session: AsyncSession, vault: Vault, held: AgentsHeld, scope: Scope) -> list[Listed]:
    """The org's numbers in the env, oldest first, and what a call to each does now."""
    found = await RouteRepository(session).list_of_org(scope.org, scope.env)
    routes = [numbered.route for numbered in found]
    running = held.list_held(scope.org, scope.env)
    rings = await number_path.rings_of(session, vault, routes, lambda route: route.agent in running)
    return [Listed(route, ringing) for route, ringing in zip(routes, rings, strict=True)]


async def get_number(session: AsyncSession, org: str, number: str, env: Env | None = None) -> Route:
    """The org's number, in the env when one is named; NotFound otherwise."""
    numbered = await RouteRepository(session).find(org, number)
    if numbered is None or (env is not None and numbered.route.env is not env):
        sentence = NOT_IN_EITHER_ENV if env is None else NOT_IN_THE_ENV
        raise NotFound(sentence.format(number=number, env=env))
    return numbered.route


async def get_path(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, names: SipNames, held: AgentsHeld, route: Route
) -> number_path.NumberPath:
    """What a call to the org's number goes through now, its carrier asked."""
    running = route.agent in held.list_held(route.org, route.env)
    return await number_path.path_of(session, vault, http, names, route, running=running)


# A SIP peer owns what it owns and nobody here can list it: its import takes the number typed.
async def list_owned(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, scope: Scope, account: str | None = None
) -> Available:
    """The kind of the org's accounts, and every number they own as their parties list them."""
    if account is None:
        carriers = await accounts.list_carriers(session, vault, scope.org)
    else:
        carriers = [await accounts.get_carrier(session, vault, scope.org, account)]
    if not carriers:
        raise NotFound("the org has no carrier account: PUT /v1/carrier brings a Twilio account or a SIP peer")
    repository = RouteRepository(session)
    imported = {numbered.route.number for numbered in await repository.list_of_org(scope.org, scope.env)}
    with box_wide():
        elsewhere = await repository.list_numbers_of_others(scope.org)
    owned = [
        OwnedNumber(
            number=found.number,
            name=found.name,
            imported=found.number in imported,
            held_elsewhere=found.number in elsewhere,
            account=carrier.id,
        )
        for carrier in carriers
        for found in await carrier.list_owned(http)
    ]
    lister = next((carrier for carrier in carriers if carrier.has_api), carriers[0])
    return Available(kind=lister.kind.value, numbers=owned)


# ── one let go, moved ──


async def release_number(session: AsyncSession, servers: Servers, route: Route) -> None:
    """Let the number go: the route, its env's LiveKit's trunks and rule; the account keeps it."""
    await RouteRepository(session).delete_of(route.org, route.number)
    await sfu.let_go(servers[route.env], route.org, route.number)


async def release_named(session: AsyncSession, servers: Servers, org: str, named: str, number: str) -> None:
    """Let go the number of an org the operator names, whichever env it answers in; NotFound for one nobody routed."""
    with box_wide():
        numbered = await RouteRepository(session).find(org, parse_e164(number))
        if numbered is None:
            raise NotFound(f"no route for {number} in org {named}")
        await release_number(session, servers, numbered.route)


# Until 2026-11 an agent erased, or an org, took its rows with one statement and left the SFU as it
# was: the trunk went on listing each number, and nobody else could import a number so "held".
async def release_numbers_of(
    session: AsyncSession, servers: Servers, org: str, *, agent: str | None = None
) -> list[str]:
    """Let go every number of the org, or those one of its agents answers; the numbers let go."""
    with box_wide():
        routes = list(await RouteRepository(session).list_of_agent(org, agent))
        for route in routes:
            await release_number(session, servers, route)
    return [route.number for route in routes]


# Where both envs share a LiveKit the number keeps its trunk and changes rules; where each has
# its own, it leaves the old env's LiveKit and is admitted on the new one's. The row moves first:
# a LiveKit that refuses raises, and the request's transaction takes the move back.
async def move_number(session: AsyncSession, vault: Vault, servers: Servers, route: Route, env: Env) -> Route:
    """Move the number into the other env: its row, and its trunk and rule on that LiveKit."""
    if route.env is env:
        return route
    await RouteRepository(session).update(route, env=env)
    # A WhatsApp number is on no trunk: its env is its row alone.
    if route.channel is Channel.phone:
        fencing = await rebuild.fencing_of(session, vault, route.org)
        await rebuild.readmit_number(servers, route, fencing, await fleet.get_fleets(session))
    return route


# ── the operator's ──


def came_in(numbered: Numbered) -> CameIn:
    """How the number came to the box, by the account it was imported from when one is known."""
    match numbered.route.origin:
        case RouteOrigin.imported:
            return "imported" if numbered.carrier_kind is None else IMPORTED_FROM[numbered.carrier_kind]
        case RouteOrigin.bought:
            return "bought"
        case RouteOrigin.hooked:
            return "hooked"
        case RouteOrigin.typed:
            return "typed"


# A number with no account, no carrier named and no networks of its own is fenced to Twilio's. The
# kind of an account and the kind of a catalog carrier are two vocabularies: only an account whose
# kind the catalog also names (Twilio) is counted under it.
def comes_through(numbered: Numbered) -> str | None:
    """The catalog carrier the number reaches the box through; None for a peer's, Meta's, or one nobody knows."""
    route = numbered.route
    if route.via is not None:
        return route.via
    if numbered.carrier_kind is not None:
        return numbered.carrier_kind.value if numbered.carrier_kind.value in catalog.KNOWN else None
    if route.managed or route.origin in {RouteOrigin.hooked, RouteOrigin.typed}:
        return BOX_CARRIER
    return None


# What a number would do if it rang now: whose it is, how it came, and whether anyone picks up.
async def list_box_numbers(session: AsyncSession, held: AgentsHeld) -> list[BoxNumber]:
    """Every number the box answers at, of every org and env, by number."""
    with box_wide():
        slugs = {org.id: org.slug for org in await org_accounts.list_orgs(session)}
        found = await RouteRepository(session).list_on_the_box()
    scopes = {(numbered.route.org, numbered.route.env) for numbered in found}
    running = {(org, env): held.list_held(org, env) for org, env in scopes}
    return [
        BoxNumber(
            number=numbered.route.number,
            channel=numbered.route.channel,
            org=slugs.get(numbered.route.org, numbered.route.org),
            env=numbered.route.env,
            agent=numbered.route.agent,
            came_in=came_in(numbered),
            running=numbered.route.agent in running[(numbered.route.org, numbered.route.env)],
            via=numbered.route.via,
            approved=numbered.route.approved,
        )
        for numbered in found
    ]


# A number an org hooked proves nothing of whose it is: the operator says it is the org's, and a
# call to it opens from then on. Refused, it is let go of (DELETE /v1/ops/routes/{number}).
async def approve_number(session: AsyncSession, org: str, named: str, number: str, by: str) -> None:
    """The operator's word that the org's hooked number is the org's; NotFound when none waited."""
    with box_wide():
        if not await RouteRepository(session).approve(org, number, by=by, at=now()):
            raise NotFound(f"no number {number} of org {named} waits for approval")


async def get_box_carriers(session: AsyncSession) -> BoxCarriers:
    """The catalog, each carrier admitted or not with the numbers it brings, and the fence now."""
    admitted = await catalog.list_admitted(session)
    through = await _count_through(session)
    openings = await fence.list_openings(session)
    return BoxCarriers(
        carriers=[_admission_of(carrier, admitted, through) for carrier in catalog.CATALOG],
        openings=openings,
        networks=fence.list_every_network(openings),
    )


async def admit_box_carrier(session: AsyncSession, kind: str, *, on: bool) -> Admission:
    """Admit a carrier of the catalog, or stop admitting it; the carrier as it stands after."""
    admitted = await catalog.admit(session, kind, on=on)
    return _admission_of(catalog.get_known(kind), admitted, await _count_through(session))


async def _count_through(session: AsyncSession) -> Counter[str | None]:
    with box_wide():
        return Counter(comes_through(numbered) for numbered in await RouteRepository(session).list_on_the_box())


def _admission_of(carrier: catalog.KnownCarrier, admitted: frozenset[str], through: Counter[str | None]) -> Admission:
    return Admission(
        carrier=carrier,
        admitted=carrier.kind in admitted,
        fixed=carrier.kind == BOX_CARRIER,
        numbers=through[carrier.kind],
    )


async def list_routes_of(session: AsyncSession, org: str, env: Env) -> Sequence[Route]:
    """Every number the org answers at in the env, oldest first, for the operator."""
    with box_wide():
        return [numbered.route for numbered in await RouteRepository(session).list_of_org(org, env)]
