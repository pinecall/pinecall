"""What a request may ask a monitor to watch: a known metric, a known window, a rate that is a share."""

import pytest
from pydantic import ValidationError

from runtime.alerts.schemas import MonitorRequest
from runtime.enums import MonitorMetric
from runtime.wire.declaration import MonitorDeclared


def test_a_request_watches_a_known_metric_over_a_known_window() -> None:
    """A metric nobody measures, or a window other than a day, a week or a month, is refused."""
    with pytest.raises(ValidationError):
        MonitorRequest.model_validate({"name": "x", "metric": "p50", "above": True, "threshold": 1.0})
    with pytest.raises(ValidationError):
        MonitorRequest.model_validate(
            {"name": "x", "metric": "calls", "above": True, "threshold": 1.0, "window_days": 3}
        )


def test_a_rate_is_a_share_between_nothing_and_everything() -> None:
    """A rate's line is a share: 1.5 of the calls held is refused."""
    with pytest.raises(ValidationError):
        MonitorRequest.model_validate({"name": "x", "metric": "held_rate", "above": False, "threshold": 1.5})
    assert MonitorRequest.model_validate({"name": "x", "metric": "held_rate", "above": False, "threshold": 0.9})


def test_a_declared_monitor_is_held_to_what_a_request_is() -> None:
    """A rate's line sits between 0 and 1, whoever draws it."""
    assert MonitorDeclared(name="held", metric=MonitorMetric.held_rate, above=False, threshold=0.9).window_days == 7
    with pytest.raises(ValidationError):
        MonitorDeclared(name="held", metric=MonitorMetric.held_rate, above=False, threshold=90)
