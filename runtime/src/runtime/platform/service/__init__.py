"""The platform's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.platform.service.settings import Setting, find_setting, put_setting

__all__ = ["Setting", "find_setting", "put_setting"]
