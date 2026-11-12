"""Mail's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.mail.service.emails import (
    Email,
    LinkDetails,
    Wording,
    code_block,
    frame,
    heading,
    paragraph,
    small,
    write_link_email,
    write_notice,
)
from runtime.mail.service.outbox import Outbox

__all__ = [
    "Email",
    "LinkDetails",
    "Outbox",
    "Wording",
    "code_block",
    "frame",
    "heading",
    "paragraph",
    "small",
    "write_link_email",
    "write_notice",
]
