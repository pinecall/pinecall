"""The case group endpoints: what broke an agent, its diagnosis, the fix applied, a persona from it."""

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Path, Query

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.agents import schemas as agents
from pinecall_runtime.agents.service import settings
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.enums import CaseStatus
from pinecall_runtime.evals.auth import EvalsKey, WordsKey
from pinecall_runtime.evals.endpoints.reading import asked_by
from pinecall_runtime.exceptions import Conflict, ServiceUnavailable, ValidationError
from pinecall_runtime.judging import schemas as judged
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.kit.time import epoch
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.metrics import LLMModelUsage
from pinecall_runtime.wire.scores import CallScore, EvalsSpent

router = APIRouter()

# A diagnosis reads this many of a group's newest calls: enough to see what they share.
CALLS_READ = 5
NOT_A_SETTING = (
    "group {id} proposes {kind}, and only a setting is applied here: a code change goes to your "
    "assistant (`pinecall mcp`, the cases tool), knowledge to the agent's base"
)
NO_SUCH_SETTING = "group {id} proposes changing {where}, which is not one of the agent's settings"
NOT_DIAGNOSED = "group {id} has no proposal yet: POST /v1/evals/groups/{id}/propose first"
WRONG_ONLY_WHEN_DISMISSED = (
    "judge_was_wrong says the group's judge broke where it should have held, so it dismisses the "
    "group: send it with status dismissed"
)


@router.get("/v1/evals/groups")
async def list_groups(
    actor: EvalsKey, session: Session, agent: Annotated[str | None, Query()] = None
) -> judged.GroupList:
    """The org's case groups, one agent's or every one, the pending first and newest first."""
    return judged.GroupList(groups=await judging.list_groups(session, actor.org, agent))


@router.get("/v1/evals/groups/{id}")
async def get_group(group: Annotated[str, Path(alias="id")], actor: EvalsKey, session: Session) -> judged.GroupWhole:
    """One group and every case in it."""
    found = await judging.get_group(session, actor.org, group)
    keys.check_agent(actor, found.agent)
    cases = await judging.list_cases(session, actor.org, found.agent, group=found.id)
    return judged.GroupWhole(group=found, cases=cases)


# One request to the model the agent's calls are judged on: one eval, none on the org's own key.
@router.post("/v1/evals/groups/{id}/propose")
async def propose(
    group: Annotated[str, Path(alias="id")], actor: EvalsKey, serving: TheServing, session: Session
) -> judged.GroupRow:
    """Diagnose the group: the cause its calls share, and the smallest change that fixes it."""
    found = await judging.get_group(session, actor.org, group)
    keys.check_agent(actor, found.agent)
    judge, configured = await _judge_for(session, serving, actor.scope, found.agent)
    dossier = await _dossier_of(session, serving, actor.scope, found)
    running = judge.running
    if running is None:
        raise ServiceUnavailable(judge.unjudged)
    model = providers.llm_of(running)
    try:
        proposal, usage = await judging.diagnose(model, dossier)
    finally:
        await model.aclose()
    run = judging.JudgeRun("propose", found.id, actor.env, evals=1)
    await _spent(serving, found.agent, run, running, configured, usage)
    await judging.propose_for_group(session, actor.org, found.id, proposal.model_dump(mode="json"))
    return await judging.get_group(session, actor.org, found.id)


# Written as a new version of the key's scope, checked as any set is; a person tries it with
# `pinecall test --case` before pushing it on.
@router.post("/v1/evals/groups/{id}/apply", response_model_exclude_unset=True)
async def apply(
    group: Annotated[str, Path(alias="id")], actor: WordsKey, serving: TheServing, handles: TheHandles, session: Session
) -> agents.SettingsResponse:
    """Write the group's proposed setting into the agent's settings, noted with the group."""
    scope = actor.scope
    found = await judging.get_group(session, actor.org, group)
    keys.check_agent(actor, found.agent)
    if found.proposal is None:
        raise Conflict(NOT_DIAGNOSED.format(id=found.id))
    proposal = found.proposal
    if proposal.kind != "setting":
        raise Conflict(NOT_A_SETTING.format(id=found.id, kind=proposal.kind))
    if proposal.where not in settings.TUNING_KNOBS:
        raise Conflict(NO_SUCH_SETTING.format(id=found.id, where=proposal.where))
    kept = await settings.tuning_side_by_side(session, scope, found.agent)
    newest = kept.team if scope.holder == THE_ORGS_OWN else kept.yours
    current = {} if newest is None else settings.dump_tuning(newest.value)
    wanted = settings.parse_tuning({**current, proposal.where: proposal.change})
    written = settings.Written(
        author=asked_by(actor), note=f"case {found.id}", if_version=None if newest is None else newest.version
    )
    await settings.write_tuning(
        session,
        scope,
        found.agent,
        wanted,
        written,
        actor=actor,
        declared=serving.registry.declared(found.agent),
        vault_keyring=await providers.keys_of(session, handles.vault, scope),
    )
    declared = serving.registry.declared(found.agent)
    return await settings.settings_response(
        session, scope, found.agent, fixed=() if declared is None else declared.fixed
    )


# A caller like the group's newest call's, kept as the agent's own; one eval to write it.
@router.post("/v1/evals/groups/{id}/persona")
async def persona_from(
    group: Annotated[str, Path(alias="id")], actor: EvalsKey, serving: TheServing, session: Session
) -> judged.GeneratedPersonas:
    """A persona written from the group's newest call, saved as the agent's own."""
    found = await judging.get_group(session, actor.org, group)
    keys.check_agent(actor, found.agent)
    judge, configured = await _judge_for(session, serving, actor.scope, found.agent)
    running = judge.running
    if running is None:
        raise ServiceUnavailable(judge.unjudged)
    cases = await judging.list_cases(session, actor.org, found.agent, group=found.id)
    entries = await serving.logs.store.whole(cases[0].source_call) if cases else []
    brief = judging.Brief(call=judging.conversation_of(judging.case_of(entries, None)), about=found.cause)
    model = providers.llm_of(running)
    try:
        written, usage = await judging.write_personas(model, brief, 1)
    finally:
        await model.aclose()
    run = judging.JudgeRun("generate", "personas", actor.env, evals=1)
    spent = await _spent(serving, found.agent, run, running, configured, usage)
    kept = [replace(persona, tags=(*persona.tags, "from-case"), name=_free(persona, found)) for persona in written]
    for persona in kept:
        await judging.put_persona(session, actor.org, found.agent, persona, by=actor.key_id, was=None)
    return judged.GeneratedPersonas(
        personas=[judging.proposed_row(persona) for persona in kept],
        evals=spent.evals,
        cost_usd=spent.judge_cost_usd or 0.0,
    )


# The judge that was wrong is a calibration label of each call, in the call's own env.
@router.patch("/v1/evals/groups/{id}")
async def decide_group(
    group: Annotated[str, Path(alias="id")], body: judged.GroupDecision, actor: EvalsKey, session: Session
) -> judged.GroupRow:
    """Approve or dismiss the group and every case waiting in it."""
    found = await judging.get_group(session, actor.org, group)
    keys.check_agent(actor, found.agent)
    if body.judge_was_wrong and body.status is not CaseStatus.dismissed:
        raise ValidationError(WRONG_ONLY_WHEN_DISMISSED)
    author = asked_by(actor)
    if body.judge_was_wrong:
        for kept in await judging.list_cases(session, actor.org, found.agent, group=found.id):
            where = judging.Where(org=actor.org, env=kept.source_env, agent=kept.agent)
            label = judging.Label(call=kept.source_call, judge=found.judge, held=True, author=author, note=body.note)
            await judging.label_call(session, where, label)
    await judging.decide_group(session, actor.org, found.id, status=body.status, by=author)
    return await judging.get_group(session, actor.org, found.id)


async def _judge_for(
    session: Session, serving: calls.Serving, scope: Scope, agent: str
) -> tuple[judging.JudgeModel, providers.Catalog]:
    registration = serving.registry.serving(scope, agent, None)
    declared = None if registration is None else registration.config
    configured = await providers.get_catalog(session)
    judge = await calls.judge_of(session, serving, configured, scope, declared)
    if judge.running is not None and judge.running.lent:
        await billing.admit_evals(session, scope.org, scope.env, at=epoch())
    return judge, configured


async def _dossier_of(
    session: Session, serving: calls.Serving, scope: Scope, found: judged.GroupRow
) -> judging.Dossier:
    spec = await judging.judge_named(session, scope.org, found.agent, found.judge)
    cases = (await judging.list_cases(session, scope.org, found.agent, group=found.id))[:CALLS_READ]
    failures: list[judging.Failure] = []
    newest: list[Entry] = []
    for kept in cases:
        entries = await serving.logs.store.whole(kept.source_call)
        newest = newest or entries
        reason = next((broke.reason for broke in kept.broke if broke.judge == found.judge), "")
        failures.append(judging.Failure(kept.source_call, reason, _lines_of(entries, found.judge)))
    registration = serving.registry.serving(scope, found.agent, None)
    tools = () if registration is None else registration.config.tools
    tuned = (await settings.current_settings(session, scope, found.agent)).tuning
    return judging.Dossier(
        judge=found.judge,
        question=spec.question,
        failures=failures,
        prompt=await calls.prompt_of(session, scope.org, newest),
        settings=settings.dump_tuning(tuned),
        tools=tuple(f"{tool.name}: {tool.description}" for tool in tools),
    )


# One request, one eval: none on the org's own key, where the model is the org's to pay.
async def _spent(
    serving: calls.Serving,
    agent: str,
    run: judging.JudgeRun,
    running: providers.Running,
    configured: providers.Catalog,
    usage: LLMModelUsage | None,
) -> EvalsSpent:
    spent = judging.judge_spend(run, running, configured, usage)
    await serving.logs.agent(agent).append("evals.spent", spent.dump())
    return spent


# The lines the judge pointed at on its score, as the call said them.
def _lines_of(entries: list[Entry], judge: str) -> tuple[str, ...]:
    scored = next((entry for entry in reversed(entries) if entry.type == "call.score"), None)
    if scored is None:
        return ()
    score = CallScore.model_validate(scored.data)
    cited = {seq for judgment in score.judges if judgment.name == judge for seq in judgment.evidence.seqs}
    return tuple(f"#{entry.seq} {entry.type}: {entry.data.get('text', '')}" for entry in entries if entry.seq in cited)


def _free(persona: judging.Persona, found: judged.GroupRow) -> str:
    return f"{persona.name}-{found.id.removeprefix(judging.A_GROUP)[:4]}"
