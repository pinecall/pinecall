"""The eval runs and the comparisons, each a document written whole; a run's lease; the callers' jobs; the labels."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from runtime.enums import Env
from runtime.evals.models import CallerJob, Comparison, EvalRun, JudgeLabel, RunLease
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

    # Every gateway passes: the row is locked by the one that finds it and skipped by the others until
    # that one's transaction ends, in which it writes that it has it. A comparison made before
    # 2026-11-24 says nothing of `done` and is never found.
    async def find_left(self, before: float) -> Comparison | None:
        """A comparison of any org still to be played that no gateway said anything of since `before`, locked."""
        undone = Comparison.document["done"].as_boolean().is_(False)
        quiet = Comparison.document["heard_at"].as_float() < before
        oldest = self.statement().where(undone, quiet).order_by(Comparison.started_at).limit(1)
        return await self.one_or_none(oldest.with_for_update(skip_locked=True))


# A job is open until it ended. Open and unclaimed with its document, it waits for a process; claimed,
# it is its process's for as long as that one says so; said broken, it waits for a gateway to end its
# call. Every reader that takes a row to act on it locks the row and skips the ones another holds.
class CallerJobRepository(Repository[CallerJob]):
    """One row per simulated caller of a spoken call, from its place on the line to an hour past its end."""

    model = CallerJob

    # Held to the end of the transaction, by every gateway alike, as a fleet's seats are taken
    # (`fleet.repository.take_turns`): the count and the row that takes the place are one step.
    async def take_turns(self, org: str, env: Env) -> None:
        """Wait for whoever is placing a caller of the org in the env now: a place is counted and taken in one step."""
        line = func.hashtext(f"caller_jobs:{org}:{env.value}")
        await self.session.execute(select(func.pg_advisory_xact_lock(line)))

    async def count_open(self, org: str, env: Env) -> int:
        """How many of the org's callers in the env have a place on its line: placed, and not over."""
        return await self.count(
            self.statement().where(CallerJob.org == org, CallerJob.env == env, CallerJob.ended_at.is_(None))
        )

    async def find(self, call: str) -> CallerJob | None:
        """The call's job, or None for a call no row was written for."""
        return await self.one_or_none(self.statement().where(CallerJob.call == call))

    async def list_of_calls(self, calls: Sequence[str]) -> Sequence[CallerJob]:
        """The jobs of these calls, those that have one."""
        return await self.all(self.statement().where(CallerJob.call.in_(calls))) if calls else []

    async def complete(self, call: str, document: dict[str, Any]) -> None:
        """Say the call's simulation, as it was placed: from here a process may claim it."""
        await self.change(update(CallerJob).where(CallerJob.call == call).values(document=document))

    async def drop(self, call: str) -> None:
        """Give the call's place back: its placing was refused before it could be played."""
        await self.change(delete(CallerJob).where(CallerJob.call == call))

    # The org that holds the fewest callers at a process goes first, then the caller placed first: the
    # rule a fleet's seats are shared by (`fleet.service.shares`), so one org's comparison never holds
    # every process while another org's caller waits to ask for a seat.
    async def claim(self, process: str, now: float) -> CallerJob | None:
        """Take the next caller that waits for a process, as this one's; None when none waits."""
        held = CallerJob.__table__.alias("held")
        holding = (
            select(func.count())
            .select_from(held)
            .where(held.c.org == CallerJob.org, held.c.claimed_by.is_not(None), held.c.ended_at.is_(None))
            .scalar_subquery()
        )
        waiting = (
            self.statement()
            .where(
                CallerJob.document.is_not(None),
                CallerJob.claimed_by.is_(None),
                CallerJob.broke.is_(None),
                CallerJob.ended_at.is_(None),
            )
            .order_by(holding, CallerJob.placed_at)
            .limit(1)
            .with_for_update(skip_locked=True, of=CallerJob)
        )
        job = await self.one_or_none(waiting)
        if job is not None:
            job.claimed_by, job.heard_at, job.played = process, now, job.played + 1
            await self.session.flush()
        return job

    # Only the callers it names: one whose task ended without letting go of its row (the database was
    # away for the whole of it) stops being said, and is taken up as left.
    async def renew(self, process: str, calls: Sequence[str], now: float) -> None:
        """Say the process still plays these callers, of the ones it claimed."""
        still = update(CallerJob).where(CallerJob.claimed_by == process, CallerJob.call.in_(calls))
        await self.change(still.where(CallerJob.ended_at.is_(None)).values(heard_at=now))

    # Each of the three ways a process lets go of a caller is its own alone: a row another process took
    # since (this one was taken for gone) is not written over.
    async def end(self, call: str, process: str, now: float, *, lost: bool) -> None:
        """The job is over for the process that played it; `lost` when it left the call on the line."""
        mine = update(CallerJob).where(CallerJob.call == call, CallerJob.claimed_by == process)
        await self.change(mine.where(CallerJob.ended_at.is_(None)).values(ended_at=now, lost=lost))

    async def say_broke(self, call: str, process: str, why: str) -> None:
        """The process could not play the caller, before the call began: why, for a gateway to end the call with."""
        mine = update(CallerJob).where(CallerJob.call == call, CallerJob.claimed_by == process)
        await self.change(mine.where(CallerJob.ended_at.is_(None)).values(broke=why))

    async def release(self, call: str, process: str) -> None:
        """The process lets a caller go whose call never began: another one claims it and plays it whole."""
        mine = update(CallerJob).where(CallerJob.call == call, CallerJob.claimed_by == process)
        await self.change(mine.where(CallerJob.ended_at.is_(None)).values(claimed_by=None, heard_at=None))

    async def find_broken(self) -> CallerJob | None:
        """A caller its process said it could not play, whose call no gateway ended yet, locked."""
        broken = self.statement().where(CallerJob.broke.is_not(None), CallerJob.ended_at.is_(None))
        return await self.one_or_none(broken.order_by(CallerJob.placed_at).limit(1).with_for_update(skip_locked=True))

    async def find_left(self, before: float) -> CallerJob | None:
        """A caller whose process said nothing of it since `before`, locked: that process is gone."""
        left = self.statement().where(
            CallerJob.claimed_by.is_not(None),
            CallerJob.broke.is_(None),
            CallerJob.ended_at.is_(None),
            CallerJob.heard_at < before,
        )
        return await self.one_or_none(left.order_by(CallerJob.placed_at).limit(1).with_for_update(skip_locked=True))

    async def find_unclaimed(self, before: float) -> CallerJob | None:
        """A caller placed before the moment that no process ever took, locked: nothing plays callers here."""
        unclaimed = self.statement().where(
            CallerJob.claimed_by.is_(None), CallerJob.broke.is_(None), CallerJob.ended_at.is_(None)
        )
        oldest = unclaimed.where(CallerJob.placed_at < before).order_by(CallerJob.placed_at).limit(1)
        return await self.one_or_none(oldest.with_for_update(skip_locked=True))

    async def count_open_of(self, comparison: str) -> int:
        """How many of the comparison's callers are not over: waiting for a process, or played by one."""
        return await self.count(
            self.statement().where(CallerJob.comparison == comparison, CallerJob.ended_at.is_(None))
        )

    async def list_lost(self, comparison: str) -> Sequence[CallerJob]:
        """The comparison's callers a process left on the line: each call is over, its caller not played whole."""
        return await self.all(self.statement().where(CallerJob.comparison == comparison, CallerJob.lost.is_(True)))

    async def delete_older_than(self, moment: float, *, unplaced_before: float) -> None:
        """Rows whose job was over before the moment, and places a placing took before the other and never filled."""
        over = CallerJob.ended_at < moment
        never_placed = CallerJob.document.is_(None) & (CallerJob.placed_at < unplaced_before)
        await self.change(delete(CallerJob).where(over | never_placed))


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
