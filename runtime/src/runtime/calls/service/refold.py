"""The facts folded again from the log: rebuilt a call at a time, and a sample checked by doctor."""

from dataclasses import dataclass, fields, replace
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.context import A_CALL
from runtime.calls.folds.facts import CallFacts, facts_of, fold, line_of
from runtime.calls.folds.state import reduce
from runtime.calls.repository.entries import EntryRepository
from runtime.calls.repository.facts import FactsRepository
from runtime.calls.repository.heads import HeadRepository
from runtime.calls.repository.rebuild import RebuildRepository, Refolding
from runtime.exceptions import ValidationError
from runtime.kit.text import JsonObject
from runtime.wire.base import Entry
from runtime.wire.events import EVENTS, event_of

# Calls named per read of the heads.
A_PAGE = 500
# What doctor refolds and compares, and how many of the heads behind their rows it names.
A_SAMPLE = 20
HEADS_EXAMINED = 20
# The column a sealed call's line is kept in, beside its fold.
LINE = "line"


@dataclass(frozen=True, slots=True)
class Rebuilt:
    """What a rebuild read, what it rewrote, and what it left: logs this release cannot read."""

    calls: int
    rewritten: int
    left: int


@dataclass(frozen=True, slots=True)
class Heads:
    """The heads doctor examined, and those among them whose rows are past their head's seq."""

    examined: int
    behind: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Differs:
    """A call whose stored facts are not what its log folds to, and the columns that differ."""

    call: str
    columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Refolded:
    """A call's facts as they are stored and as its log folds them now, with the line a sealed call keeps."""

    stored: CallFacts
    stored_line: JsonObject | None
    folded: CallFacts
    # None for a call still open: its line is written with its seal.
    line: JsonObject | None

    @property
    def columns_apart(self) -> tuple[str, ...]:
        """The columns whose stored value is not what the log folds to."""
        apart = [
            one.name for one in fields(CallFacts) if getattr(self.stored, one.name) != getattr(self.folded, one.name)
        ]
        if self.line is not None and self.line != self.stored_line:
            apart.append(LINE)
        return tuple(apart)


# Each call is refolded in a transaction of its own, committed before the next: the lock an append
# waits on is held for one call's fold and no longer. Until 2026-11 the rebuild ran in the one
# transaction its caller opened, each call under a savepoint, and releasing a savepoint releases no
# row lock: every live call it had visited could not append until the rebuild ended, and an append
# that waits 30 s fails its whole group.
async def rebuild(sessions: async_sessionmaker[AsyncSession], refolding: Refolding, *, page: int = A_PAGE) -> Rebuilt:
    """Fold each call's facts again from its log and write the row where it differs."""
    calls = rewritten = left = 0
    after = ""
    while names := await _list_calls_after(sessions, refolding, after, page):
        for call in names:
            wrote = await _rebuild_one(sessions, call)
            left += wrote is None
            rewritten += bool(wrote)
            calls += 1
        after = names[-1]
    return Rebuilt(calls=calls, rewritten=rewritten, left=left)


async def examine_heads(session: AsyncSession) -> Heads:
    """The newest heads and a sample of the rest, and those that gave out fewer seqs than rows."""
    rows = await RebuildRepository(session).list_heads_behind(f"{A_CALL}{uuid4().hex}", HEADS_EXAMINED)
    return Heads(examined=len(rows), behind=tuple(row.log for row in rows if row.behind))


async def list_differing(session: AsyncSession, *, sample: int = A_SAMPLE) -> list[Differs]:
    """Refold a sample of sealed calls and name each whose stored facts differ, and where."""
    found: list[Differs] = []
    for call in await RebuildRepository(session).list_sample(f"{A_CALL}{uuid4().hex}", sample):
        refolded = await refold(session, call)
        if refolded is not None and refolded.columns_apart:
            found.append(Differs(call=call, columns=refolded.columns_apart))
    return found


# The fold run as entries land, run over the whole log from nothing. A log holding an entry this
# release's wire refuses folds to None: the fold would pass the entry by and lose what the release
# that wrote it folded from it, so its stored row is the better account. A persona kept before the
# call started stands where the log names none (`FactsRepository.write_all`), and is no difference.
async def refold(session: AsyncSession, call: str) -> Refolded | None:
    """The call's facts as stored and as its log folds them now; None for a log this release cannot read."""
    row = await FactsRepository(session).find(call)
    stored = CallFacts(call=call) if row is None else facts_of(row)
    folded = CallFacts(call=call)
    entries = await EntryRepository(session).whole_of(call)
    for entry in entries:
        if _is_refused(entry):
            return None
        folded = fold(folded, entry)
    folded = replace(folded, persona=folded.persona or stored.persona)
    # A sealed call's line is the state's at the seal: folded again from the same log.
    sealed = await HeadRepository(session).is_sealed(call)
    return Refolded(
        stored=stored,
        stored_line=None if row is None else row.line,
        folded=folded,
        line=line_of(reduce(entries)) if sealed else None,
    )


async def _list_calls_after(
    sessions: async_sessionmaker[AsyncSession], refolding: Refolding, after: str, limit: int
) -> list[str]:
    async with sessions() as session:
        return await RebuildRepository(session).list_calls_after(refolding, after, limit)


# Whether the call's row was rewritten; None for a log left as it is.
async def _rebuild_one(sessions: async_sessionmaker[AsyncSession], call: str) -> bool | None:
    async with sessions.begin() as session:
        await RebuildRepository(session).lock_head(call)
        refolded = await refold(session, call)
        if refolded is None:
            return None
        apart = refolded.columns_apart
        if set(apart) - {LINE}:
            await FactsRepository(session).write_all([refolded.folded])
        if LINE in apart:
            await FactsRepository(session).keep(call, line=refolded.line)
        return bool(apart)


def _is_refused(entry: Entry) -> bool:
    if entry.ephemeral or entry.type not in EVENTS:
        return False
    try:
        event_of(entry)
    except ValidationError:
        return True
    return False
