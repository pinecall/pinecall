"""Billing's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.billing.service.admission import give_first_quotas
from runtime.billing.service.limits import admit_memory, admit_number, admit_push, admit_seat
from runtime.billing.service.quotas import Quotas, get_quotas, hold_stock

__all__ = [
    "Quotas",
    "admit_memory",
    "admit_number",
    "admit_push",
    "admit_seat",
    "get_quotas",
    "give_first_quotas",
    "hold_stock",
]
