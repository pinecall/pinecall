"""The org's hang-up judging: on or off, and on what model."""

from fastapi import APIRouter

from runtime.handles import TheSessions, TheVault
from runtime.judging import schemas
from runtime.judging.auth import CallsKey, UsageKey
from runtime.judging.service import judge_model
from runtime.postgres import Session

router = APIRouter()


# Per org, not per env: an org's evals are counted across both.
@router.get("/v1/org/judging")
async def get_judging(actor: CallsKey, session: Session) -> schemas.JudgingSettings:
    """Whether hang-up judging is on, the model it runs on, and its ceiling per call."""
    return schemas.JudgingSettings.of(await judge_model.judging_of(session, actor.org))


# The use case opens its own transactions: none is held while a vendor is tried.
@router.put("/v1/org/judging")
async def put_judging(
    body: schemas.JudgingRequest, actor: UsageKey, sessions: TheSessions, vault: TheVault
) -> schemas.JudgingSettings:
    """Hang-up judging on or off, and the model it runs on, from the next call."""
    judging = await judge_model.put_judging(sessions, vault, actor.org, on=body.on, model=body.model)
    return schemas.JudgingSettings.of(judging)
