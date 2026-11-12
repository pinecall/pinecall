"""The call_facts rows: the folded columns locked and written by the writer, and what is kept beside the fold."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from runtime.calls.folds.facts import FOLDED_COLUMNS, CallFacts
from runtime.calls.models import CallFact, CallLogHead
from runtime.enums import Env
from runtime.kit.repository import Repository

# What no entry of a call's log says, kept in its row by whoever knows it: the vendors the call ran
# on the box's own key (the seal), who played a simulated caller, what the agent ran on over its
# settings and the comparison it was placed in, how a simulated call was heard (evals), and the
# line a list shows (the seal). A fold never writes these. `persona` is both: folded from
# `call.started`, and kept by a simulation placed before its call starts. `caller_cost_usd` is
# added to, never set (`add_caller_cost`).
KEPT_COLUMNS = frozenset(
    {"lent", "caller_llm", "caller_tts", "caller_voice", "against", "comparison", "hearing", "line", "persona"}
)


@dataclass(frozen=True, slots=True)
class Billed:
    """What a call's bill reads beside its summary: the vendors it ran on the box's key, and its caller's cost."""

    lent: tuple[str, ...]
    caller_cost_usd: float


@dataclass(frozen=True, slots=True)
class AgentFacts:
    """A call's facts row with the agent its head names."""

    row: CallFact
    agent: str


class FactsRepository(Repository[CallFact]):
    """What is known of every call without folding its log."""

    model = CallFact

    async def find(self, call: str) -> CallFact | None:
        """The facts of one call, or None while nothing folded into them."""
        return await self.one_or_none(self.statement().where(CallFact.call == call))

    async def list_ended_of_org(self, org: str) -> list[str]:
        """The org's calls that ended, in either env: the newborns' sweep reads them box-wide."""
        statement = (
            select(CallLogHead.log)
            .join(CallFact, CallFact.call == CallLogHead.log)
            .where(CallLogHead.org == org, CallLogHead.call.is_not(None), CallFact.ended_at.is_not(None))
        )
        return [str(log) for log in (await self.session.execute(statement)).scalars()]

    # A summary is what gives a call its cost, so a simulated call with none has begun and not ended.
    async def count_simulating(self, org: str, env: Env, since: float, simulated_from: str) -> int:
        """How many simulated calls of the org in the env began since then and have no summary yet."""
        statement = (
            select(func.count())
            .select_from(CallLogHead)
            .join(CallFact, CallFact.call == CallLogHead.log)
            .where(
                CallLogHead.org == org,
                CallLogHead.env == env,
                CallLogHead.call.is_not(None),
                CallLogHead.sealed.is_(False),
                CallLogHead.started_at >= since,
                CallFact.cost_usd.is_(None),
                or_(CallFact.persona.is_not(None), CallFact.from_number == simulated_from),
            )
        )
        return int((await self.session.execute(statement)).scalar_one())

    # In the order of the calls, as the heads are locked: two writers never wait in a circle.
    async def lock(self, calls: Sequence[str]) -> dict[str, CallFact]:
        """The facts rows of these calls, locked for the writer's transaction."""
        statement = self.statement().where(CallFact.call.in_(list(calls))).order_by(CallFact.call).with_for_update()
        return {row.call: row for row in await self.all(statement)}

    # The folded columns are written whole every time: the merge happened in the fold, in one place.
    # The others are not named, so they stand: until 2026-11 the statement replaced the row whole, a
    # `facts rebuild` emptied what the log does not hold (the vendors lent, a simulated caller's cost)
    # and a call's first fold could write over a column kept a moment before it. A persona is the one
    # column both write: the fold never unsets it, so one kept stands where the log names none.
    async def write_all(self, rows: Sequence[CallFacts]) -> None:
        """Insert each call's folded columns, or replace them where its row is there; what is kept beside them stays."""
        if not rows:
            return
        statement = insert(CallFact)
        excluded = statement.excluded
        folded: dict[str, ColumnElement[Any]] = {
            name: excluded[name] for name in FOLDED_COLUMNS if name not in ("call", "persona")
        }
        folded["persona"] = func.coalesce(excluded.persona, CallFact.persona)
        await self.session.execute(
            statement.on_conflict_do_update(index_elements=[CallFact.call], set_=folded),
            [row.as_row() for row in rows],
        )

    # One statement for what were five (`set_lent`, `keep_caller`, `keep_hearing`, `keep_against`,
    # `set_line`), each the same upsert of other columns. A persona kept as None leaves the one the
    # log folded, as `keep_against` always did.
    async def keep(self, call: str, **columns: object) -> None:
        """Keep these columns of the call's row beside its fold, making the row when nothing folded into it yet."""
        unknown = sorted(set(columns) - KEPT_COLUMNS)
        if unknown or not columns:
            raise ValueError(f"call_facts keeps {sorted(KEPT_COLUMNS)} beside the fold, not {unknown}")
        statement = insert(CallFact).values(call=call, **columns)
        excluded = statement.excluded
        kept: dict[str, ColumnElement[Any]] = {name: excluded[name] for name in columns if name != "persona"}
        if "persona" in columns:
            kept["persona"] = func.coalesce(excluded.persona, CallFact.persona)
        await self.session.execute(statement.on_conflict_do_update(index_elements=[CallFact.call], set_=kept))

    # Not a fold: a simulation's caller speaks line by line, and each simulation adds what it spent.
    async def add_caller_cost(self, call: str, usd: float) -> None:
        """Add what a simulated caller's model and voice cost to the call's facts."""
        statement = insert(CallFact).values(call=call, caller_cost_usd=usd)
        statement = statement.on_conflict_do_update(
            index_elements=[CallFact.call],
            set_={"caller_cost_usd": CallFact.caller_cost_usd + statement.excluded.caller_cost_usd},
        )
        await self.session.execute(statement)

    async def list_billed(self, calls: Sequence[str]) -> dict[str, Billed]:
        """For each of the calls that has either: the vendors it ran on the box's key, and its caller's cost."""
        if not calls:
            return {}
        statement = select(CallFact.call, CallFact.lent, CallFact.caller_cost_usd).where(
            CallFact.call.in_(list(calls)),
            (func.cardinality(CallFact.lent) > 0) | (CallFact.caller_cost_usd > 0),
        )
        rows = (await self.session.execute(statement)).all()
        return {call: Billed(tuple(lent), float(caller)) for call, lent, caller in rows}

    async def list_with_agent(self, calls: Sequence[str]) -> dict[str, AgentFacts]:
        """The facts of each of the calls that has a row, with its agent off the head."""
        if not calls:
            return {}
        statement = (
            select(CallFact, CallLogHead.agent)
            .join(CallLogHead, CallLogHead.log == CallFact.call)
            .where(CallFact.call.in_(list(calls)))
        )
        rows = (await self.session.execute(statement)).all()
        return {row[0].call: AgentFacts(row[0], row[1] or "") for row in rows}
