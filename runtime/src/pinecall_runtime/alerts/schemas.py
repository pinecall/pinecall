"""The bodies of the monitors and webhook endpoints."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, field_serializer, model_validator

from pinecall_runtime.enums import MonitorMetric
from pinecall_runtime.kit.schemas import Row, Schema

# A monitor's number is read over one of these many days, today included.
type WindowDays = Literal[1, 7, 30]
A_RATE = frozenset({MonitorMetric.held_rate, MonitorMetric.escalated_rate, MonitorMetric.tool_failure_rate})
A_SHARE = "{metric} is a share between 0 and 1, not {said}"


class MonitorRequest(Schema):
    """POST /v1/monitors: what to watch, over which window, the line, and whose agent."""

    name: str = Field(min_length=1)
    metric: MonitorMetric
    above: bool
    threshold: float
    window_days: WindowDays = 7
    agent: str | None = None

    @model_validator(mode="after")
    def _a_share(self) -> Self:
        if self.metric in A_RATE and not 0 <= self.threshold <= 1:
            raise ValueError(A_SHARE.format(metric=self.metric, said=self.threshold))
        return self


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
