"""What this gateway is, before anybody holds a key."""

from fastapi import APIRouter

from runtime.handles import TheSettings
from runtime.mail.auth import TheOutbox
from runtime.postgres import Session
from runtime.signin import schemas
from runtime.signin.service import gateway

router = APIRouter()


@router.get("/.well-known/pinecall")
async def gateway_info(settings: TheSettings, outbox: TheOutbox, session: Session) -> schemas.GatewayInfo:
    """What this gateway is and how it signs people in, before anybody holds a key."""
    described = await gateway.describe(
        session,
        outbox,
        signup=settings.signup,
        min_password=settings.min_password,
        turnstile=settings.turnstile_site_key,
    )
    return schemas.GatewayInfo.of(described)
