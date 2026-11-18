"""Mail's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.mail.service.emails import (
    Email,
    LinkDetails,
    Wording,
    button,
    code_block,
    fallback,
    frame,
    heading,
    paragraph,
    small,
    write_link_email,
    write_notice,
)
from runtime.mail.service.mailboxes import Mailbox
from runtime.mail.service.outbox import Outbox
from runtime.mail.service.smtp import check_login, check_public, deliver

__all__ = [
    "Email",
    "LinkDetails",
    "Mailbox",
    "Outbox",
    "Wording",
    "button",
    "check_login",
    "check_public",
    "code_block",
    "deliver",
    "fallback",
    "frame",
    "heading",
    "paragraph",
    "small",
    "write_link_email",
    "write_notice",
]
