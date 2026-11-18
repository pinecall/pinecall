"""Meta's WhatsApp webhook: the handshake that subscribes it, its deliveries, and what an org types at Meta."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from runtime.handles import TheVault
from runtime.whatsapp import schemas
from runtime.whatsapp.auth import SignedMessages, TheBoxApp, TheSubscription, TheThreads
from runtime.whatsapp.service import webhook

router = APIRouter()


@router.get("/v1/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    box: TheBoxApp,
    vault: TheVault,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    word: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Meta subscribing: its challenge echoed back when it says the box's word, or one given to an org."""
    return webhook.handshake(box, vault, mode, word, challenge)


@router.post("/v1/whatsapp/webhook")
async def receive_webhook(messages: SignedMessages, threads: TheThreads) -> schemas.Received:
    """Every message of a signed body onto its contact's conversation."""
    return schemas.Received(received=await webhook.receive_all(threads, messages))


# An org with a Meta app of its own types these two in the app's WhatsApp ▸ Configuration.
@router.get("/v1/whatsapp/subscription")
async def get_subscription(subscription: TheSubscription) -> schemas.Subscription:
    """The callback URL and the verify token the org's own Meta app subscribes with."""
    return schemas.Subscription.of(subscription)
