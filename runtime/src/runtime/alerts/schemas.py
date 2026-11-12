"""The bodies of the monitors, webhook and alerts endpoints."""

from datetime import date, datetime
from typing import Any

from pydantic import ConfigDict, field_serializer

from runtime.enums import Env, MonitorMetric
from runtime.kit.schemas import Row, Schema
from runtime.wire.declaration import MonitorDeclared


# What a class declares of a monitor is what a request asks of one, held to the same lines (a known
# metric, a window of a day, a week or a month, a rate between 0 and 1), plus whose agent it watches.
class MonitorRequest(MonitorDeclared):
    """POST /v1/monitors: what to watch, over which window, the line, and whose agent."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    agent: str | None = None


class MonitorRow(Row):
    """One monitor: its rule, who set it, and the last day it fired with the value that crossed."""

    id: str
    name: str
    metric: MonitorMetric
    above: bool
    threshold: float
    window_days: int
    agent: str | None
    created_by: str
    fired_on: date | None
    fired_value: float | None

    @field_serializer("fired_on")
    def _as_a_day(self, fired_on: date | None) -> str | None:
        return None if fired_on is None else fired_on.isoformat()


class MonitorList(Row):
    """GET /v1/monitors: the env's monitors, oldest first."""

    monitors: list[MonitorRow]


class WebhookRequest(Schema):
    """PUT /v1/webhook: the URL, and the secret every post is signed with (never read back)."""

    url: str
    secret: str | None = None


class WebhookResponse(Row):
    """GET /v1/webhook: the URL and whether posts are signed; null when alerts go nowhere."""

    url: str
    signed: bool


class WebhookTestResponse(Row):
    """POST /v1/webhook/test, the answer: whether the URL took it, and what went wrong if not."""

    sent: bool
    error: str | None


class AlertRow(Row):
    """One alert kept: whose, what kind, about what, when, and whether it was mailed."""

    id: str
    org: str
    env: Env
    agent: str | None
    kind: str
    data: dict[str, Any]
    mailed: bool
    at: datetime


class AlertList(Row):
    """The alerts asked for, newest first."""

    alerts: list[AlertRow]
