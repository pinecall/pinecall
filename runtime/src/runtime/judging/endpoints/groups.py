"""The case group endpoints: what broke an agent, and every case of one group."""

from fastapi import APIRouter

from runtime.agents import schemas as agents
from runtime.agents.auth import KnownFilter
from runtime.evals.auth import TheHarness
from runtime.evals.service import diagnoses
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey, TheGroup, TheGroupToApply, WordsKey
from runtime.judging.service import GroupCounted, cases, groups
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/evals/groups")
async def list_groups(actor: EvalsKey, session: Session, agent: KnownFilter) -> schemas.GroupList:
    """The org's case groups, one agent's or every one, the pending first and newest first."""
    found = await groups.list_groups(session, actor.org, agent)
    rows = [schemas.GroupRow.of_counted(one.group, cases=one.cases, simulations=one.simulations) for one in found]
    return schemas.GroupList(groups=rows)


@router.get("/v1/evals/groups/{id}")
async def get_group(found: TheGroup, actor: EvalsKey, session: Session) -> schemas.GroupWhole:
    """One group and every case in it."""
    group = schemas.GroupRow.of_counted(found.group, cases=found.cases, simulations=found.simulations)
    kept = await cases.list_cases(session, actor.org, group.agent, group=group.id)
    return schemas.GroupWhole(group=group, cases=[schemas.CaseRow.of(case) for case in kept])


# The four below are evals' use cases: each reads the group's calls, which stand above this domain.


# One request to the model the agent's calls are judged on: one eval, none on the org's own key.
@router.post("/v1/evals/groups/{id}/propose")
async def propose(found: TheGroup, actor: EvalsKey, parts: TheHarness) -> schemas.GroupRow:
    """Diagnose the group: the cause its calls share, and the smallest change that fixes it."""
    return _row(await diagnoses.propose_fix(parts, actor, found))


# Written as a new version of the key's scope, checked as any set is; a person tries it with
# `pinecall test --case` before pushing it on.
@router.post("/v1/evals/groups/{id}/apply", response_model_exclude_unset=True)
async def apply(found: TheGroupToApply, actor: WordsKey, parts: TheHarness) -> agents.SettingsResponse:
    """Write the group's proposed setting into the agent's settings, noted with the group."""
    return agents.SettingsResponse.of(await diagnoses.apply_fix(parts, actor, found))


# A caller like the group's newest call's, kept as the agent's own; one eval to write it.
@router.post("/v1/evals/groups/{id}/persona")
async def persona_from(found: TheGroup, actor: EvalsKey, parts: TheHarness) -> schemas.GeneratedPersonas:
    """A persona written from the group's newest call, saved as the agent's own; 409 while its class declares them."""
    made = await diagnoses.write_persona_from(parts, actor, found)
    return schemas.GeneratedPersonas.of_written(made.personas, evals=made.evals, cost_usd=made.cost_usd)


# The judge that was wrong is a calibration label of each call, in the call's own env.
@router.patch("/v1/evals/groups/{id}")
async def decide_group(
    found: TheGroup, body: schemas.GroupDecision, actor: EvalsKey, session: Session
) -> schemas.GroupRow:
    """Approve or dismiss the group and every case waiting in it."""
    decided = await diagnoses.decide_group(
        session, actor, found, status=body.status, judge_was_wrong=body.judge_was_wrong, note=body.note
    )
    return _row(decided)


def _row(found: GroupCounted) -> schemas.GroupRow:
    return schemas.GroupRow.of_counted(found.group, cases=found.cases, simulations=found.simulations)
