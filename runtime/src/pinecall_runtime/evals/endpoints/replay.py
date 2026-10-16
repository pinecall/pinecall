"""A finished call checked again: the six code checks, or the hang-up panel asked later."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.evals import schemas, service
from pinecall_runtime.evals.auth import EvalsKey
from pinecall_runtime.evals.endpoints.reading import is_over, readable
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.scores import CallScore

router = APIRouter()

STILL_GOING = "call {call} is still going: it is judged when it hangs up"
ALREADY_JUDGED = "call {call} was judged at hang-up: ?again=true judges it again, and pays for it again"


# Another org's call and nobody's are one 404: neither is told apart from a typo.
@router.post("/v1/evals/replay/{call}")
async def replay_call(
    call: str,
    actor: EvalsKey,
    serving: TheServing,
    session: Session,
    body: schemas.ReplayCallRequest | None = None,
) -> schemas.ReplayCallResponse:
    """The six code checks over a finished call, the barge-ins it answered among them."""
    entries, declared = await readable(session, serving, actor, call)
    wanted = body or schemas.ReplayCallRequest()
    verdicts = service.replay(
        entries, banned=wanted.banned, budget=wanted.budget, irreversible=service.irreversible_tools(declared)
    )
    return schemas.ReplayCallResponse(
        call=call,
        agent=entries[0].agent,
        passed=not any(verdict.status == "broken" for verdict in verdicts),
        verdicts=verdicts,
    )


# Hang-up judging run later: the org judged nothing then, the judge failed, or a judge again.
@router.post("/v1/evals/judge/{call}", response_model_exclude_unset=True)
async def judge_call(
    call: str, actor: EvalsKey, serving: TheServing, session: Session, query: Annotated[schemas.JudgeQuery, Query()]
) -> CallScore:
    """Judge a finished call, write the verdict on its log, and answer it."""
    entries, declared = await readable(session, serving, actor, call)
    if not is_over(entries):
        raise Conflict(STILL_GOING.format(call=call))
    if not query.again and any(
        entry.type == "call.score" and entry.data.get("passed") is not None for entry in entries
    ):
        raise Conflict(ALREADY_JUDGED.format(call=call))
    panel = await calls.panel_for(session, actor.org, entries, declared)
    score = await calls.judge_call(session, serving, entries, declared, panel, actor.scope)
    await serving.logs.store.rescore(call, entries[0].agent, score.dump())
    await calls.drift_folded(session, call, entries, score)
    return score
