"""A monitor: the line it fires across, and what a request may ask it to watch."""

import pytest
from pydantic import ValidationError

from pinecall_runtime.alerts.models import Monitor
from pinecall_runtime.alerts.schemas import MonitorRequest
from pinecall_runtime.alerts.service import monitors
from pinecall_runtime.alerts.service.monitors import crossed
from pinecall_runtime.enums import Env, MonitorMetric
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.wire.declared import MonitorDeclared
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


def test_a_declared_monitor_is_held_to_what_a_request_is() -> None:
    """A rate's line sits between 0 and 1, whoever draws it."""
    assert MonitorDeclared(name="held", metric=MonitorMetric.held_rate, above=False, threshold=0.9).window_days == 7
    with pytest.raises(ValidationError):
        MonitorDeclared(name="held", metric=MonitorMetric.held_rate, above=False, threshold=90)


@needs_the_services
async def test_a_classs_monitors_are_kept_by_name_and_no_door_takes_one_out(gateway: Gateway, tenant: Tenant) -> None:
    """Made, changed and dropped as the class says them; one somebody set by hand is left alone."""
    scope = Scope(org=tenant.org, env=Env.sandbox, holder=THE_ORGS_OWN)
    slow = MonitorDeclared(name="slow", metric=MonitorMetric.e2e_median_s, above=True, threshold=2.0)
    busy = MonitorDeclared(name="busy", metric=MonitorMetric.calls, above=True, threshold=100, window_days=1)
    async with gateway.app.state.handles.sessions.begin() as session:
        by_hand = MonitorRequest(name="spend", metric=MonitorMetric.spend_usd, above=True, threshold=5, agent="front")
        await monitors.create_monitor(session, scope, by_hand, by="m_ana")
        await monitors.keep_declared(session, scope, "front", [slow, busy])
        await monitors.keep_declared(session, scope, "front", [slow.model_copy(update={"threshold": 3.0})])
        rows = {row.name: row for row in await monitors.list_monitors(session, scope)}
        assert sorted(rows) == ["slow", "spend"]
        assert (rows["slow"].threshold, rows["slow"].created_by) == (3.0, monitors.THE_CLASS)
        with pytest.raises(Conflict, match="declared by the class of front"):
            await monitors.delete_monitor(session, scope, rows["slow"].id)
        await monitors.keep_declared(session, scope, "front", None)
        assert len(await monitors.list_monitors(session, scope)) == 2
