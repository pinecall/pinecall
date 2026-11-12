"""The log's days: a partition of call_log per UTC day, made ahead and dropped once emptied."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from runtime.calls.models import CallLog
from runtime.kit.repository import Repository
from runtime.kit.time import A_DAY_S

# A day is call_log_<YYYYMMDD>; the table as it was before the days is one partition of its own.
BEFORE = "call_log_before_the_days"
DEFAULT = "call_log_default"
A_NAME = re.compile(r"^call_log_[a-z0-9_]+$")

PARTITIONS = text("""
SELECT child.relname AS name, pg_get_expr(child.relpartbound, child.oid) AS bound
FROM pg_inherits link JOIN pg_class child ON child.oid = link.inhrelid
WHERE link.inhparent = 'call_log'::regclass
""")

# The upper bound a partition was made with, as pg_get_expr prints it.
UPPER = re.compile(r"TO \('?(-?[0-9.e+]+)'?\)")

# A partition made or dropped waits a second at most for its lock, and tries again the next night.
BRIEF = text("SET LOCAL lock_timeout = '1s'")


@dataclass(frozen=True, slots=True)
class Partition:
    """A partition of the log: its name, and the time it holds rows up to (None: the default)."""

    name: str
    upto: float | None


def name_day(start: float) -> str:
    """The name of the day that starts at that time."""
    return f"call_log_{datetime.fromtimestamp(start, UTC):%Y%m%d}"


def start_of_day(now: float) -> float:
    """The UTC midnight the moment falls after."""
    return float(int(now) - int(now) % A_DAY_S)


# DDL on a partitioned table: the names are the runtime's own (`call_log_YYYYMMDD`), checked
# against A_NAME before they are quoted into a statement.
class DayRepository(Repository[CallLog]):
    """The partitions of call_log, as the nightly run makes and drops them."""

    model = CallLog

    async def list_partitions(self) -> list[Partition]:
        """Every partition of the log, the default's end unknown, in order of their end."""
        rows = (await self.session.execute(PARTITIONS)).all()
        found: list[Partition] = []
        for row in rows:
            upper = UPPER.search(str(row.bound))
            found.append(Partition(str(row.name), None if upper is None else float(upper.group(1))))
        return sorted(found, key=lambda part: (part.upto is None, part.upto or 0.0))

    async def has_in_default(self, start: float, end: float) -> bool:
        """Whether the default partition caught rows of that day."""
        statement = text(f"SELECT EXISTS (SELECT 1 FROM {DEFAULT} WHERE ts >= :start AND ts < :end)")
        return bool((await self.session.execute(statement, {"start": start, "end": end})).scalar_one())

    async def count_in_default(self) -> int:
        """How many rows the default partition holds: rows a missing day let in."""
        return int((await self.session.execute(text(f"SELECT count(*) FROM {DEFAULT}"))).scalar_one())

    async def create_day(self, name: str, start: float, end: float) -> None:
        """Create the day's partition, waiting a second at most for the lock."""
        await self.session.execute(BRIEF)
        await self.session.execute(
            text(f"CREATE TABLE {_check(name)} PARTITION OF call_log FOR VALUES FROM ({start!r}) TO ({end!r})")
        )

    async def has_rows(self, name: str) -> bool:
        """Whether the partition still holds a row."""
        return bool((await self.session.execute(text(f"SELECT EXISTS (SELECT 1 FROM {_check(name)})"))).scalar_one())

    async def drop_day(self, name: str) -> None:
        """Drop the partition, waiting a second at most for the lock."""
        await self.session.execute(BRIEF)
        await self.session.execute(text(f"DROP TABLE {_check(name)}"))


def _check(name: str) -> str:
    if not A_NAME.match(name):
        raise ValueError(f"{name!r} is not a partition of the log")
    return name
