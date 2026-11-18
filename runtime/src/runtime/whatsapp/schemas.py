"""The bodies WhatsApp's endpoints answer with: Meta's deliveries counted, and what an org types in its Meta app."""

from runtime.kit.schemas import Row


class Received(Row):
    """POST /v1/whatsapp/webhook: how many messages the body carried."""

    received: int


class Subscription(Row):
    """GET /v1/whatsapp/subscription: where the org's own Meta app delivers, the word it subscribes with, the field."""

    callback_url: str
    verify_token: str
    field: str
