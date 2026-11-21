"""Sign-in's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.signin.service.sso import delete_proofs

__all__ = [
    "delete_proofs",
]
