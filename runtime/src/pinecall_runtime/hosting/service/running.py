"""A hosted app while it runs: stopped and started, the logs asked for, the time it served."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.hosting.models import HostedUsage
from pinecall_runtime.hosting.repository import HostedAppRepository, ServedRepository
from pinecall_runtime.hosting.schemas import ServedPage, ServedRow
from pinecall_runtime.hosting.service.apps import NOT_HOSTED, App

# Said on this channel (to every gateway) each time the runner's lines for the app are kept.
LOGS_CHANNEL = "app-logs:{org}:{env}:{name}"
NOT_A_MONTH = "{month!r} is not a month: YYYY-MM, like 2026-09"


@dataclass(frozen=True, slots=True)
class Logs:
    """The last lines of an app's process as the runner read them; empty before the first read."""

    host: str | None
    lines: str
    at: datetime | None


async def stop_app(session: AsyncSession, app: App, *, by: str) -> None:
    """Stop running the app: the runner drains it, and its releases and token stay."""
    if not await HostedAppRepository(session).stop(app.org, app.env, app.name, by=by):
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))


async def start_app(session: AsyncSession, app: App) -> None:
    """Run a stopped app again, its newest release."""
    if not await HostedAppRepository(session).start(app.org, app.env, app.name):
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))


async def ask_for_logs(session: AsyncSession, app: App) -> Logs:
    """What the runner last sent of the app's output; the runner is told to send it again."""
    found = await HostedAppRepository(session).ask_for_logs(app.org, app.env, app.name)
    if found is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    return Logs(host=found.logs_host, lines=found.logs, at=found.logs_at)


async def keep_logs(session: AsyncSession, app: App, *, host: str, lines: str) -> None:
    """Keep what the runner read of the app's output, its last part when it is long."""
    await HostedAppRepository(session).keep_logs(app.org, app.env, app.name, host=host, lines=lines)


async def count_serving(session: AsyncSession, env: Env, serving: Sequence[tuple[str, str]], now: datetime) -> None:
    """Count the time the env's serving apps, each an (org, name), served since the last count."""
    await HostedAppRepository(session).count_serving(env, serving, now)


async def served(
    session: AsyncSession, since: date, until: date, *, org: str | None = None, env: Env | None = None
) -> Sequence[HostedUsage]:
    """The time apps served per UTC day in [since, until), one org's or every org's."""
    return await ServedRepository(session).between(since, until, org=org, env=env)


def month_of(month: str | None) -> tuple[date, date]:
    """The first day of the month named (YYYY-MM), or of this UTC one, and of the next."""
    if month is None:
        first = datetime.now(UTC).date().replace(day=1)
    else:
        try:
            first = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC).date()
        except ValueError:
            raise ValidationError(NOT_A_MONTH.format(month=month)) from None
    after = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, after


def served_page(since: date, until: date, rows: Sequence[HostedUsage]) -> ServedPage:
    """The time apps served, as the endpoints answer it."""
    return ServedPage(
        since=since.isoformat(),
        until=until.isoformat(),
        rows=[
            ServedRow(org=row.org, env=row.env, name=row.name, day=row.day.isoformat(), seconds=round(row.seconds, 1))
            for row in rows
        ],
    )
