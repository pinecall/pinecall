"""A runner's beat as the gateway hears it: its reports and its logs kept, and what it is to run answered."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.alerts import service as alerts
from runtime.calls.log import Feeds
from runtime.enums import Env
from runtime.hosting.repository import HostedAppRepository
from runtime.hosting.service import apps, hostnames, logs
from runtime.hosting.service.apps import App, Processes, Standing
from runtime.kit.commit import run_after_commit
from runtime.signal import Signal
from runtime.wire.feed import AppFailed, ReleaseChanged
from runtime.wire.runner import RunnerHeartbeatRequest, RunnerReport

logger = logging.getLogger(__name__)


# In this order: what the runner says is kept first, so what it is answered already counts it.
async def hear_beat(
    session: AsyncSession,
    alerting: alerts.Alerting,
    feeds: Feeds,
    signal: Signal,
    processes: Processes,
    env: Env,
    beat: RunnerHeartbeatRequest,
) -> list[Standing]:
    """Keep the runner's reports and logs, and answer every app of its env it is to have running."""
    for report in beat.reports:
        await _hear_report(session, alerting, feeds, env, beat.runner, report)
    for sent in beat.logs:
        await logs.keep_logs(session, signal, App(sent.org, env, sent.name), host=sent.host, lines=sent.lines)
    return await apps.list_wanted(session, processes, env)


# A report names its host, and a host names its release: one about a release since replaced is kept as
# what it is, and says nothing of the release wanted now. The first report of a host failing is the
# org's alert; the next beats repeat nothing. What changed is said once the beat is stored: the console
# reads the release when told.
async def _hear_report(
    session: AsyncSession, alerting: alerts.Alerting, feeds: Feeds, env: Env, runner: str, report: RunnerReport
) -> None:
    repository = HostedAppRepository(session)
    release = hostnames.release_of(report.host)
    scope = Scope(report.org, env)
    if report.state == "live":
        await repository.mark_live(report.org, env, report.name, release=release, host=report.host, runner=runner)
    elif await repository.mark_failed(report.org, env, report.name, host=report.host, why=report.why, runner=runner):
        failed = AppFailed(app=report.name, host=report.host, release=release, why=report.why)
        await alerting.raise_alert(session, scope, None, failed)
    if release is None:
        logger.warning("runner %s reported %s of %s, which is no release's host", runner, report.host, report.name)
        return
    news = ReleaseChanged(app=report.name, release=release)
    run_after_commit(session, lambda: feeds.announce(scope, "release.changed", news))
