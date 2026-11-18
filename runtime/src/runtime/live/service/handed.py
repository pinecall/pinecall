"""A message or a receipt as one gateway hands it to the one holding its contact's thread, and back."""

from runtime.whatsapp import service as whatsapp
from runtime.wire.signal import HandedMessage


def hand(inbound: whatsapp.Inbound) -> HandedMessage:
    """The contact's message, as the gateway holding the thread is told it."""
    return HandedMessage(
        number=inbound.number,
        phone_number_id=inbound.phone_number_id,
        wa_id=inbound.wa_id,
        name=inbound.name,
        message_id=inbound.message_id,
        kind=inbound.kind,
        text=inbound.text,
        media_id=inbound.media_id,
        channel=inbound.channel,
        carrier_replied=inbound.carrier_replied,
        subject=inbound.subject,
        references=list(inbound.references),
        thread=inbound.thread,
    )


def hand_receipt(receipt: whatsapp.Receipt) -> HandedMessage:
    """Where one of the agent's replies stands, as the gateway holding the thread is told it."""
    return HandedMessage(
        number=receipt.number,
        phone_number_id=receipt.phone_number_id,
        wa_id=receipt.wa_id,
        name=None,
        message_id=receipt.message_id,
        kind="status",
        text=None,
        status=receipt.status,
        error=receipt.error,
        channel=receipt.channel,
    )


# Claimed and read by the gateway it landed on: here it is only heard.
def message_of(handed: HandedMessage) -> whatsapp.Inbound:
    """The contact's message a gateway handed on."""
    return whatsapp.Inbound(
        number=handed.number,
        phone_number_id=handed.phone_number_id,
        wa_id=handed.wa_id,
        name=handed.name,
        message_id=handed.message_id,
        kind=handed.kind,
        text=handed.text,
        media_id=handed.media_id,
        channel=handed.channel,
        carrier_replied=handed.carrier_replied,
        subject=handed.subject,
        references=tuple(handed.references),
        thread=handed.thread,
    )


# Vouched for by the gateway that took it off the webhook: handed on, it names no signer.
def receipt_of(handed: HandedMessage, status: str) -> whatsapp.Receipt:
    """The receipt a gateway handed on."""
    return whatsapp.Receipt(
        number=handed.number,
        phone_number_id=handed.phone_number_id,
        wa_id=handed.wa_id,
        message_id=handed.message_id,
        status=status,
        error=handed.error,
        channel=handed.channel,
    )
