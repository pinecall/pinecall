"""WhatsApp's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.whatsapp.service.graph import (
    Media,
    Template,
    mark_read,
    number_of,
    read_media,
    send_template,
    send_text,
)
from runtime.whatsapp.service.messenger import (
    app_of,
    mark_seen,
    name_of,
    open_conversations,
    page_of,
    read_attachment,
    scopes_of,
    subscribe_app,
    subscribe_page,
)
from runtime.whatsapp.service.messenger import send_text as send_on_messenger
from runtime.whatsapp.service.seen import forget_seen_before, read_once
from runtime.whatsapp.service.webhook import (
    Inbound,
    OwnApp,
    Receipt,
    Subscription,
    Threads,
    box_meta_app,
    subscription_of,
)

__all__ = [
    "Inbound",
    "Media",
    "OwnApp",
    "Receipt",
    "Subscription",
    "Template",
    "Threads",
    "app_of",
    "box_meta_app",
    "forget_seen_before",
    "mark_read",
    "mark_seen",
    "name_of",
    "number_of",
    "open_conversations",
    "page_of",
    "read_attachment",
    "read_media",
    "read_once",
    "scopes_of",
    "send_on_messenger",
    "send_template",
    "send_text",
    "subscribe_app",
    "subscribe_page",
    "subscription_of",
]
