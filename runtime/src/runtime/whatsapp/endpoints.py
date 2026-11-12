"""Meta's WhatsApp webhook: the handshake that subscribes it, and the messages it delivers."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from runtime.whatsapp import schemas, service
from runtime.whatsapp.auth import SignedMessages, TheMetaApp, TheThreads

router = APIRouter()


@router.get("/v1/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    app: TheMetaApp,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    word: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Meta subscribing: its challenge echoed back when it says this box's word."""
    return service.handshake(app, mode, word, challenge)


@router.post("/v1/whatsapp/webhook")
async def receive_webhook(messages: SignedMessages, threads: TheThreads) -> schemas.Received:
    """Every message of a signed body onto its contact's conversation."""
    return schemas.Received(received=await service.receive_all(threads, messages))
