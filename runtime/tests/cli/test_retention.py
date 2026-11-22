"""`retention run` as its CronJob runs it: on the database and the recordings' place, with no SFU and no Redis."""

import inspect
import io

import pytest
import typer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.service.days import DaysKept
from runtime.cli import retention
from runtime.cli.command import OK, Context
from runtime.cli.output import Printer
from runtime.config import load_settings
from runtime.retention.service import nightly
from runtime.retention.service.erasure import Erasing
from tests.conftest import needs_the_database

# What the chart's `retentionEnv` does not hand the nightly's pod.
NOT_HANDED = ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "PINECALL_REDIS_URL")


@needs_the_database
async def test_the_nights_run_opens_neither_the_sfu_nor_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handed no LiveKit pair and no Redis, the night still runs: it opened the process's whole state, and refused."""
    for name in NOT_HANDED:
        monkeypatch.delenv(name, raising=False)
    ran: list[Erasing] = []

    async def a_quiet_night(
        sessions: async_sessionmaker[AsyncSession], erasing: Erasing, now: float
    ) -> nightly.Nightly:
        ran.append(erasing)
        days = DaysKept(made=["2026-11-19"], dropped=[], refused=[])
        return nightly.Nightly(erased=[], records=0, dials=0, seen=0, alerts=0, days=days)

    monkeypatch.setattr(nightly, "run_nightly", a_quiet_night)
    said = io.StringIO()
    context = Context(load_settings(), Printer(as_json=False, out=said))
    ctx = typer.Context(typer.main.get_command(retention.app), obj=context)
    async with context.stack:
        assert await inspect.unwrap(retention.retention_run)(ctx) == OK
    assert len(ran) == 1
    assert "0 calls erased past their org's days" in said.getvalue()
    assert "days of the log: 1 made ahead, 0 dropped once empty" in said.getvalue()


def test_the_night_waits_for_its_hour_of_utc() -> None:
    """A server's night runs at 04:00 UTC: later today, tomorrow once the hour is past, a whole day at the minute."""
    midnight = 1795392000.0  # 2026-11-23T00:00:00Z
    assert retention.seconds_until("04:00", midnight) == 4 * 3600
    assert retention.seconds_until("04:00", midnight + 5 * 3600) == 23 * 3600
    assert retention.seconds_until("04:00", midnight + 4 * 3600) == 24 * 3600
    assert retention.seconds_until("23:30", midnight + 23 * 3600) == 30 * 60
