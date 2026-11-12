"""The providers' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.providers.service.keyring import parse_lending

__all__ = ["parse_lending"]
