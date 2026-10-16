"""The numbers endpoints: the org's carrier accounts, its numbers, dialling out, and a worker's leg."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pinecall_runtime.accounts.service import tokens
from pinecall_runtime.calls import service as calls
from pinecall_runtime.exceptions import Conflict, NotFound, ServiceUnavailable
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.kit.time import now, today_in
from pinecall_runtime.postgres import Session
from pinecall_runtime.telephony import schemas
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.telephony.auth import NumbersKey, TalkKey, WorkerKey
from pinecall_runtime.telephony.service import (
    accounts,
    catalog,
    dial_policy,
    dialing,
    fence,
    networks,
    number_path,
    numbers,
    sip,
)
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.dial_policy import Dial
from pinecall_runtime.telephony.service.networks import NetworkAsk
from pinecall_runtime.telephony.service.numbers import NumberImport, NumberPurchase

router = APIRouter()

# A person or a server acts in the org's own scope of its env: numbers are the org's.
AccountAsked = Annotated[str | None, Query()]
DryRun = Annotated[bool, Query()]


# ── the accounts ──


@router.get("/v1/carrier")
async def get_carrier(
    actor: NumbersKey, handles: TheHandles, session: Session, account: AccountAsked = None
) -> schemas.CarrierRow:
    """The org's account, named, never its secret; the only one unless one is asked for."""
    carrier = await accounts.carrier_named(session, handles.vault, actor.org, account)
    return _carrier_row(carrier, await networks.of_org(session, actor.org))


@router.get("/v1/carriers")
async def list_carriers(actor: NumbersKey, handles: TheHandles, session: Session) -> schemas.CarrierList:
    """Every account of the org, oldest first."""
    asks = await networks.of_org(session, actor.org)
    return schemas.CarrierList(
        carriers=[
            _carrier_row(carrier, asks) for carrier in await accounts.carriers_of(session, handles.vault, actor.org)
        ]
    )


# What Add a number offers beside the org's own accounts: Twilio drives its own numbers; a
# guided carrier is SIP terms, a number pasted into its portal.
@router.get("/v1/carriers/catalog")
async def list_carrier_catalog(_actor: NumbersKey, handles: TheHandles, session: Session) -> schemas.CarrierCatalog:
    """The carriers this box admits, each automatic or guided, and whether the box sells numbers."""
    admitted = await catalog.admitted_kinds(session)
    try:
        await accounts.box_twilio(session, handles.vault)
        sells = True
    except ServiceUnavailable:
        sells = False
    return schemas.CarrierCatalog(
        carriers=[
            schemas.CatalogCarrier(
                kind=carrier.kind,
                name=carrier.name,
                how="automatic" if carrier.control else "guided",
                networks=list(carrier.networks),
            )
            for carrier in catalog.KNOWN.values()
            if carrier.kind in admitted
        ],
        sells=sells,
    )


# Bringing an account the org already holds replaces its secret; a Twilio pair is tried first.
@router.put("/v1/carrier")
async def put_carrier(
    body: schemas.Account, actor: NumbersKey, handles: TheHandles, session: Session
) -> schemas.CarrierRow:
    """Keep an account of the org: a Twilio account, a SIP peer, a WhatsApp number at Meta."""
    declared = fence.declared_networks(CarrierAccount(org=actor.org, account=body))
    for network in declared or ():
        networks.checked(network)
    await accounts.verify_account(handles.http, body)
    carrier = await accounts.put_carrier(session, handles.vault, actor.org, body)
    if declared is not None:
        await networks.ask(session, actor.org, carrier.id, declared)
        await sip.readmit(session, handles, actor.org)
    return _carrier_row(carrier, await networks.of_org(session, actor.org))


@router.delete("/v1/carrier", status_code=204)
async def drop_carrier(actor: NumbersKey, handles: TheHandles, session: Session, account: AccountAsked = None) -> None:
    """Forget an account; its numbers stay routed until each is let go."""
    await accounts.drop_carrier(session, handles.vault, actor.org, account)


# ── the numbers ──


@router.get("/v1/numbers")
async def list_numbers(
    actor: NumbersKey, request: Request, handles: TheHandles, session: Session
) -> list[schemas.NumberRow]:
    """The org's numbers in the key's env, and the agent each reaches."""
    records = await telephony.records_of(session, actor.org, actor.env)
    running = _running(request, Scope(actor.org, actor.env))
    rings = await number_path.rings_of(session, handles, records, lambda record: record.route.agent in running)
    return [
        schemas.NumberRow(
            route=schemas.RouteBody.model_validate(record.route, from_attributes=True),
            origin=record.route.origin,
            rings=ringing,
            last_call_at=record.last_call_at,
            via=record.route.via,
            account=record.route.account,
        )
        for record, ringing in zip(records, rings, strict=True)
    ]


@router.get("/v1/numbers/{number}/path")
async def number_path_of(
    number: str, actor: NumbersKey, request: Request, handles: TheHandles, session: Session
) -> schemas.NumberPath:
    """What a call to the number goes through now: its carrier, the fence, the env, the agent."""
    record = await telephony.record_of(session, actor.org, parse_e164(number))
    if record is None or record.route.env is not actor.env:
        raise NotFound(f"the org answers at no {number} in the {actor.env}")
    running = _running(request, Scope(actor.org, actor.env))
    found = await number_path.path_of(session, handles, record, running=record.route.agent in running)
    return schemas.NumberPath(
        number=record.route.number,
        steps=[
            schemas.PathStep(step=step.step, state=step.state, says=step.says, fix=step.fix) for step in found.steps
        ],
        rings=found.rings,
        last_call_at=record.last_call_at,
    )


@router.get("/v1/numbers/available")
async def list_available_numbers(
    actor: NumbersKey, handles: TheHandles, session: Session, account: AccountAsked = None
) -> schemas.AvailableNumbers:
    """What the org's Twilio accounts own, and which of it this env imported."""
    kind, owned = await numbers.owned_numbers(session, handles, _org_scope(actor), account)
    return schemas.AvailableNumbers(
        kind=kind,
        numbers=[
            schemas.OwnedNumberRow(number=item.number, name=item.name, imported=item.imported, account=item.account)
            for item in owned
        ],
    )


@router.post("/v1/numbers")
async def import_number(
    body: schemas.ImportNumberRequest,
    actor: NumbersKey,
    handles: TheHandles,
    session: Session,
    *,
    dry_run: DryRun = False,
) -> schemas.ImportNumberResponse:
    """Hook a number at its account, admit it on the SFU in the key's env, route it."""
    _check_agent(actor, body.agent)
    wanted = NumberImport(
        scope=_org_scope(actor),
        agent=body.agent,
        number=body.number,
        channel=body.channel,
        account=body.account,
        hooked=body.hooked,
        networks=tuple(body.networks),
        via=body.via,
        move=body.move,
    )
    plan = (
        await numbers.plan_import(session, handles, wanted)
        if dry_run
        else await numbers.import_number(session, handles, wanted)
    )
    return schemas.ImportNumberResponse(
        route=schemas.RouteBody.model_validate(plan.route, from_attributes=True), steps=plan.steps, dry_run=plan.dry_run
    )


@router.post("/v1/numbers/buy")
async def buy_number(
    body: schemas.BuyNumberRequest, actor: NumbersKey, handles: TheHandles, session: Session, *, dry_run: DryRun = False
) -> schemas.ImportNumberResponse:
    """Buy a number on the box's account and hook it, counted against the env's stock."""
    _check_agent(actor, body.agent)
    wanted = NumberPurchase(
        scope=_org_scope(actor), agent=body.agent, country=body.country, area_code=body.area_code, channel=body.channel
    )
    plan = (
        await numbers.plan_buy(session, handles, wanted)
        if dry_run
        else await numbers.buy_number(session, handles, wanted)
    )
    return schemas.ImportNumberResponse(
        route=schemas.RouteBody.model_validate(plan.route, from_attributes=True), steps=plan.steps, dry_run=plan.dry_run
    )


@router.delete("/v1/numbers/{number}", status_code=204)
async def release_number(number: str, actor: NumbersKey, handles: TheHandles, session: Session) -> None:
    """Let the number go: its route and its admission; the account keeps it."""
    await numbers.release_number(session, handles, actor.org, parse_e164(number), actor.env)


@router.put("/v1/numbers/{number}/env")
async def move_number(
    number: str, body: schemas.MoveNumberRequest, actor: NumbersKey, handles: TheHandles, session: Session
) -> schemas.NumberRow:
    """Move the number into the other env: its row and the two rules."""
    moved = await numbers.move_number(session, handles, actor.org, parse_e164(number), body.env)
    return schemas.NumberRow(route=schemas.RouteBody.model_validate(moved, from_attributes=True), origin=moved.origin)


# ── dialling out ──


@router.get("/v1/carrier/outbound")
async def get_outbound_status(
    actor: NumbersKey, handles: TheHandles, session: Session, account: AccountAsked = None
) -> schemas.OutboundStatus:
    """Whether the org can place a call, one sentence per thing missing, and its guards."""
    readiness = await dialing.outbound_readiness(session, handles, _org_scope(actor), account)
    return schemas.OutboundStatus(
        ready=readiness.ready,
        kind=readiness.kind,
        from_numbers=readiness.from_numbers,
        steps_missing=readiness.steps_missing,
        guards=_guards_row(readiness.guards),
    )


@router.post("/v1/carrier/outbound", response_model_exclude_unset=True)
async def provision_outbound(
    actor: NumbersKey, handles: TheHandles, session: Session, *, account: AccountAsked = None, dry_run: DryRun = False
) -> schemas.ProvisionOutboundResponse:
    """Make an account dialable: Twilio's termination and a credential; a peer needs nothing."""
    if dry_run:
        done = await dialing.plan_outbound(session, handles, actor.org, actor.env, account)
        return schemas.ProvisionOutboundResponse(steps=done.steps, dry_run=True, ready=False)
    done = await dialing.provision_outbound(session, handles, actor.org, actor.env, account)
    return schemas.ProvisionOutboundResponse(
        steps=done.steps, dry_run=False, ready=done.ready, trunk=done.trunk, address=done.address
    )


@router.post("/v1/agents/{slug}/dial", status_code=202)
async def dial_out(
    slug: str, body: schemas.DialRequest, actor: TalkKey, request: Request, handles: TheHandles, session: Session
) -> schemas.DialResponse:
    """Place a call as the agent, after its guards: the call it became, before anything rings."""
    serving: calls.Serving = request.app.state.serving
    if serving.registry.serving(actor.scope, slug, None) is None:
        raise Conflict(f"nobody holds agent {slug} in this scope: a phone would ring with no app to serve it")
    who = _asked_by(actor)
    placement = calls.Placement(
        scope=actor.scope,
        agent=slug,
        to=body.to,
        shown=body.from_,
        asked_by=who,
        today=today_in(handles.settings.timezone),
        at=now(),
        own_phone=serving.registry.phone_of(actor.env, body.to) == who,
        consent=body.consent,
    )
    placed = await calls.place_call(session, serving, placement)
    signer = serving.signer
    return schemas.DialResponse.model_validate(
        {
            "call": placed.call,
            "agent": slug,
            "to": placed.to,
            "from": placed.shown,
            "env": actor.env,
            "log_token": tokens.log_token(signer, placed.call, body.log),
        }
    )


# The worker's, for a leg into a live call and for the leg a dial placed.
@router.get("/v1/agents/{slug}/outbound-trunk")
async def get_leg_trunk(
    slug: str, actor: WorkerKey, handles: TheHandles, session: Session, query: Annotated[schemas.LegTrunkQuery, Query()]
) -> schemas.LegTrunkResponse:
    """The leg's trunk inline, after the shape and the pace; a dial's own first leg passes."""
    dial = Dial(actor.scope, slug, query.to, query.shown, _asked_by(actor), query.call, now())
    return schemas.LegTrunkResponse(trunk=await dialing.leg_trunk(session, handles, dial))


# The worker's, before it sends the caller on: a REFER dials nothing of the box's, but the carrier
# dials it on the org's bill, so it passes the same guards as a warm transfer's leg.
@router.post("/v1/agents/{slug}/cold-transfer", status_code=204)
async def judge_cold_transfer(
    slug: str, actor: WorkerKey, session: Session, query: Annotated[schemas.ColdTransferQuery, Query()]
) -> None:
    """A cold transfer's leg, past the shape and the pace, its ledger row written."""
    await dial_policy.guard_second_leg(
        session, Dial(actor.scope, slug, query.to, None, _asked_by(actor), query.call, now())
    )


# ── private ──


def _running(request: Request, scope: Scope) -> set[str]:
    serving: calls.Serving = request.app.state.serving
    return {registration.slug for registration in serving.registry.holding(scope, every_scope=True)}


def _check_agent(actor: Actor, agent: str) -> None:
    if actor.person is not None and actor.person.agents and agent not in actor.person.agents:
        raise NotFound(f"agent {agent} is not one this key may act for")


# The one record of who asked, which is what audits a dial.
def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


def _org_scope(actor: Actor) -> Scope:
    return Scope(actor.org, actor.env)


def _carrier_row(carrier: CarrierAccount, asks: list[NetworkAsk]) -> schemas.CarrierRow:
    return schemas.CarrierRow(
        kind=carrier.account.kind,
        account=carrier.id,
        label=carrier.account.label,
        networks=[schemas.NetworkRow(network=ask.network, state=ask.state) for ask in asks if ask.source == carrier.id],
    )


def _guards_row(guards: dial_policy.Guards) -> schemas.DialGuards:
    return schemas.DialGuards(
        dial_anywhere=guards.dial_anywhere,
        per_minute=guards.per_minute,
        per_day=guards.per_day,
        max_duration_s=guards.max_duration_s,
    )
