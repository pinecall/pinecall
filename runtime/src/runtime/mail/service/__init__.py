"""Mail's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.mail.service.emails import Email, LinkDetails, Wording, write_link_email
from runtime.mail.service.outbox import Outbox

__all__ = ["Email", "LinkDetails", "Outbox", "Wording", "write_link_email"]
