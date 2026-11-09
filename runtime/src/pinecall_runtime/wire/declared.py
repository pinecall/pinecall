"""What a class declares beside its stages: the quiet it bears, a machine that answers, the numbers it watches."""

from typing import Self

from pydantic import Field, model_validator

from pinecall_runtime.enums import MonitorMetric
from pinecall_runtime.wire.base import WireModel

# What an idle line waits and how many are said, when the agent does not say.
IDLE_AFTER_S = 7.5
IDLE_TIMES = 3
# The metrics that are a share of the calls, so their line sits between 0 and 1.
RATES = frozenset({MonitorMetric.held_rate, MonitorMetric.escalated_rate, MonitorMetric.tool_failure_rate})
# The windows a monitor reads its number over, in days.
WINDOWS = frozenset({1, 7, 30})
A_SHARE = "{metric} is a share between 0 and 1, not {said}"


class IdleConfig(WireModel):
    """What the agent says when the caller has gone quiet."""

    says: list[str]
    after_s: float = IDLE_AFTER_S
    times: int = IDLE_TIMES


class VoicemailConfig(WireModel):
    """Lets the model tell a machine from a person on a call it placed, and what it leaves there."""

    message: str | None = None


class MonitorDeclared(WireModel):
    """One number of the agent's calls the class watches: it fires, once a day, when it crosses the line."""

    name: str = Field(min_length=1)
    metric: MonitorMetric
    above: bool
    threshold: float
    window_days: int = 7

    @model_validator(mode="after")
    def _a_share(self) -> Self:
        if self.window_days not in WINDOWS:
            raise ValueError(f"window_days is one of {sorted(WINDOWS)}, not {self.window_days}")
        if self.metric in RATES and not 0 <= self.threshold <= 1:
            raise ValueError(A_SHARE.format(metric=self.metric, said=self.threshold))
        return self
