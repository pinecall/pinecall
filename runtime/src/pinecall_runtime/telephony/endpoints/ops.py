"""The operator's telephony: the numbers account, every number, the carriers and the fence, a traceback."""

import dataclasses
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Query, Request

from pinecall_runtime.accounts.service import members, orgs
from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.billing import service as billing
from pinecall_runtime.billing.schemas import OrgQuotas
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Env, NetworkState, RouteOrigin
from pinecall_runtime.exceptions import NotFound, ServiceUnavailable
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.knowledge import service as knowledge
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.telephony import schemas
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.telephony.auth import TheOperator
from pinecall_runtime.telephony.service import RouteRecord, accounts, catalog, dial_policy, networks, sip
from pinecall_runtime.telephony.service.catalog import KnownCarrier
from pinecall_runtime.telephony.service.networks import NetworkAsk

router = APIRouter()

NO_NUMBERS_ACCOUNT = "this box holds no Twilio account to buy numbers on: PUT one here"


# ── the account the box buys numbers on ──


@router.get("/v1/ops/numbers-account")
async def numbers_account(_actor: TheOperator, handles: TheHandles, session: Session) -> schemas.NumbersAccount:
    """The account the box buys numbers on, by its SID and label; 404 when it holds none."""
    try:
        account = await accounts.box_twilio(session, handles.vault)
    except ServiceUnavailable:
        raise NotFound(NO_NUMBERS_ACCOUNT) from None
    return schemas.NumbersAccount(account_sid=account.account_sid, label=account.label)


# Tried against Twilio before it is kept, as an org's account is: a pair Twilio refuses is never
# the account a purchase fails on later.
@router.put("/v1/ops/numbers-account")
async def put_numbers_account(
    body: schemas.TwilioAccount, _actor: TheOperator, handles: TheHandles, session: Session
) -> schemas.NumbersAccount:
    """Keep the account the box buys numbers on, sealed; it replaces the one held."""
    await accounts.verify_account(handles.http, body)
    await accounts.put_box_twilio(session, handles.vault, body)
    return schemas.NumbersAccount(account_sid=body.account_sid, label=body.label)


@router.delete("/v1/ops/numbers-account", status_code=204)
async def drop_numbers_account(_actor: TheOperator, session: Session) -> None:
    """Forget it: the box buys no numbers from now on, and the ones it bought keep ringing."""
    if not await accounts.drop_box_twilio(session):
        raise NotFound(NO_NUMBERS_ACCOUNT)


# ── every number ──


# What a number would do if it rang now: whose it is, how it came, and whether anyone picks up.
@router.get("/v1/ops/numbers")
async def list_box_numbers(_actor: TheOperator, request: Request, session: Session) -> list[schemas.BoxNumber]:
    """Every number the box answers at, of every org and env, by number."""
    registry: AgentRegistry = request.app.state.registry
    with box_wide():
        slugs = {org.id: org.slug for org in await orgs.list_orgs(session)}
        found = await telephony.records_on_the_box(session)
    running = {
        (route.org, route.env): {held.slug for held in registry.holding(Scope(route.org, route.env), every_scope=True)}
        for route in (record.route for record in found)
    }
    return [
        schemas.BoxNumber(
            number=record.route.number,
            channel=record.route.channel,
            org=slugs.get(record.route.org, record.route.org),
            env=record.route.env,
            agent=record.route.agent,
            came_in=_came_in(record),
            running=record.route.agent in running[(record.route.org, record.route.env)],
            via=record.route.via,
            approved=record.route.approved,
        )
        for record in found
    ]


# A number an org hooked proves nothing of whose it is: the operator says it is the org's, and a
# call to it opens from then on. Refused, it is let go of (DELETE /v1/ops/routes/{number}).
@router.post("/v1/ops/numbers/{number}/approve", status_code=204)
async def approve_box_number(number: str, actor: TheOperator, session: Session, org: Annotated[str, Query()]) -> None:
    """Approve that a number the org hooked is the org's."""
    with box_wide():
        found = await orgs.get_org(session, org)
        if not await channels.approve_route(session, found.id, parse_e164(number), actor.name):
            raise NotFound(f"no number {number} of org {org} waits for approval")


# ── the carriers ──


@router.get("/v1/ops/carriers")
async def list_box_carriers(_actor: TheOperator, session: Session) -> schemas.BoxCarriers:
    """The catalog, each carrier admitted or not with the numbers it brings, and the fence now."""
    with box_wide():
        admitted = await catalog.admitted_kinds(session)
        through = Counter(_comes_through(record) for record in await telephony.records_on_the_box(session))
        found = await catalog.openings(session)
    return schemas.BoxCarriers(
        carriers=[_box_carrier(carrier, admitted, through[carrier.kind]) for carrier in catalog.KNOWN.values()],
        fence=schemas.BoxFence(
            openings=[schemas.FenceOpening(network=opening.network, reason=opening.reason) for opening in found],
            networks=catalog.every_network(found),
        ),
    )


# On, every org sees it under Add a number, and its networks join the fence's list for the cloud's
# firewall (`fence export`, then Terraform).
@router.put("/v1/ops/carriers/{kind}")
async def admit_box_carrier(
    kind: str, body: schemas.AdmitCarrierRequest, _actor: TheOperator, session: Session
) -> schemas.BoxCarrier:
    """Admit a carrier of the catalog, or stop admitting it; Twilio is admitted always."""
    with box_wide():
        admitted = await catalog.admit(session, kind, on=body.admitted)
        through = Counter(_comes_through(record) for record in await telephony.records_on_the_box(session))
    return _box_carrier(catalog.known_carrier(kind), admitted, through[kind])


# Once, when the box's SIP moves off its names or a name is retired: the runtime never touches a
# carrier on its own.
@router.post("/v1/ops/sip/repoint")
async def repoint_trunks(
    _actor: TheOperator, handles: TheHandles, session: Session, body: schemas.RepointRequest | None = None
) -> list[schemas.RepointedTrunk]:
    """Send every Twilio trunk at an env's name, or a former one, to that env's SIP name."""
    with box_wide():
        moved = await sip.repointed(session, handles, None if body is None else body.former)
    return [
        schemas.RepointedTrunk(account=item.account, trunk=item.trunk, world=item.world, was=item.was, now=item.now)
        for item in moved
    ]


@router.get("/v1/ops/carrier-networks")
async def list_carrier_networks(
    _actor: TheOperator, session: Session, state: Annotated[NetworkState | None, Query()] = None
) -> list[schemas.CarrierNetworkRow]:
    """Every network an org asked 5060 to open to, or those in one state, oldest first."""
    with box_wide():
        slugs = {org.id: org.slug for org in await orgs.list_orgs(session)}
        return [_network_row(ask, slugs) for ask in await networks.listed(session, state)]


@router.post("/v1/ops/carrier-networks/{ask}/approve")
async def approve_carrier_network(
    ask: int, actor: TheOperator, handles: TheHandles, session: Session
) -> schemas.CarrierNetworkRow:
    """Put the network on the firewall's list, and admit the org's numbers it fences."""
    return await _decided(session, handles, ask, NetworkState.approved, actor.name)


@router.post("/v1/ops/carrier-networks/{ask}/refuse")
async def refuse_carrier_network(
    ask: int, actor: TheOperator, handles: TheHandles, session: Session
) -> schemas.CarrierNetworkRow:
    """Keep the network off the fence's list; numbers it alone fenced are let go of on the SFU."""
    return await _decided(session, handles, ask, NetworkState.refused, actor.name)


# ── a carrier's traceback ──


# ── an org as it stands, and its dial guards ──


# `holding` is what the org has now, never a fold of the log: usage is /v1/ops/usage.
@router.get("/v1/ops/orgs/{named}")
async def org_standing(named: str, _actor: TheOperator, session: Session) -> schemas.OrgProfile:
    """One org as it stands: its quotas per env, its dial guards, and what it holds."""
    with box_wide():
        org = await orgs.get_org(session, named)
        quotas = {env: OrgQuotas.of(await billing.get_quotas(session, org.id, env)) for env in Env}
        holding = schemas.OrgHolding(
            memory_facts=sum([await knowledge.facts_kept(session, org.id, env) for env in Env]),
            knowledge_chunks=sum([await knowledge.chunks_kept(session, org.id, env) for env in Env]),
            numbers=sum([await channels.managed_in(session, org.id, env) for env in Env]),
            seats=await members.seats_taken(session, org.id),
        )
        guards = await dial_policy.guards_of(session, org.id)
    return schemas.OrgProfile(
        id=org.id,
        slug=org.slug,
        name=org.name,
        quotas=quotas,
        dialling=schemas.DialGuards(**dataclasses.asdict(guards)),
        holding=holding,
    )


# The operator's: an org able to lift its own dial guards would have none.
@router.put("/v1/ops/orgs/{named}/dialling")
async def put_dialling(
    named: str, body: schemas.PutDialGuards, _actor: TheOperator, session: Session
) -> schemas.DialGuards:
    """The org's dial guards, replaced whole; one left out is the default."""
    guards = dial_policy.Guards(**body.model_dump(exclude_none=True))
    with box_wide():
        org = await orgs.get_org(session, named)
        await dial_policy.put_guards(session, org.id, guards)
    return schemas.DialGuards(**dataclasses.asdict(guards))


@router.get("/v1/ops/traceback")
async def number_traceback(
    actor: TheOperator,
    session: Session,
    number: Annotated[str, Query()],
    since: Annotated[float | None, Query()] = None,
) -> schemas.Traceback:
    """What the box keeps of one number since a day: every phone call with it and every dial to it."""
    return await calls.traceback_of(session, number, since, read_by=actor.name)


# ── private ──


def _came_in(record: RouteRecord) -> schemas.NumberCameIn:
    match record.route.origin, record.carrier:
        case RouteOrigin.imported, "twilio" | "sip" | "whatsapp" as kind:
            return kind
        case RouteOrigin.imported, _:
            return "imported"
        case RouteOrigin.bought, _:
            return "bought"
        case RouteOrigin.hooked, _:
            return "hooked"
        case _, _:
            return "typed"


def _box_carrier(carrier: KnownCarrier, admitted: frozenset[str], numbers: int) -> schemas.BoxCarrier:
    return schemas.BoxCarrier(
        kind=carrier.kind,
        name=carrier.name,
        control=carrier.control,
        networks=list(carrier.networks),
        source=carrier.source,
        read_on=carrier.read_on.isoformat(),
        admitted=carrier.kind in admitted,
        fixed=carrier.kind == catalog.BOX_CARRIER,
        numbers=numbers,
    )


# A number with no account, no carrier named and no networks of its own is fenced to Twilio's.
def _comes_through(record: RouteRecord) -> str | None:
    if record.route.via is not None:
        return record.route.via
    if record.carrier is not None:
        return record.carrier
    if record.route.managed or record.route.origin in {RouteOrigin.hooked, RouteOrigin.typed}:
        return catalog.BOX_CARRIER
    return None


def _network_row(ask: NetworkAsk, slugs: dict[str, str]) -> schemas.CarrierNetworkRow:
    return schemas.CarrierNetworkRow(
        id=ask.id,
        org=slugs.get(ask.org, ask.org),
        source=ask.source,
        network=ask.network,
        state=ask.state,
        asked_at=ask.asked_at,
        decided_by=ask.decided_by,
        decided_at=ask.decided_at,
    )


async def _decided(
    session: Session, handles: TheHandles, ask: int, state: NetworkState, by: str
) -> schemas.CarrierNetworkRow:
    with box_wide():
        decided = await networks.decide(session, ask, state, by)
        await sip.readmit(session, handles, decided.org)
        slugs = {org.id: org.slug for org in await orgs.list_orgs(session)}
    return _network_row(decided, slugs)
