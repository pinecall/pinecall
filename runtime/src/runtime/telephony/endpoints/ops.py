"""The operator's telephony: the numbers account, every number and route, the catalog, the fence, the test line."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.accounts.service import orgs
from runtime.actor import Scope
from runtime.auth import TheOperator
from runtime.enums import Env
from runtime.handles import TheHttp, TheServers, TheVault
from runtime.kit.text import parse_e164
from runtime.postgres import TheBoxSession
from runtime.telephony.auth import TheAgentsHeld, TheOrgAsked, TheSipNames
from runtime.telephony.schemas import carriers
from runtime.telephony.schemas import ops as schemas
from runtime.telephony.service import accounts, networks, number_hook, numbers, outbound, rebuild, test_line
from runtime.telephony.service.number_hook import NumberImport
from runtime.telephony.service.twilio import TwilioAccount
from runtime.wire.worker import RouteRow

router = APIRouter()


# ── the account the box buys numbers on ──


@router.get("/v1/ops/numbers-account")
async def get_numbers_account(_actor: TheOperator, vault: TheVault, session: TheBoxSession) -> schemas.NumbersAccount:
    """The account the box buys numbers on, by its SID and label; 404 when it holds none."""
    return schemas.NumbersAccount.of(await accounts.get_numbers_account(session, vault))


@router.put("/v1/ops/numbers-account")
async def put_numbers_account(
    body: carriers.TwilioAccount, _actor: TheOperator, vault: TheVault, http: TheHttp, session: TheBoxSession
) -> schemas.NumbersAccount:
    """Keep the account the box buys numbers on, verified and sealed; it replaces the one held."""
    account = TwilioAccount(body.account_sid, body.user, body.secret, body.label)
    return schemas.NumbersAccount.of(await accounts.put_box_twilio(session, vault, http, account))


@router.delete("/v1/ops/numbers-account", status_code=204)
async def delete_numbers_account(_actor: TheOperator, session: TheBoxSession) -> None:
    """Forget it: the box buys no numbers from now on, and the ones it bought keep ringing."""
    await accounts.delete_box_twilio(session)


# ── every number ──


@router.get("/v1/ops/numbers")
async def list_box_numbers(_actor: TheOperator, held: TheAgentsHeld, session: TheBoxSession) -> list[schemas.BoxNumber]:
    """Every number the box answers at, of every org and env, by number."""
    return [schemas.BoxNumber.of(number) for number in await numbers.list_box_numbers(session, held)]


@router.post("/v1/ops/numbers/{number}/approve", status_code=204)
async def approve_box_number(number: str, actor: TheOperator, org: TheOrgAsked, session: TheBoxSession) -> None:
    """Approve that a number the org hooked is the org's."""
    await numbers.approve_number(session, org.id, org.slug, parse_e164(number), actor.name)


# ── the carriers ──


@router.get("/v1/ops/carriers")
async def list_box_carriers(_actor: TheOperator, session: TheBoxSession) -> schemas.BoxCarriers:
    """The catalog, each carrier admitted or not with the numbers it brings, and the fence now."""
    return schemas.BoxCarriers.of(await numbers.get_box_carriers(session))


@router.put("/v1/ops/carriers/{kind}")
async def admit_box_carrier(
    kind: str, body: schemas.AdmitCarrierRequest, _actor: TheOperator, session: TheBoxSession
) -> schemas.BoxCarrier:
    """Admit a carrier of the catalog, or stop admitting it; Twilio is admitted always."""
    return schemas.BoxCarrier.of(await numbers.admit_box_carrier(session, kind, on=body.admitted))


# Once, when the box's SIP moves off its names or a name is retired: the runtime never touches a
# carrier on its own.
@router.post("/v1/ops/sip/repoint")
async def repoint_trunks(
    _actor: TheOperator,
    vault: TheVault,
    http: TheHttp,
    names: TheSipNames,
    session: TheBoxSession,
    body: schemas.RepointRequest | None = None,
) -> list[schemas.RepointedTrunk]:
    """Send every Twilio trunk at an env's name, or a former one, to that env's SIP name."""
    moved = await outbound.repoint_trunks(session, vault, http, names, None if body is None else body.former)
    return [schemas.RepointedTrunk.of(trunk) for trunk in moved]


@router.get("/v1/ops/carrier-networks")
async def list_carrier_networks(
    _actor: TheOperator, session: TheBoxSession, state: Annotated[schemas.NetworkStateName | None, Query()] = None
) -> list[schemas.CarrierNetworkRow]:
    """Every network an org asked 5060 to open to, or those in one state, oldest first."""
    return [schemas.CarrierNetworkRow.of(asked) for asked in await networks.list_asked(session, state)]


@router.post("/v1/ops/carrier-networks/{ask}/approve")
async def approve_carrier_network(
    ask: int, actor: TheOperator, vault: TheVault, servers: TheServers, session: TheBoxSession
) -> schemas.CarrierNetworkRow:
    """Put the network on the firewall's list, and admit the org's numbers it fences."""
    decided = await rebuild.approve_network(session, vault, servers, ask, actor.name)
    return schemas.CarrierNetworkRow.of(decided)


@router.post("/v1/ops/carrier-networks/{ask}/refuse")
async def refuse_carrier_network(
    ask: int, actor: TheOperator, vault: TheVault, servers: TheServers, session: TheBoxSession
) -> schemas.CarrierNetworkRow:
    """Keep the network off the fence's list; numbers it alone fenced are let go of on the SFU."""
    decided = await rebuild.refuse_network(session, vault, servers, ask, actor.name)
    return schemas.CarrierNetworkRow.of(decided)


# ── the operator's routes ──


@router.get("/v1/ops/routes")
async def list_box_routes(
    org: TheOrgAsked, session: TheBoxSession, env: Annotated[Env, Query()] = Env.production
) -> list[RouteRow]:
    """Every number the org answers at in the env, oldest first."""
    found = await numbers.list_routes_of(session, org.id, env)
    return [RouteRow.model_validate(route, from_attributes=True) for route in found]


# One row per number per org: a number added again moves. It is admitted on the SFU at once;
# the carrier is never touched, so it rings only where the carrier already points it here.
@router.post("/v1/ops/routes")
async def add_box_route(
    body: schemas.RouteRequest,
    _actor: TheOperator,
    vault: TheVault,
    http: TheHttp,
    servers: TheServers,
    names: TheSipNames,
    session: TheBoxSession,
) -> RouteRow:
    """A number answered by this org's agent, in this env, on this channel."""
    org = await orgs.get_org(session, body.org)
    wanted = NumberImport(Scope(org.id, body.env), body.agent, body.number, channel=body.channel)
    typed = await number_hook.type_route(session, vault, http, servers, names, wanted)
    return RouteRow.model_validate(typed.route, from_attributes=True)


@router.delete("/v1/ops/routes/{number}", status_code=204)
async def delete_box_route(number: str, org: TheOrgAsked, servers: TheServers, session: TheBoxSession) -> None:
    """The org's route at the number forgotten, and its admission; 404 for a number nobody typed."""
    await numbers.release_named(session, servers, org.id, org.slug, number)


# ── the box's test line ──


@router.get("/v1/ops/test-line")
async def get_test_line(_actor: TheOperator, session: TheBoxSession) -> schemas.BoxTestLine:
    """The box's test line: the sandbox number a person calls to reach their own agent, or null."""
    return schemas.BoxTestLine(number=await test_line.find_test_line(session))


@router.put("/v1/ops/test-line")
async def put_test_line(body: schemas.BoxTestLine, _actor: TheOperator, session: TheBoxSession) -> schemas.BoxTestLine:
    """Make one of the box's own sandbox numbers the test line, or forget it with a null number."""
    return schemas.BoxTestLine(number=await test_line.put_test_line(session, body.number))
