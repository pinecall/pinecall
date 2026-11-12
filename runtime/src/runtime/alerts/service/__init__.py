"""The alerts' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.alerts.service.alerts import Alerting, forget_alerts
from runtime.alerts.service.monitors import check_monitors
from runtime.alerts.service.spend import UnusualSpend, watch_spend
from runtime.alerts.service.vendors import failure_of, vendor_of
from runtime.alerts.service.webhooks import forget_webhook

__all__ = [
    "Alerting",
    "UnusualSpend",
    "check_monitors",
    "failure_of",
    "forget_alerts",
    "forget_webhook",
    "vendor_of",
    "watch_spend",
]
