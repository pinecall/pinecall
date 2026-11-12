"""The last lines of an app's process: asked for, kept as the runner sends them, followed."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import NotFound
from runtime.hosting.repository import HostedAppRepository
from runtime.hosting.service.apps import NOT_HOSTED, App
from runtime.kit.commit import run_after_commit
from runtime.signal import Signal

# Said on this channel (to every gateway) each time the runner's lines for the app are kept.
LOGS_CHANNEL = "app-logs:{org}:{env}:{name}"
# What a person reads of a process's output: its last lines, and no more than this.
LONGEST_LOGS = 64 * 1024


@dataclass(frozen=True, slots=True)
class Logs:
    """The last lines of an app's process as the runner read them; empty before the first read."""

    name: str
    host: str | None
    lines: str
    at: datetime | None


# The runner sends them on its next beat: a first ask answers what it sent last, or nothing.
async def ask_for_logs(session: AsyncSession, app: App) -> Logs:
    """What the runner last sent of the app's output; the runner is told to send it again."""
    found = await HostedAppRepository(session).ask_for_logs(app.org, app.env, app.name)
    if found is None:
        raise NotFound(NOT_HOSTED.format(name=app.name, env=app.env.value))
    return Logs(name=app.name, host=found.logs_host, lines=found.logs, at=found.logs_at)


# Said once they are stored: whoever follows the app reads them from the row.
async def keep_logs(session: AsyncSession, signal: Signal, app: App, *, host: str, lines: str) -> None:
    """Keep what the runner read of the app's output, its last part when it is long, and say so."""
    await HostedAppRepository(session).keep_logs(app.org, app.env, app.name, host=host, lines=lines[-LONGEST_LOGS:])
    run_after_commit(session, lambda: signal.publish(_channel_of(app), b""))


# Each time the runner's lines for the app are kept, on any gateway, they are read; asked again each
# time, so the runner keeps sending for as long as the app is followed. Listened to before the first
# is handed over, so nothing kept in between is missed.
async def follow_logs(
    sessions: async_sessionmaker[AsyncSession], signal: Signal, app: App, first: Logs
) -> AsyncIterator[Logs]:
    """The app's lines as they stand, then as each beat of its runner brings them."""
    listening = await signal.subscribe(_channel_of(app))
    try:
        yield first
        async for _ in listening:
            async with sessions.begin() as session:
                logs = await ask_for_logs(session, app)
            yield logs
    finally:
        listening.close()


def _channel_of(app: App) -> str:
    return LOGS_CHANNEL.format(org=app.org, env=app.env.value, name=app.name)
