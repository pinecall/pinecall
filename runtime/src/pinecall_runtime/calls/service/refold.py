"""The facts folded again from the log: rebuilt a call at a time, and a sample checked by doctor."""

from dataclasses import dataclass, fields, replace
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.context import A_CALL
from pinecall_runtime.calls.facts import CallFacts, facts_of, fold, line_of
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.calls.repository.facts import COLUMNS, FactsRepository
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.repository.refold import Refolding, RefoldRepository
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import EVENTS, event_of

# Calls named per read of the heads; each is refolded in a transaction of its own, so a rebuild
# never holds a lock longer than one call's fold.
A_PAGE = 500
# What doctor refolds and compares, and how many of the heads behind their rows it names.
A_SAMPLE = 20
HEADS_EXAMINED = 20


@dataclass(frozen=True)
class Rebuilt:
    """What a rebuild read, what it rewrote, and what it left: logs this release cannot read."""

    calls: int
    rewritten: int
    left: int


@dataclass(frozen=True)
class Heads:
    """The heads doctor examined, and those among them whose rows are past their head's seq."""

    examined: int
    behind: tuple[str, ...]


@dataclass(frozen=True)
class Differs:
    """A call whose stored facts are not what its log folds to, and the columns that differ."""

    call: str
    columns: tuple[str, ...]


async def rebuild(session: AsyncSession, refolding: Refolding, *, page: int = A_PAGE) -> Rebuilt:
    """Fold each call's facts again from its log and write the row where it differs."""
    repository = RefoldRepository(session)
    calls = rewritten = left = 0
    after = ""
    while names := await repository.calls_after(refolding, after, page):
        for call in names:
            async with session.begin_nested():
                await repository.lock_head(call)
                stored, folded = await _refolded(session, call)
                if folded is None:
                    left += 1
                elif folded != (stored or CallFacts(call=call)):
                    await FactsRepository(session).write_all([folded.as_row()])
                    rewritten += 1
            calls += 1
        after = names[-1]
    return Rebuilt(calls=calls, rewritten=rewritten, left=left)


async def heads_behind(session: AsyncSession) -> Heads:
    """The newest heads and a sample of the rest, and those that gave out fewer seqs than rows."""
    rows = await RefoldRepository(session).heads_behind(f"{A_CALL}{uuid4().hex}", HEADS_EXAMINED)
    return Heads(examined=len(rows), behind=tuple(str(row.log) for row in rows if row.behind))


async def differing(session: AsyncSession, *, sample: int = A_SAMPLE) -> list[Differs]:
    """Refold a sample of sealed calls and name each whose stored facts differ, and where."""
    repository = RefoldRepository(session)
    found: list[Differs] = []
    for call in await repository.sample(f"{A_CALL}{uuid4().hex}", sample):
        stored, folded = await _refolded(session, call)
        if folded is None:
            continue
        columns = _columns_apart(stored or CallFacts(call=call), folded)
        if columns:
            found.append(Differs(call=call, columns=columns))
    return found


# The fold run as entries land, run over the whole log from nothing. A log holding an entry this
# release's wire refuses folds to None: the fold would pass the entry by and lose what the release
# that wrote it folded from it, so its stored row is the better account.
async def _refolded(session: AsyncSession, call: str) -> tuple[CallFacts | None, CallFacts | None]:
    row = await FactsRepository(session).get(call)
    stored = None if row is None else facts_of(row)
    folded = CallFacts(call=call)
    entries = await RefoldRepository(session).entries_of(call)
    for entry in entries:
        if _refused(entry):
            return stored, None
        folded = fold(folded, entry)
    # A sealed call's line is the state's at the seal: folded again from the same log.
    if await HeadRepository(session).is_sealed(call):
        folded = replace(folded, line=line_of(reduce(entries)))
    return stored, folded


def _columns_apart(stored: CallFacts, folded: CallFacts) -> tuple[str, ...]:
    return tuple(
        f.name for f in fields(CallFacts) if f.name in COLUMNS and getattr(stored, f.name) != getattr(folded, f.name)
    )


def _refused(entry: Entry) -> bool:
    if entry.ephemeral or entry.type not in EVENTS:
        return False
    try:
        event_of(entry)
    except ValidationError:
        return True
    return False
