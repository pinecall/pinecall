"""The body WhatsApp's webhook answers Meta with."""

from runtime.kit.schemas import Row


class Received(Row):
    """POST /v1/whatsapp/webhook: how many messages the body carried."""

    received: int
