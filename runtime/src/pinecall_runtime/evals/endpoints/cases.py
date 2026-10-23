"""The dataset endpoints: a call kept as a case or read as a golden, one written by hand, the inbox, a case decided."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.agents.auth import KnownAgent, KnownFilter
from pinecall_runtime.calls.auth import Reader, TheServing, check_readable
from pinecall_runtime.enums import CaseStatus
from pinecall_runtime.evals import schemas
from pinecall_runtime.evals.auth import EvalsKey
from pinecall_runtime.evals.endpoints.reading import asked_by, finished
from pinecall_runtime.judging import schemas as judged
from pinecall_runtime.judging import service as judging
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.goldens import Expect, Golden
from pinecall_runtime.wire.scores import CallScore

router = APIRouter()


# The case is the org's, played in the sandbox whichever env its call ran in; the key must be
# one that reads the call, as a replay's does. An expect left empty is the one the call's broken
# verdicts give.
@router.post("/v1/evals/cases", response_model_exclude_unset=True)
async def promote_case(
    body: judged.PromoteCaseRequest, actor: EvalsKey, serving: TheServing, session: Session
) -> judged.CaseRow:
    """A finished call's caller lines kept as a case of the org's dataset."""
    entries, agent, env, version = await finished(session, serving, actor, body.call)
    score = _score_in(entries)
    expect = body.expect
    if expect == Expect() and score is not None:
        expect = judging.expect_of(score.judges, entries)
    golden = judging.golden_of(entries, body.name, expect)
    promoting = judging.Promoted(
        org=actor.org,
        env=env,
        name=body.name,
        author=asked_by(actor),
        held_out=body.held_out,
        broke=[] if score is None else judging.broke_of(score),
        source_version=version,
    )
    return await judging.promote_case(session, golden, agent, promoting)


# Written in the key's env, as a kept call is in its call's; played in the sandbox like every case.
@router.put("/v1/agents/{slug}/cases/{name}", response_model_exclude_unset=True)
async def write_case(
    slug: KnownAgent,
    name: Annotated[str, Path(min_length=1)],
    body: judged.WriteCaseRequest,
    actor: EvalsKey,
    session: Session,
) -> judged.CaseRow:
    """Write a golden as a case of the agent, by hand; their own name again rewrites it."""
    keys.check_agent(actor, slug)
    writing = judging.Promoted(org=actor.org, env=actor.env, name=name, author=asked_by(actor), held_out=body.held_out)
    return await judging.write_case(session, body.golden, slug, writing)


# What `pinecall runs promote` writes to the agent's test/candidates: the same golden a case would hold,
# derived here once, kept nowhere.
@router.get("/v1/calls/{call}/golden", response_model_exclude_unset=True)
async def golden_of_call(
    call: Annotated[str, Path()],
    actor: EvalsKey,
    serving: TheServing,
    session: Session,
    query: Annotated[schemas.GoldenQuery, Query()],
) -> Golden:
    """The golden a finished call makes from a seq on, its expect from its broken verdicts."""
    entries, _, _, _ = await finished(session, serving, actor, call)
    score = _score_in(entries)
    expect = Expect() if score is None else judging.expect_of(score.judges, entries)
    cut = judging.cut_at(entries, query.from_seq)
    return judging.golden_of(cut, query.name or call, expect)


@router.get("/v1/evals/cases", response_model_exclude_unset=True)
async def list_cases(
    actor: EvalsKey,
    session: Session,
    agent: KnownFilter,
    status: Annotated[CaseStatus | None, Query()] = None,
) -> judged.CaseList:
    """The org's cases, one agent's or every one, the pending first; how many wait, of how many."""
    if agent is not None:
        keys.check_agent(actor, agent)
    return judged.CaseList(
        cases=await judging.list_cases(session, actor.org, agent, status),
        pending=await judging.waiting_cases(session, actor.org, agent),
        pending_at_most=judging.PENDING_AT_MOST,
    )


# The judge called wrong is a calibration label in the call's own env, so the key must read the
# call as the calibration endpoint's does.
@router.patch("/v1/evals/cases/{id}", response_model_exclude_unset=True)
async def decide_case(
    case: Annotated[str, Path(alias="id")],
    body: judged.CaseDecision,
    actor: EvalsKey,
    serving: TheServing,
    session: Session,
) -> judged.CaseRow:
    """Approve, dismiss, hold out or mark a case as kept in the repository."""
    kept = await judging.get_case(session, actor.org, case)
    keys.check_agent(actor, kept.agent)
    judging.check_decision(kept, body)
    author = asked_by(actor)
    if body.judge_was_wrong is not None:
        await check_readable(session, serving, Reader(actor=actor), kept.source_call)
        where = judging.Where(org=actor.org, env=kept.source_env, agent=kept.agent)
        label = judging.Label(
            call=kept.source_call, judge=body.judge_was_wrong, held=True, author=author, note=body.note
        )
        await judging.label_call(session, where, label)
    return await judging.decide_case(session, actor.org, case, body, by=author)


@router.delete("/v1/evals/cases/{id}", status_code=204)
async def delete_case(case: Annotated[str, Path(alias="id")], actor: EvalsKey, session: Session) -> None:
    """Forget one of the org's cases; another org's, or nobody's, is the same 404."""
    await judging.delete_case(session, actor.org, case)


def _score_in(entries: list[Entry]) -> CallScore | None:
    """The call's last call.score, the verdict a judge may write again after the seal."""
    found = [entry for entry in entries if entry.type == "call.score"]
    return None if not found else CallScore.model_validate(found[-1].data)
