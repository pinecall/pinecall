"""A group of cases diagnosed by the judge model: the cause its calls share, the change proposed, the fix applied."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.agents.settings import FIELDS, AgentSettings, dump_settings
from runtime.calls import service as calls
from runtime.enums import CaseStatus
from runtime.evals.parts import Harness
from runtime.evals.service import calibration
from runtime.evals.service.personas import Generated
from runtime.evals.service.writers import Brief, write_personas
from runtime.exceptions import Conflict, UpstreamError
from runtime.judging import service as judging
from runtime.judging.models import EvalCase
from runtime.kit.text import JsonObject
from runtime.providers import service as providers
from runtime.wire.base import Entry
from runtime.wire.metrics import LLMModelUsage
from runtime.wire.scores import CallScore

# A proposal is read by a person before anything changes: it says where, what, and how sure,
# and it never answers for the judge: a judge that was wrong is the person's to say.
DOCTOR = (
    "You diagnose why an AI phone or chat agent failed the same check on several calls. "
    "Read the check, what each call did wrong and the lines that show it, the agent's "
    "prompt, its settings and its tools. Name the one cause they share in one sentence. "
    "Then propose the smallest change that fixes it: a setting (name the setting and its "
    "new value), code (name the tool or the prompt block and what it must do instead), "
    "knowledge (what the agent must be told), or none when the calls show no fault of the "
    "agent's. Say how sure you are, 0 to 1. Then call the tool."
)
MOST_CHARS = 6000
# A diagnosis reads this many of a group's newest calls: enough to see what they share.
CALLS_READ = 5
KINDS = ("setting", "code", "knowledge", "none")

TOOL: JsonObject = {
    "name": "propose_fix",
    "description": "Hand in the diagnosis.",
    "parameters": {
        "type": "object",
        "properties": {
            "cause": {"type": "string", "description": "the cause the calls share, one sentence"},
            "kind": {"type": "string", "enum": list(KINDS)},
            "where": {
                "type": "string",
                "description": "the setting's name, the tool or prompt block, or the knowledge",
            },
            "change": {"description": "the setting's new value, or what the code or knowledge must say"},
            "confidence": {"type": "number", "description": "0 to 1"},
        },
        "required": ["cause", "kind", "where", "change", "confidence"],
    },
}


@dataclass(frozen=True, slots=True)
class Failure:
    """One call of the group: the reason its judge gave, and the lines it pointed at."""

    call: str
    reason: str
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Dossier:
    """What the doctor reads: the check that failed, the calls, the agent as it ran."""

    judge: str
    question: str
    failures: Sequence[Failure]
    prompt: str = ""
    settings: Mapping[str, object] | None = None
    tools: tuple[str, ...] = ()


async def diagnose(model: providers.Answerer, dossier: Dossier) -> tuple[JsonObject, LLMModelUsage | None]:
    """The group's cause and the change proposed, as its row keeps them; refused when the answer does not read."""
    fields, usage = await judging.force_tool(model, DOCTOR, _question_of(dossier), TOOL)
    cause, kind, where, sure = fields.get("cause"), fields.get("kind"), fields.get("where"), fields.get("confidence")
    if not isinstance(cause, str) or not isinstance(where, str):
        raise UpstreamError("the model handed in no diagnosis it could read: cause and where are sentences")
    if kind not in KINDS:
        raise UpstreamError(f"the model handed in no diagnosis it could read: kind is one of {', '.join(KINDS)}")
    if isinstance(sure, bool) or not isinstance(sure, int | float) or not 0.0 <= sure <= 1.0:
        raise UpstreamError("the model handed in no diagnosis it could read: confidence is a number from 0 to 1")
    return {"cause": cause, "kind": kind, "where": where, "change": fields.get("change"), "confidence": sure}, usage


# One request to the model the agent's calls are judged on: one eval, none on the org's own key.
async def propose_fix(parts: Harness, actor: Actor, found: judging.GroupCounted) -> judging.GroupCounted:
    """Diagnose the group: the cause its calls share, and the smallest change that fixes it."""
    group, scope = found.group, actor.scope
    async with parts.sessions.begin() as session_:
        dossier = await _dossier_of(session_, parts, scope, found)
        declaration = await agents.declaration_of(session_, scope, group.agent)
    run = judging.JudgeRun("propose", group.id, actor.env, evals=1)
    ask = partial(diagnose, dossier=dossier)
    log = parts.logs.agent(group.agent)
    proposal, _spent = await judging.ask_judge_model(parts.sessions, parts.vault, scope, declaration, run, ask, log)
    async with parts.sessions.begin() as session_:
        return await judging.propose_for_group(session_, actor.org, group.id, proposal)


# Written as a new version of the key's scope, checked as any set is; a person tries it with
# `pinecall test --case` before pushing it on.
async def apply_fix(parts: Harness, actor: Actor, found: judging.GroupCounted) -> agents.Shown[AgentSettings]:
    """Write the group's proposed setting into the agent's settings, noted with the group."""
    group, scope = found.group, actor.scope
    proposal = group.proposal
    if proposal is None:
        raise Conflict(f"group {group.id} has no proposal yet: `pinecall cases propose {group.id}` writes one first")
    kind, where = str(proposal.get("kind")), str(proposal.get("where"))
    if kind != "setting":
        raise Conflict(
            f"group {group.id} proposes {kind}, and only a setting is applied here: a code change goes to your "
            "assistant (`pinecall mcp`, the cases tool), knowledge to the agent's base"
        )
    if where not in FIELDS:
        raise Conflict(f"group {group.id} proposes changing {where}, which is not one of the agent's settings")
    async with parts.sessions.begin() as session_:
        kept = await agents.show_settings(session_, scope, group.agent)
    newest = kept.yours if scope.holder else kept.team
    current = {} if newest is None else dump_settings(newest.value)
    wanted = agents.parse_settings({**current, where: proposal.get("change")})
    written = agents.Written(
        author=actor.asked_by, note=f"case {group.id}", if_version=None if newest is None else newest.version
    )
    return await agents.put_settings(parts.sessions, parts.vault, actor, group.agent, wanted, written, team=False)


# A caller like the group's newest call's, kept as the agent's own; one eval to write it.
async def write_persona_from(parts: Harness, actor: Actor, found: judging.GroupCounted) -> Generated:
    """A persona written from the group's newest call, saved as the agent's own; 409 while its class declares them."""
    group, scope = found.group, actor.scope
    async with parts.sessions.begin() as session_:
        agent = await agents.agent_of(session_, scope, group.agent)
        agents.refuse_what_the_class_sets(agent, ("personas",))
        cases = await judging.list_cases(session_, actor.org, group.agent, group=group.id)
    made_from = [call for _, call in _list_from_calls(cases)]
    entries = await parts.store.whole_of(made_from[0]) if made_from else []
    brief = Brief(call=judging.conversation_of(judging.transcript_of(entries, None)), about=group.cause)
    run = judging.JudgeRun("generate", "personas", actor.env, evals=1)
    ask = partial(write_personas, brief=brief, n=1)
    log = parts.logs.agent(group.agent)
    written, spent = await judging.ask_judge_model(parts.sessions, parts.vault, scope, agent.declaration, run, ask, log)
    suffix = group.id.removeprefix(judging.A_GROUP)[:4]
    kept = [replace(one, tags=(*one.tags, "from-case"), name=f"{one.name}-{suffix}") for one in written]
    async with parts.sessions.begin() as session_:
        for persona in kept:
            await judging.put_persona(session_, actor.org, group.agent, persona, by=actor.asked_by, was=None)
    return Generated(kept, spent.evals, spent.judge_cost_usd or 0.0)


# The judge that was wrong is a calibration label of each call, in the call's own env. Each call is
# read as the key may read it and its judge checked before it is labelled: until 2026-11 a group
# dismissed this way labelled every call with neither check, and a sandbox key labelled production's.
async def decide_group(
    session_: AsyncSession,
    actor: Actor,
    found: judging.GroupCounted,
    *,
    status: CaseStatus,
    judge_was_wrong: bool,
    note: str | None,
) -> judging.GroupCounted:
    """Approve or dismiss the group and every case waiting in it; a judge called wrong is a label on each call."""
    group = found.group
    decided = await judging.decide_group(
        session_, actor.org, group.id, status=status, judge_was_wrong=judge_was_wrong, by=actor.asked_by
    )
    if judge_was_wrong:
        cases = await judging.list_cases(session_, actor.org, group.agent, group=group.id)
        for kept, call in _list_from_calls(cases):
            await _label_wrong(session_, actor, kept, call, group.judge, note)
    return decided


async def decide_case(session_: AsyncSession, actor: Actor, case: EvalCase, decision: judging.Decision) -> EvalCase:
    """Approve, dismiss, hold out or mark a case as kept; a judge called wrong is a label on the call it came from."""
    judging.check_decision(case, decision)
    # A judge called wrong broke on the case, so a call made it: the decision's check refused a person's case.
    if decision.judge_was_wrong is not None and case.source_call is not None:
        await _label_wrong(session_, actor, case, case.source_call, decision.judge_was_wrong, decision.note)
    return await judging.decide_case(session_, case, decision, by=actor.asked_by)


async def _label_wrong(
    session_: AsyncSession, actor: Actor, kept: EvalCase, call: str, judge: str, note: str | None
) -> None:
    await calls.get_readable(session_, calls.Reader(actor=actor), call)
    where = calibration.Where(org=actor.org, env=kept.source_env, agent=kept.agent)
    label = calibration.Label(call=call, judge=judge, held=True, author=actor.asked_by, note=note)
    await calibration.label_call(session_, where, label)


# A group holds what a judge broke on at hang-up, each kept from a call; a case a person wrote joins none.
def _list_from_calls(cases: Iterable[EvalCase]) -> Iterator[tuple[EvalCase, str]]:
    return ((kept, kept.source_call) for kept in cases if kept.source_call is not None)


async def _dossier_of(session_: AsyncSession, parts: Harness, scope: Scope, found: judging.GroupCounted) -> Dossier:
    group = found.group
    declaration = await agents.declaration_of(session_, scope, group.agent)
    class_judges = None if declaration is None else declaration.judges
    spec = await judging.judge_named(session_, scope.org, group.agent, group.judge, class_judges)
    cases = (await judging.list_cases(session_, scope.org, group.agent, group=group.id))[:CALLS_READ]
    failures: list[Failure] = []
    newest: list[Entry] = []
    for kept, call in _list_from_calls(cases):
        entries = await parts.store.whole_of(call)
        newest = newest or entries
        reason = next((str(broke.get("reason", "")) for broke in kept.broke if broke.get("judge") == group.judge), "")
        failures.append(Failure(call, reason, _lines_of(entries, group.judge)))
    tools = () if declaration is None else declaration.tools
    current = await agents.current_settings(session_, scope, group.agent)
    return Dossier(
        judge=group.judge,
        question=spec.question,
        failures=failures,
        prompt=await judging.prompt_of(session_, parts.prompts, scope.org, newest),
        settings=dump_settings(current.settings),
        tools=tuple(f"{tool.name}: {tool.description}" for tool in tools),
    )


# The lines the judge pointed at on its score, as the call said them.
def _lines_of(entries: Sequence[Entry], judge: str) -> tuple[str, ...]:
    scored = next((entry for entry in reversed(entries) if entry.type == "call.score"), None)
    if scored is None:
        return ()
    score = CallScore.model_validate(scored.data)
    cited = {seq for judgment in score.judges if judgment.name == judge for seq in judgment.evidence.seqs}
    return tuple(f"#{entry.seq} {entry.type}: {entry.data.get('text', '')}" for entry in entries if entry.seq in cited)


def _question_of(dossier: Dossier) -> str:
    blocks = [f"The check ({dossier.judge}): {dossier.question}"]
    for failure in dossier.failures:
        lines = "\n".join(f"  {line}" for line in failure.lines)
        blocks.append(f"Call {failure.call} failed it: {failure.reason}\n{lines}")
    if dossier.prompt:
        blocks.append(f"The agent's prompt:\n{dossier.prompt[:MOST_CHARS]}")
    if dossier.settings:
        settings = "\n".join(f"- {name}: {value}" for name, value in dossier.settings.items())
        blocks.append(f"The agent's settings:\n{settings}")
    if dossier.tools:
        blocks.append("The agent's tools:\n" + "\n".join(dossier.tools))
    return "\n\n".join(blocks)
