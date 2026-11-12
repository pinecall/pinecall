"""The org's numbers: listed, a number's path, what its accounts own, one imported, bought, let go or moved."""

from fastapi import APIRouter

from runtime.actor import Scope
from runtime.handles import TheHttp, TheServers, TheVault
from runtime.postgres import Session
from runtime.telephony.auth import (
    AccountAsked,
    DryRun,
    NumbersKey,
    TheAgentsHeld,
    TheNumber,
    TheNumberInEitherEnv,
    TheSipNames,
    check_agent,
)
from runtime.telephony.schemas import numbers as schemas
from runtime.telephony.service import number_hook, numbers
from runtime.telephony.service.number_hook import NumberImport, NumberPurchase

router = APIRouter()


@router.get("/v1/numbers")
async def list_numbers(
    actor: NumbersKey, vault: TheVault, held: TheAgentsHeld, session: Session
) -> list[schemas.NumberRow]:
    """The org's numbers in the key's env, and the agent each reaches."""
    listed = await numbers.list_numbers(session, vault, held, Scope(actor.org, actor.env))
    return [schemas.NumberRow.of(number) for number in listed]


@router.get("/v1/numbers/{number}/path")
async def get_number_path(
    route: TheNumber, vault: TheVault, http: TheHttp, names: TheSipNames, held: TheAgentsHeld, session: Session
) -> schemas.NumberPath:
    """What a call to the number goes through now: its carrier, the fence, the env, the agent."""
    return schemas.NumberPath.of(await numbers.get_path(session, vault, http, names, held, route))


@router.get("/v1/numbers/available")
async def list_available_numbers(
    actor: NumbersKey, vault: TheVault, http: TheHttp, session: Session, account: AccountAsked = None
) -> schemas.AvailableNumbers:
    """What the org's accounts own, and which of it this env imported."""
    owned = await numbers.list_owned(session, vault, http, Scope(actor.org, actor.env), account)
    return schemas.AvailableNumbers.of(owned)


@router.post("/v1/numbers")
async def import_number(
    body: schemas.ImportNumberRequest,
    actor: NumbersKey,
    vault: TheVault,
    http: TheHttp,
    servers: TheServers,
    names: TheSipNames,
    session: Session,
    *,
    dry_run: DryRun = False,
) -> schemas.ImportNumberResponse:
    """Hook a number at its account, admit it on the SFU in the key's env, route it."""
    check_agent(actor, body.agent)
    wanted = NumberImport(
        scope=Scope(actor.org, actor.env),
        agent=body.agent,
        number=body.number,
        channel=body.channel,
        account=body.account,
        hooked=body.hooked,
        networks=tuple(body.networks),
        via=body.via,
        move=body.move,
    )
    hook = number_hook.plan_import if dry_run else number_hook.import_number
    return schemas.ImportNumberResponse.of(await hook(session, vault, http, servers, names, wanted))


@router.post("/v1/numbers/buy")
async def buy_number(
    body: schemas.BuyNumberRequest,
    actor: NumbersKey,
    vault: TheVault,
    http: TheHttp,
    servers: TheServers,
    names: TheSipNames,
    session: Session,
    *,
    dry_run: DryRun = False,
) -> schemas.ImportNumberResponse:
    """Buy a number on the box's account and hook it, counted against the env's stock."""
    check_agent(actor, body.agent)
    scope = Scope(actor.org, actor.env)
    wanted = NumberPurchase(scope, body.agent, body.country, body.area_code, body.channel)
    hook = number_hook.plan_buy if dry_run else number_hook.buy_number
    return schemas.ImportNumberResponse.of(await hook(session, vault, http, servers, names, wanted))


@router.delete("/v1/numbers/{number}", status_code=204)
async def release_number(route: TheNumber, servers: TheServers, session: Session) -> None:
    """Let the number go: its route and its admission; the account keeps it."""
    await numbers.release_number(session, servers, route)


@router.put("/v1/numbers/{number}/env")
async def move_number(
    route: TheNumberInEitherEnv, body: schemas.MoveNumberRequest, vault: TheVault, servers: TheServers, session: Session
) -> schemas.NumberRow:
    """Move the number into the other env: its row and the two rules."""
    moved = await numbers.move_number(session, vault, servers, route, body.env)
    return schemas.NumberRow.of(numbers.Listed(moved))
