"""The org's carrier accounts: one brought, listed and let go, the catalog it may bring from, and calling out."""

from fastapi import APIRouter

from runtime.handles import TheHttp, TheServers, TheVault
from runtime.postgres import Session
from runtime.telephony.auth import AccountAsked, DryRun, NumbersKey, TheSipNames
from runtime.telephony.schemas import carriers as schemas
from runtime.telephony.service import accounts, numbers, outbound, rebuild

router = APIRouter()


@router.get("/v1/carrier")
async def get_carrier(
    actor: NumbersKey, vault: TheVault, session: Session, account: AccountAsked = None
) -> schemas.CarrierRow:
    """The org's account, named, never its secret; the only one unless one is asked for."""
    carrier = await accounts.get_carrier(session, vault, actor.org, account)
    return schemas.CarrierRow.of(await accounts.describe_carrier(session, carrier))


@router.get("/v1/carriers")
async def list_carriers(actor: NumbersKey, vault: TheVault, session: Session) -> schemas.CarrierList:
    """Every account of the org, oldest first."""
    listed = await accounts.describe_carriers(session, vault, actor.org)
    return schemas.CarrierList(carriers=[schemas.CarrierRow.of(carrier) for carrier in listed])


# What Add a number offers beside the org's own accounts.
@router.get("/v1/carriers/catalog")
async def list_carrier_catalog(
    actor: NumbersKey, vault: TheVault, names: TheSipNames, session: Session
) -> schemas.CarrierCatalog:
    """The carriers this box admits, automatic or guided, whether it sells numbers, and where a carrier sends a call."""
    return schemas.CarrierCatalog.of(await numbers.get_offer(session, vault, names, actor.env))


# Bringing an account the org already holds replaces its secret; its party is asked first.
@router.put("/v1/carrier")
async def put_carrier(
    body: schemas.Account, actor: NumbersKey, vault: TheVault, http: TheHttp, servers: TheServers, session: Session
) -> schemas.CarrierRow:
    """Keep an account of the org: a Twilio account, a SIP peer, a WhatsApp number at Meta."""
    brought = accounts.read_carrier(actor.org, body.model_dump())
    return schemas.CarrierRow.of(await rebuild.bring_carrier(session, vault, http, servers, brought))


@router.delete("/v1/carrier", status_code=204)
async def delete_carrier(actor: NumbersKey, vault: TheVault, session: Session, account: AccountAsked = None) -> None:
    """Forget an account; its numbers stay routed until each is let go."""
    await accounts.delete_carrier(session, vault, actor.org, account)


# ── calling out ──


@router.get("/v1/carrier/outbound")
async def get_outbound_status(
    actor: NumbersKey, vault: TheVault, session: Session, account: AccountAsked = None
) -> schemas.OutboundStatus:
    """Whether the org can place a call, one sentence per thing missing, and its guards."""
    return schemas.OutboundStatus.of(await outbound.get_readiness(session, vault, actor.scope, account))


@router.post("/v1/carrier/outbound", response_model_exclude_none=True)
async def provision_outbound(
    actor: NumbersKey,
    vault: TheVault,
    http: TheHttp,
    names: TheSipNames,
    session: Session,
    *,
    account: AccountAsked = None,
    dry_run: DryRun = False,
) -> schemas.ProvisionOutboundResponse:
    """Make an account dialable: Twilio's termination and a credential; a peer needs nothing."""
    provision = outbound.plan_outbound if dry_run else outbound.provision_outbound
    return schemas.ProvisionOutboundResponse.of(await provision(session, vault, http, names, actor.scope, account))
