"""The comparison endpoints: callers against the agent under several setups, and the comparison read."""

from fastapi import APIRouter

from runtime.evals import schemas
from runtime.evals.auth import EvalsKey, TheHarness
from runtime.evals.endpoints.simulations import check_agent_values, simulation_of
from runtime.evals.service import comparisons
from runtime.postgres import Session

router = APIRouter()


# Every configuration is checked before anything is placed: one the key may not name refuses the whole.
@router.post("/v1/simulations/compare")
async def compare(body: schemas.ComparisonRequest, actor: EvalsKey, parts: TheHarness) -> schemas.ComparisonStarted:
    """Each persona against the agent under each voice and models named, as many times as asked; what started."""
    against = [check_agent_values(actor, values) for values in body.against]
    personas = list(dict.fromkeys([body.persona, *body.more_personas]))
    begun = await comparisons.start_comparison(parts, actor, simulation_of(body), against, personas, body.repeats)
    return schemas.ComparisonStarted.of_begun(begun)


@router.get("/v1/simulations/compare/{comparison}")
async def read_comparison(comparison: str, actor: EvalsKey, parts: TheHarness, session: Session) -> schemas.Comparison:
    """The comparison's calls, each caller's best first: its goal held, every judge, the fastest, the cheapest."""
    read = await comparisons.get_comparison(session, parts, actor, comparison)
    return schemas.Comparison.of_read(read.plan, read.rows, planned=read.planned, abandoned=read.abandoned)
