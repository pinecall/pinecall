"""The replay endpoint: a finished call checked again by code alone."""

from fastapi import APIRouter

from runtime.calls import service as calls
from runtime.evals import schemas
from runtime.evals.auth import EvalsKey
from runtime.evals.service import replay
from runtime.postgres import Session

router = APIRouter()


# Another org's call and nobody's are one 404: neither is told apart from a typo.
@router.post("/v1/evals/replay/{call}")
async def replay_call(
    call: str, actor: EvalsKey, session: Session, body: schemas.ReplayCallRequest | None = None
) -> schemas.ReplayCallResponse:
    """The six code checks over a finished call, the barge-ins it answered among them."""
    wanted = body or schemas.ReplayCallRequest()
    read = await calls.read_for_key(session, actor, call)
    policy = replay.Policy(banned=tuple(wanted.banned), budget=wanted.budget)
    return schemas.ReplayCallResponse.of(replay.replay_call(read.entries, read.declaration, policy))
