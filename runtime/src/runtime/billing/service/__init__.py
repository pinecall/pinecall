"""Billing's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.billing.service.admission import give_first_quotas
from runtime.billing.service.limits import admit_seat

__all__ = ["admit_seat", "give_first_quotas"]
