"""A monitor: the line it fires across, and the class's own, kept by name as the class has them."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.alerts.models import Monitor
from runtime.alerts.schemas import MonitorRequest
from runtime.alerts.service import monitors
from runtime.alerts.service.monitors import crosses
from runtime.enums import Env, MonitorMetric
from runtime.exceptions import Conflict, NotFound
from runtime.wire.declaration import MonitorDeclared
from tests.conftest import Tenant, needs_the_database


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


class Held:
    """The agents an org's apps hold, as a monitor asks whose an agent is."""

    def __init__(self, org: str, *agents: str) -> None:
        self.org, self.agents = org, agents

    async def owner(self, agent: str) -> str | None:
        """The org that holds the agent; None when nobody does."""
        return self.org if agent in self.agents else None


def test_a_ceiling_fires_above_it_and_a_floor_below_it() -> None:
    """A ceiling fires only past it; a floor only under it; the line itself is never crossed."""
    slow = a_monitor(MonitorMetric.e2e_median_s, above=True, threshold=2.0)
    assert crosses(slow, 2.5)
    assert not crosses(slow, 2.0)
    held = a_monitor(MonitorMetric.held_rate, above=False, threshold=0.9)
    assert crosses(held, 0.85)
    assert not crosses(held, 0.9)


@needs_the_database
async def test_a_monitor_of_an_agent_nobody_of_the_org_holds_is_refused(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A slug typed wrong would never fire, and another org's agent is not this org's to watch."""
    scope = Scope(org=tenant.org, env=Env.sandbox, holder=THE_ORGS_OWN)
    slow = MonitorDeclared(name="slow", metric=MonitorMetric.e2e_median_s, above=True, threshold=2.0)
    async with sessions.begin() as session:
        with pytest.raises(NotFound):
            await monitors.create_monitor(session, Held(tenant.org, "front"), scope, slow, "nobody-held", by="m_ana")
        with pytest.raises(NotFound):
            await monitors.create_monitor(session, Held("org_other", "front"), scope, slow, "front", by="m_ana")
        assert await monitors.list_monitors(session, scope) == []


@needs_the_database
async def test_a_classs_monitors_are_kept_by_name_and_nobody_deletes_one_by_hand(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Made, changed and dropped as the class says them; one somebody set by hand is left alone."""
    scope = Scope(org=tenant.org, env=Env.sandbox, holder=THE_ORGS_OWN)
    slow = MonitorDeclared(name="slow", metric=MonitorMetric.e2e_median_s, above=True, threshold=2.0)
    busy = MonitorDeclared(name="busy", metric=MonitorMetric.calls, above=True, threshold=100, window_days=1)
    async with sessions.begin() as session:
        by_hand = MonitorRequest(name="spend", metric=MonitorMetric.spend_usd, above=True, threshold=5, agent="front")
        await monitors.create_monitor(session, Held(tenant.org, "front"), scope, by_hand, by_hand.agent, by="m_ana")
        await monitors.sync_monitors(session, scope, "front", [slow, busy])
        await monitors.sync_monitors(session, scope, "front", [slow.model_copy(update={"threshold": 3.0})])
        rows = {row.name: row for row in await monitors.list_monitors(session, scope)}
        assert sorted(rows) == ["slow", "spend"]
        assert (rows["slow"].threshold, rows["slow"].created_by) == (3.0, monitors.THE_CLASS)
        with pytest.raises(Conflict, match="declared by the class of front"):
            await monitors.delete_monitor(session, scope, rows["slow"].id)
        left_alone = await monitors.sync_monitors(session, scope, "front", None)
        assert sorted(row.name for row in left_alone) == ["slow", "spend"]
        assert len(await monitors.list_monitors(session, scope)) == 2
        await monitors.delete_monitor(session, scope, rows["spend"].id)
        assert [row.name for row in await monitors.list_monitors(session, scope)] == ["slow"]
