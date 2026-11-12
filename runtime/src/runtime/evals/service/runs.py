"""An eval run's record: what is kept of a run, and what an erasure takes of it."""

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.evals.repository import RunRepository


# The row names its org with no key to it, so no cascade reaches it: the erasure of an org, or of one
# of its agents, asks here (`EvalRun.__kept__`).
async def delete_runs(session: AsyncSession, org: str, agent: str | None = None) -> int:
    """Delete the org's eval runs, one agent's or all; how many went."""
    return await RunRepository(session).delete_of_org(org, agent)
