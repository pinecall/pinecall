"""Sign-in's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.signin.service.sso import delete_proofs
from runtime.signin.service.turnstile import Turnstile

__all__ = [
    "Turnstile",
    "delete_proofs",
]
