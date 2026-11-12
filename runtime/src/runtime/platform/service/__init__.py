"""The platform's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.platform.service.attempts import AttemptThrottle
from runtime.platform.service.brand import Brand, get_brand
from runtime.platform.service.settings import (
    Setting,
    delete_setting,
    find_sealed_setting,
    find_setting,
    put_setting,
    put_setting_if_absent,
)

__all__ = [
    "AttemptThrottle",
    "Brand",
    "Setting",
    "delete_setting",
    "find_sealed_setting",
    "find_setting",
    "get_brand",
    "put_setting",
    "put_setting_if_absent",
]
