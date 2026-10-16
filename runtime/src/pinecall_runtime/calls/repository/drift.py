"""The drift tables: a sealed call claimed once, its stages and verdicts added into its day."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Row, bindparam, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert

from pinecall_runtime.calls.models import CallLogHead, DriftCall
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository

# Two histograms add bucket by bucket (calls/histogram); both always have its BUCKETS.
STAGES_ADDED = text("""
insert into stage_days as kept (org, env, holder, agent, day, config_version, stage, vendor,
                                model, turns, buckets, confidence_sum, confidence_turns)
select :org, :env, :holder, :agent, :day, :version, sample.stage,
       sample.vendor, sample.model, sample.turns, sample.buckets, sample.confidence_sum,
       sample.confidence_turns
from jsonb_to_recordset(:samples) as sample(stage text, vendor text, model text,
     turns integer, buckets integer[], confidence_sum double precision, confidence_turns integer)
on conflict (org, env, holder, day, agent, config_version, stage, vendor, model) do update set
    turns = kept.turns + excluded.turns,
    buckets = (select array_agg(mine + theirs order by at)
               from unnest(kept.buckets, excluded.buckets) with ordinality as bucket(mine, theirs, at)),
    confidence_sum = kept.confidence_sum + excluded.confidence_sum,
    confidence_turns = kept.confidence_turns + excluded.confidence_turns
""").bindparams(bindparam("samples", type_=JSONB))

# A verdict counted is +1 on its side; a verdict replaced is -1 on the side it was counted on.
VERDICTS_ADDED = text("""
insert into judge_days as kept (org, env, holder, agent, day, config_version, judge, criteria, held, broken)
select :org, :env, :holder, :agent, :day, :version, verdict.judge, verdict.criteria, verdict.held, verdict.broken
from jsonb_to_recordset(:verdicts) as verdict(judge text, criteria text, held integer, broken integer)
on conflict (org, env, holder, day, agent, config_version, judge, criteria) do update set
    held = kept.held + excluded.held,
    broken = kept.broken + excluded.broken
""").bindparams(bindparam("verdicts", type_=JSONB))

# A side is a day, a version, or both; one agent's rows in the scope.
ONE_SIDE = """
where org = :org and env = :env and holder = :holder and agent = :agent
  and (cast(:day as date) is null or day = :day)
  and (cast(:version as integer) is null or config_version = :version)
"""
SIDE_STAGES = text(
    f"select stage, vendor, model, config_version, turns, buckets, confidence_sum, confidence_turns from "
    f"stage_days {ONE_SIDE}"
)
SIDE_VERDICTS = text(f"select judge, criteria, config_version, held, broken from judge_days {ONE_SIDE}")

WINDOW_STAGES = text("""
select stage, vendor, model, turns, buckets, confidence_sum, confidence_turns
from stage_days
where org = :org and env = :env and holder = :holder
  and day >= :first and day <= :last and (cast(:agent as text) is null or agent = :agent)
""")

# A rebuild forgets what it will fold again, in one transaction, then folds call by call.
FORGET = text("""
with calls as (
    delete from drift_calls
    where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
), stages as (
    delete from stage_days
    where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
)
delete from judge_days
where (cast(:org as text) is null or org = :org) and (cast(:since as date) is null or day >= :since)
""")


@dataclass(frozen=True, slots=True)
class Where:
    """Which day's row a call is counted on: its scope, its agent, its day, its version."""

    org: str
    env: Env
    holder: str
    agent: str
    day: date
    version: int

    def params(self) -> dict[str, Any]:
        """As the statements take it."""
        return {
            "org": self.org,
            "env": self.env.value,
            "holder": self.holder,
            "agent": self.agent,
            "day": self.day,
            "version": self.version,
        }


class DriftRepository(Repository[DriftCall]):
    """One row per sealed call counted, and the days its stages and verdicts added into."""

    model = DriftCall

    # Taken once per call: a second fold of the same call finds its row and changes only what differs.
    async def claim(
        self, call: str, where: Where, verdicts: list[dict[str, Any]], tools_ran: int, tools_failed: int
    ) -> bool:
        """Count the call once; False when it was counted already."""
        statement = insert(DriftCall).values(
            call=call,
            org=where.org,
            env=where.env,
            holder=where.holder,
            agent=where.agent,
            day=where.day,
            config_version=where.version,
            verdicts=verdicts,
            tools_ran=tools_ran,
            tools_failed=tools_failed,
        )
        written = statement.on_conflict_do_nothing(index_elements=[DriftCall.call]).returning(DriftCall.call)
        return (await self.session.execute(written)).scalar_one_or_none() is not None

    async def verdicts_counted(self, call: str) -> list[dict[str, Any]] | None:
        """The verdicts the call was counted with, locked for a recount."""
        statement = select(DriftCall.verdicts).where(DriftCall.call == call).with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def recount(self, call: str, verdicts: list[dict[str, Any]]) -> None:
        """Keep the verdicts the call is counted with now."""
        await self.session.execute(update(DriftCall).where(DriftCall.call == call).values(verdicts=verdicts))

    async def add_stages(self, where: Where, samples: Sequence[Mapping[str, Any]]) -> None:
        """Add the stage samples into the day's rows."""
        if samples:
            await self.session.execute(STAGES_ADDED, {**where.params(), "samples": list(samples)})

    async def add_verdicts(self, where: Where, verdicts: Sequence[Mapping[str, Any]]) -> None:
        """Add the verdict counts into the day's rows."""
        if verdicts:
            await self.session.execute(VERDICTS_ADDED, {**where.params(), "verdicts": list(verdicts)})

    async def side_stages(self, scope: Scope, agent: str, day: date | None, version: int | None) -> Sequence[Row[Any]]:
        """The stage rows of one side."""
        return (await self.session.execute(SIDE_STAGES, _side(scope, agent, day, version))).all()

    async def side_verdicts(
        self, scope: Scope, agent: str, day: date | None, version: int | None
    ) -> Sequence[Row[Any]]:
        """The judge rows of one side."""
        return (await self.session.execute(SIDE_VERDICTS, _side(scope, agent, day, version))).all()

    async def window_stages(self, scope: Scope, first: date, last: date, agent: str | None) -> Sequence[Row[Any]]:
        """Every stage row of the scope's days first to last."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "holder": scope.holder,
            "first": first,
            "last": last,
            "agent": agent,
        }
        return (await self.session.execute(WINDOW_STAGES, params)).all()

    async def forget(self, org: str | None, since: date | None) -> None:
        """Drop the drift of the calls named: an org's, those since a day, or every one."""
        await self.session.execute(FORGET, {"org": org, "since": since})

    async def sealed_after(self, org: str | None, since: float | None, after: str, limit: int) -> list[str]:
        """A page of the sealed, started calls past the cursor, for a rebuild."""
        statement = select(CallLogHead.log).where(
            CallLogHead.call.is_not(None),
            CallLogHead.sealed,
            CallLogHead.started_at.is_not(None),
            CallLogHead.log > after,
        )
        if org is not None:
            statement = statement.where(CallLogHead.org == org)
        if since is not None:
            statement = statement.where(CallLogHead.started_at >= since)
        rows = await self.session.execute(statement.order_by(CallLogHead.log).limit(limit))
        return [str(log) for log in rows.scalars()]


def _side(scope: Scope, agent: str, day: date | None, version: int | None) -> dict[str, Any]:
    return {
        "org": scope.org,
        "env": scope.env.value,
        "holder": scope.holder,
        "agent": agent,
        "day": day,
        "version": version,
    }
