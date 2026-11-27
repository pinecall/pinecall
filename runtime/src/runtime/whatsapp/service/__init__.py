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
    mark_seen,
    name_of,
    open_conversations,
    page_of,
    read_attachment,
    subscribe_page,
)
from runtime.whatsapp.service.messenger import send_text as send_on_messenger
from runtime.whatsapp.service.seen import forget_seen_before, read_once
from runtime.whatsapp.service.webhook import Inbound, OwnApp, Receipt, Threads, box_meta_app

__all__ = [
    "Inbound",
    "Media",
    "OwnApp",
    "Receipt",
    "Template",
    "Threads",
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
    "send_on_messenger",
    "send_template",
    "send_text",
    "subscribe_page",
]
