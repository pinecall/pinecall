"""A monitor: the line it fires across, and what a request may ask it to watch."""

import pytest
from pydantic import ValidationError

from pinecall_runtime.alerts.models import Monitor
from pinecall_runtime.alerts.schemas import MonitorRequest
from pinecall_runtime.alerts.service.monitors import crossed
from pinecall_runtime.enums import Env, MonitorMetric
from tests.conftest import Gateway, Tenant, holding, needs_the_services


def a_monitor(metric: MonitorMetric, *, above: bool, threshold: float) -> Monitor:
    """A monitor as its row holds it."""
    return Monitor(
        id="mon_1",
        org="org_1",
        env=Env.production,
        name="m",
        metric=metric,
        above=above,
        threshold=threshold,
        window_days=7,
        created_by="m_ana",
    )


def test_a_ceiling_fires_above_it_and_a_floor_below_it() -> None:
    """A ceiling fires only past it; a floor only under it; the line itself is never crossed."""
    slow = a_monitor(MonitorMetric.e2e_median_s, above=True, threshold=2.0)
    assert crossed(slow, 2.5)
    assert not crossed(slow, 2.0)
    held = a_monitor(MonitorMetric.held_rate, above=False, threshold=0.9)
    assert crossed(held, 0.85)
    assert not crossed(held, 0.9)


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


@needs_the_services
async def test_a_monitor_watches_an_agent_the_org_has(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """An agent no app of the org ever held is a slug typed wrong: 404, never a monitor that never fires."""
    body = {"name": "slow", "metric": "e2e_median_s", "above": True, "threshold": 2.0, "agent": "nobody-held"}
    refused = await gateway.http.post("/v1/monitors", json=body, headers=tenant.person)
    assert refused.status_code == 404, refused.text
    async with holding(gateway, tenant, agent):
        kept = await gateway.http.post("/v1/monitors", json={**body, "agent": agent}, headers=tenant.person)
    assert kept.status_code == 201, kept.text
