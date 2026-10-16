"""The eval runs, each a document written whole as it goes, and the lease a run holds its agent by."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.enums import Env
from pinecall_runtime.evals.models import EvalRun, RunLease
from pinecall_runtime.kit.repository import Repository


class RunRepository(Repository[EvalRun]):
    """One row per run, its document the whole run as the endpoints send it."""

    model = EvalRun

    async def put(
        self,
        *,
        id: str,
        org: str,
        env: Env,
        agent: str,
        started_at: float,
        finished_at: float | None,
        status: str,
        document: dict[str, Any],
    ) -> None:
        """Write the run whole, in its org and env; the same id again replaces its state."""
        statement = upsert(EvalRun).values(
            id=id,
            org=org,
            env=env,
            agent=agent,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            document=document,
        )
        replaced = {
            "finished_at": statement.excluded.finished_at,
            "status": statement.excluded.status,
            "document": statement.excluded.document,
        }
        await self.session.execute(statement.on_conflict_do_update(index_elements=["id"], set_=replaced))

    async def get(self, org: str, env: Env, run: str) -> EvalRun | None:
        """One run of the org in the env; None for any other's."""
        return await self.one_or_none(self.statement().where(EvalRun.id == run, EvalRun.org == org, EvalRun.env == env))

    # The agent is filtered in SQL, so one agent's runs are never paged out by another's.
    async def listed(self, org: str, env: Env, *, agent: str | None, since: float, limit: int) -> Sequence[EvalRun]:
        """The org's runs in the env started after `since`, newest first, one agent's or all."""
        statement = self.statement().where(EvalRun.org == org, EvalRun.env == env, EvalRun.started_at > since)
        if agent is not None:
            statement = statement.where(EvalRun.agent == agent)
        return await self.all(statement.order_by(EvalRun.started_at.desc()).limit(limit))


class RunLeaseRepository(Repository[RunLease]):
    """The run each agent is under, on any gateway of the box: renewed while it runs, runs out alone."""

    model = RunLease

    # Taken when nobody holds the agent or the holder's lease ran out; else the holder is named.
    async def take(self, agent: str, run: str, seconds: float) -> bool:
        """Hold the agent for the run until `seconds` from now; False while another run holds it."""
        until = func.now() + timedelta(seconds=seconds)
        statement = (
            upsert(RunLease)
            .values(agent=agent, run=run, until=until)
            .on_conflict_do_update(
                index_elements=["agent"],
                set_={"run": run, "until": until},
                where=(RunLease.until < func.now()) | (RunLease.run == run),
            )
            .returning(RunLease.run)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def holder(self, agent: str) -> str | None:
        """The run holding the agent, lease run out or not; None when none ever did."""
        return (await self.session.execute(select(RunLease.run).where(RunLease.agent == agent))).scalar_one_or_none()

    async def release(self, agent: str, run: str) -> None:
        """Let the agent go, if this run still holds it."""
        await self.changed(delete(RunLease).where(RunLease.agent == agent, RunLease.run == run))
