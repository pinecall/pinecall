"""The log's days: made a week ahead each night, dropped once a past day holds nothing."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.repository.days import (
    A_DAY_S,
    BEFORE,
    DayRepository,
    Partition,
    day_named,
    day_of,
)

# Made a week ahead each night: a box whose nightly run stops has a week before the default fills.
AHEAD = 7
# Doctor speaks up while there are fewer days ahead than this.
FEWEST_AHEAD = 2


@dataclass(frozen=True)
class Kept:
    """What a night did to the days: made, dropped, refused for rows the default holds of them."""

    made: list[str]
    dropped: list[str]
    refused: list[str]


async def keep_days(session: AsyncSession, now: float) -> Kept:
    """Make the days ahead that are missing and drop the past days nothing is left in."""
    repository = DayRepository(session)
    found = await repository.partitions()
    made, refused = await _make_ahead(session, repository, found, now)
    return Kept(made=made, dropped=await _drop_past(session, repository, found, now), refused=refused)


async def examine_days(session: AsyncSession, now: float) -> str | None:
    """What is wrong with the days: rows the default caught, or too few days made ahead."""
    repository = DayRepository(session)
    troubles: list[str] = []
    caught = await repository.rows_in_default()
    if caught:
        troubles.append(f"{caught} rows in the default partition: a day was missing when they were written")
    ahead = sum(1 for part in await repository.partitions() if part.upto is not None and part.upto > day_of(now))
    if ahead < FEWEST_AHEAD:
        troubles.append(f"{ahead} days of the log made ahead: `retention run` makes {AHEAD}")
    return "; ".join(troubles) or None


# A day before the old table's bound is its; a day the default holds rows of cannot be made,
# since making it would move them, and is named instead.
async def _make_ahead(
    session: AsyncSession, repository: DayRepository, found: list[Partition], now: float
) -> tuple[list[str], list[str]]:
    names = {part.name for part in found}
    before = next((part.upto for part in found if part.name == BEFORE), None) or 0.0
    made: list[str] = []
    refused: list[str] = []
    for start in (day_of(now) + n * A_DAY_S for n in range(AHEAD)):
        name = day_named(start)
        if name in names or start < before:
            continue
        async with session.begin_nested():
            if await repository.default_holds(start, start + A_DAY_S):
                refused.append(name)
                continue
            await repository.make_day(name, start, start + A_DAY_S)
        made.append(name)
    return made, refused


# Only a day wholly past and empty goes: its rows went with the calls erasure took, one by one,
# as each org's days said; a row of a call kept, or of an agent's own log, keeps it.
async def _drop_past(session: AsyncSession, repository: DayRepository, found: list[Partition], now: float) -> list[str]:
    dropped: list[str] = []
    for part in found:
        if part.upto is None or part.upto > day_of(now):
            continue
        async with session.begin_nested():
            if await repository.holds_rows(part.name):
                continue
            await repository.drop_day(part.name)
        dropped.append(part.name)
    return dropped
