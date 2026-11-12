"""The time an app served: counted while it serves, and read by the month."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.hosting.models import HostedUsage
from runtime.hosting.repository import HostedAppRepository, UsageRepository
from runtime.hosting.service import apps, hostnames
from runtime.hosting.service.apps import Processes, Standing

# A gap between two counts longer than this is a gateway that was away: it counts this much.
LONGEST_GAP_S = 30.0
NOT_A_MONTH = "{month!r} is not a month: YYYY-MM, like 2026-09"


@dataclass(frozen=True, slots=True)
class Usage:
    """The time apps served per UTC day in [since, until)."""

    since: date
    until: date
    rows: Sequence[HostedUsage]


# What the org is billed for. An app with a process serves while one of the org's processes says it
# runs on a host of its own, whichever release; one with none serves wherever a gateway holds it, for
# as long as it is not stopped and has a release.
async def count_serving(session: AsyncSession, processes: Processes, env: Env, now: datetime) -> None:
    """Count the time the env's serving apps served since the last count."""
    standing = await apps.list_standing(session, env)
    hosts = {org: apps.hosts_of(processes, org, env) for org in {app.org for app in standing}}
    serving = [(app.org, app.name) for app in standing if _serves(app, hosts[app.org])]
    await HostedAppRepository(session).count_serving(env, serving, now, longest_s=LONGEST_GAP_S)


async def usage_of_month(
    session: AsyncSession, month: str | None, *, org: str | None = None, env: Env | None = None
) -> Usage:
    """The time apps served each UTC day of the month named, this one by default: one org's or every org's."""
    since, until = read_month(month)
    return Usage(since, until, await UsageRepository(session).list_between(since, until, org=org, env=env))


def read_month(month: str | None) -> tuple[date, date]:
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


def _serves(app: Standing, hosts: frozenset[str]) -> bool:
    if app.stopped or app.release is None:
        return False
    return not app.kind.has_process or any(hostnames.is_host_of(app.name, host) for host in hosts)
