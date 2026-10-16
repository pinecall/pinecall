"""Who a key is: what this gateway is before anybody holds a key, and whose a key is."""

from fastapi import APIRouter, Request

from pinecall_runtime import __version__
from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    AnyKey,
    BrandDep,
    OutboxDep,
)
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.postgres import Session

router = APIRouter()


@router.get("/.well-known/pinecall")
async def gateway_info(request: Request, outbox_: OutboxDep, brand: BrandDep) -> schemas.GatewayInfo:
    """What this gateway is and how it signs people in, before anybody holds a key."""
    settings = handles_of(request).settings
    return schemas.GatewayInfo(
        version=__version__,
        signup=settings.signup,
        min_password=settings.min_password,
        mail=await outbox_.mailbox_for(None) is not None,
        brand=schemas.BrandRow(name=brand.name, logo_url=brand.logo_url, accent=brand.accent),
        google=False,
    )


@router.get("/v1/whoami")
async def whoami(actor: AnyKey, session: Session) -> schemas.Whoami:
    """Whose key this is, the env this request acts in, and what the key opens."""
    org = await orgs.find_org(session, actor.org)
    return schemas.Whoami.for_actor(actor, None if org is None else org.slug)
