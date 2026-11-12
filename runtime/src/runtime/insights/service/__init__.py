"""The insights' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.insights.service.drift import fold_call
from runtime.insights.service.tool_days import forget_calls
from runtime.insights.service.windows import series_window

__all__ = [
    "fold_call",
    "forget_calls",
    "series_window",
]
