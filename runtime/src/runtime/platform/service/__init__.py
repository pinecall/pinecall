"""The platform's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.platform.service.brand import Brand
from runtime.platform.service.settings import (
    Setting,
    delete_setting,
    find_sealed_setting,
    find_setting,
    put_setting,
)

__all__ = ["Brand", "Setting", "delete_setting", "find_sealed_setting", "find_setting", "put_setting"]
