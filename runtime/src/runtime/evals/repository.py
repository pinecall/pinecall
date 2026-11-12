"""The eval runs and the comparisons, each a document written whole; the lease a run holds its agent by; the labels."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from runtime.enums import Env
from runtime.evals.models import Comparison, EvalRun, JudgeLabel, RunLease
from runtime.kit.repository import Repository

# Each label beside the verdict the seal counted for the same judge on the same call, when one.
AGREEMENT = text("""
select label.judge,
       count(*) as labelled,
       count(verdict.held) as compared,
       count(*) filter (where verdict.held = label.held) as agreed
from judge_labels label
left join drift_calls counted on counted.call = label.call
left join lateral (
    select (item ->> 'held')::boolean as held
    from jsonb_array_elements(counted.verdicts) as item
    where item ->> 'judge' = label.judge
    limit 1
) verdict on true
where label.org = :org and label.env = :env
  and (cast(:agent as text) is null or label.agent = :agent)
group by label.judge
order by label.judge
""")


@dataclass(frozen=True, slots=True)
class AgreementRow:
    """One judge against the labels: how many, how many had its verdict beside them, agreed."""

    judge: str
    labelled: int
    compared: int
    agreed: int


class RunRepository(Repository[EvalRun]):
    """One row per run, its document the whole run as it is read."""

    model = EvalRun

    async def put(self, run: EvalRun) -> None:
        """Write the run whole, in its org and env; the same id again replaces its state."""
        values: dict[str, Any] = {
            "id": run.id,
            "org": run.org,
            "env": run.env,
            "agent": run.agent,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status,
            "document": run.document,
        }
        await self.upsert(values, key=["id"])

    async def find(self, org: str, env: Env, run: str) -> EvalRun | None:
        """One run of the org in the env; None for any other's."""
        return await self.one_or_none(self.statement().where(EvalRun.id == run, EvalRun.org == org, EvalRun.env == env))

    # The agent is filtered in SQL, so one agent's runs are never paged out by another's.
    async def list_newest(
        self, org: str, env: Env, *, agent: str | None, since: float, limit: int
    ) -> Sequence[EvalRun]:
        """The org's runs in the env started after `since`, newest first, one agent's or all."""
        statement = self.statement().where(EvalRun.org == org, EvalRun.env == env, EvalRun.started_at > since)
        if agent is not None:
            statement = statement.where(EvalRun.agent == agent)
        return await self.all(statement.order_by(EvalRun.started_at.desc()).limit(limit))

    async def delete_of_org(self, org: str, agent: str | None) -> int:
        """Delete the org's runs, one agent's or all; how many went."""
        statement = delete(EvalRun).where(EvalRun.org == org)
        return await self.change(statement if agent is None else statement.where(EvalRun.agent == agent))


class RunLeaseRepository(Repository[RunLease]):
    """The run each agent is under, on any gateway of the box: renewed while it runs, runs out alone."""

    model = RunLease

    # Taken when nobody holds the agent or the holder's lease ran out; else the holder is named.
    async def take(self, agent: str, run: str, seconds: float) -> bool:
        """Hold the agent for the run until `seconds` from now; False while another run holds it."""
        until = func.now() + timedelta(seconds=seconds)
        statement = (
            insert(RunLease)
            .values(agent=agent, run=run, until=until)
            .on_conflict_do_update(
                index_elements=["agent"],
                set_={"run": run, "until": until},
                where=(RunLease.until < func.now()) | (RunLease.run == run),
            )
            .returning(RunLease.run)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def holder_of(self, agent: str) -> str | None:
        """The run holding the agent, lease run out or not; None when none ever did."""
        return (await self.session.execute(select(RunLease.run).where(RunLease.agent == agent))).scalar_one_or_none()

    async def release(self, agent: str, run: str) -> None:
        """Let the agent go, if this run still holds it."""
        await self.change(delete(RunLease).where(RunLease.agent == agent, RunLease.run == run))


class ComparisonRepository(Repository[Comparison]):
    """One row per comparison, its document what was asked for and how its placing stands."""

    model = Comparison

    async def put(self, comparison: Comparison) -> None:
        """Write the comparison whole, in its org and env; the same id again replaces its document."""
        values: dict[str, Any] = {
            "id": comparison.id,
            "org": comparison.org,
            "env": comparison.env,
            "agent": comparison.agent,
            "started_at": comparison.started_at,
            "document": comparison.document,
        }
        statement = insert(Comparison).values(**values)
        replaced = {"document": statement.excluded.document}
        await self.session.execute(statement.on_conflict_do_update(index_elements=["id"], set_=replaced))

    async def find(self, org: str, env: Env, comparison: str) -> Comparison | None:
        """One comparison of the org in the env; None for any other's."""
        return await self.one_or_none(
            self.statement().where(Comparison.id == comparison, Comparison.org == org, Comparison.env == env)
        )


class LabelRepository(Repository[JudgeLabel]):
    """One label per call and judge: what a person said the judge should have answered."""

    model = JudgeLabel

    async def put(self, label: JudgeLabel) -> None:
        """Keep the label, replacing the one before it for the same call and judge."""
        values: dict[str, Any] = {
            "call": label.call,
            "judge": label.judge,
            "org": label.org,
            "env": label.env,
            "agent": label.agent,
            "held": label.held,
            "note": label.note,
            "author": label.author,
        }
        statement = insert(JudgeLabel).values(**values)
        replaced = {name: statement.excluded[name] for name in ("held", "note", "author")} | {"labelled_at": func.now()}
        await self.session.execute(statement.on_conflict_do_update(index_elements=["call", "judge"], set_=replaced))

    async def measure_agreement(self, org: str, env: Env, agent: str | None) -> list[AgreementRow]:
        """Each judge against the labels on the org's calls in the env, one agent's or all."""
        rows = (await self.session.execute(AGREEMENT, {"org": org, "env": env.value, "agent": agent})).all()
        return [
            AgreementRow(str(judge), int(labelled), int(compared), int(agreed))
            for judge, labelled, compared, agreed in rows
        ]
