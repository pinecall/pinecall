"""An agent's pipeline as its next call would run it, to read: its stages, what its org could run, how fast it ran."""

from fastapi import APIRouter

from runtime.agents import schemas
from runtime.agents.auth import PipelineKey, TheAgent
from runtime.agents.service import pipeline
from runtime.calls import service as calls
from runtime.calls.auth import TheLogs
from runtime.handles import TheVault
from runtime.postgres import Session

router = APIRouter()

# Medians pool the turns of this many calls, so a short call weighs as much as its turns.
LAST_CALLS = 20


# Nothing is built: a vendor without a key is a reason, not a failure. The latencies are folded from
# the logs of the agent's last calls, which are `calls`', above this domain.
@router.get("/v1/agents/{slug}/pipeline")
async def get_pipeline(
    agent: TheAgent, actor: PipelineKey, vault: TheVault, logs: TheLogs, session: Session
) -> schemas.PipelineReport:
    """The agent's three stages, the catalogue, and the latencies of its last calls."""
    counted, medians = await calls.measure_latencies(session, logs, agent.slug, LAST_CALLS)
    measured = pipeline.Measured(calls=counted, medians=medians)
    return schemas.PipelineReport.of(await pipeline.report_on(session, vault, actor.scope, agent, measured))
