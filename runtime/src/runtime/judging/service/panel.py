"""The panel over a finished call: the judges it meets, what they are told, each gated and asked; the way to judge."""

import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.compliance import service as compliance
from runtime.enums import Direction, JudgeRunsWhen
from runtime.exceptions import PinecallError
from runtime.judging.service import asking, judges, library
from runtime.judging.service.asking import Answered, Context
from runtime.judging.service.evidence import as_text, evidence_of
from runtime.judging.service.judge_model import JudgeModel, Unjudged, judge_model_of, price_of
from runtime.judging.service.judges import RosterJudge
from runtime.judging.service.specs import JudgeSpec
from runtime.judging.service.transcript import Transcript, call_of, transcript_of
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject, sha256_of
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Running
from runtime.wire.base import Entry
from runtime.wire.metrics import LLMModelUsage
from runtime.wire.scores import CallScore, Judgment, JudgmentEvidence

logger = logging.getLogger(__name__)

OVER_THE_CEILING = "judging this call reached its ceiling of ${ceiling} before this judge asked"
OUT_OF_EVALS = "the org's evals for the month are used up: this judge was not asked"
NOTHING_ANSWERED = "every judge run over this call failed and not one of them answered"
NO_JUDGE_ON = "no judge is on for this agent: `pinecall judges` lists them, `pinecall judges on <name>` switches one on"
NOT_JUDGED = "judging this call failed: {broke}"


@dataclass(frozen=True, slots=True)
class Surroundings:
    """What is known of a call beyond its log, as the judges that read facts are told it."""

    org: str
    # The sentence outbound calls open with; None when the org and the platform set none.
    disclosure: str | None = None
    # A do-not-call fact was written with this call's id (call.opt_out).
    opted_out: bool = False


# Until 2026-11 the seal learnt that the org's evals ran out by comparing each judgment's reason to
# a sentence. The panel says it.
@dataclass(frozen=True, slots=True)
class Judged:
    """What the panel said of a call, and whether a judge went unasked because the org's evals ran out."""

    score: CallScore
    out_of_evals: bool = False


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why a judge of the panel was not asked, and whether it was the org's evals running out."""

    reason: str
    out_of_evals: bool = False


@dataclass(frozen=True, slots=True)
class Panel:
    """One call's panel as it is asked: the call as its judges read it, the judges it meets, and what they are told."""

    transcript: Transcript
    judges: tuple[RosterJudge, ...]
    context: Context
    catalog: Catalog


# The texts of a prompt's blocks are kept with the logs, which are `calls`', above this domain:
# whatever keeps them is handed in.
class PromptTexts(Protocol):
    """The texts of prompt blocks, by the hash the log names each with."""

    async def texts_of(self, session: AsyncSession, org: str, hashes: Collection[str]) -> Mapping[str, str]:
        """The text of each block the org kept, by its hash; one it never kept is left out."""
        ...


# The seal never fails on a judge: a call that could not be judged says why and seals all the same.
# What the panel reads is read in one transaction of its own, and the model is asked with no
# connection held. `only` asks one judge alone, as a judge is tried: the same path the seal takes.
async def judge_call(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    prompts: PromptTexts,
    entries: Sequence[Entry],
    declaration: Declaration | None,
    scope: Scope,
    *,
    only: JudgeSpec | None = None,
) -> Judged:
    """The panel over a finished call: the library's judges switched on, then the org's own; or one judge alone."""
    try:
        async with sessions.begin() as session:
            panel = await _read_panel(session, prompts, entries, declaration, scope, only)
            try:
                judge = await judge_model_of(session, vault, panel.catalog, scope, declaration)
            except Unjudged as none:
                return skip_unjudged(panel, entries, str(none))
        async with providers.open_answerer(judge.running) as model:
            return await ask_panel(panel, judge, entries, model)
    except PinecallError as broke:
        logger.warning("call %s: nothing judged it", call_of(entries), exc_info=True)
        return Judged(CallScore(judges=[], judge_calls=0, not_judged=NOT_JUDGED.format(broke=broke)))


def panel_of(roster: Sequence[RosterJudge], transcript: Transcript) -> tuple[RosterJudge, ...]:
    """The judges of the roster that are on, for this call: one that runs on simulations alone meets only those."""
    return tuple(
        judge
        for judge in roster
        if judge.on and (transcript.simulated or judge.spec.when is not JudgeRunsWhen.simulations)
    )


def gate_of(judge: RosterJudge, transcript: Transcript) -> str | None:
    """Why the judge does not apply to this call, said before any model is asked; None if it may."""
    match judge.gate:
        case "irreversible-tools" if not _ran_irreversible(transcript):
            return "no tool this agent declares irreversible ran on this call"
        case "outbound" if transcript.direction is not Direction.outbound:
            return "the call came in: only an outbound call names who it calls for"
        case "expectations" if not transcript.expects:
            return "the simulated caller expected nothing of the agent"
        case _:
            return None


# The gate, then the question: what a golden that names a judge of the panel asks too.
async def ask_judge(
    judge: RosterJudge, transcript: Transcript, context: Context, model: providers.Answerer
) -> Answered:
    """One judge of a roster asked of one call: N/A where its gate says so, else its answer."""
    gate = gate_of(judge, transcript)
    if gate is not None:
        return Answered("na", gate)
    return await asking.ask(judge.spec, transcript, context, model)


def context_of(transcript: Transcript, around: Surroundings, prompt: str) -> Context:
    """What the judges of a call may read beyond the conversation."""
    return Context(prompt=prompt, evidence=as_text(evidence_of(transcript)), facts=facts_of(transcript, around))


def facts_of(transcript: Transcript, around: Surroundings) -> str:
    """The facts a judge that reads them is told, one line each."""
    direction = "unknown" if transcript.direction is None else transcript.direction.value
    lines = [f"- organisation: {around.org}", f"- direction: {direction}"]
    irreversible = sorted(name for name, effect in _effects_of(transcript).items() if effect == "irreversible")
    lines.append(f"- irreversible tools: {', '.join(irreversible) or 'none'}")
    lines += [
        f"- #{line.seq} {line.kind} {line.tool}" + (f" ({line.audience})" if line.audience else "")
        for line in transcript.gate
        if line.kind != "tool.call"
    ]
    lines.append(f"- an opt-out was written on this call: {'yes' if around.opted_out else 'no'}")
    if around.disclosure:
        lines.append(f'- the disclosure sentence outbound calls open with: "{around.disclosure}"')
    summary = transcript.summary or {}
    if summary.get("end_reason"):
        lines.append(f"- the call ended: {summary.get('end_reason')}, by {summary.get('ended_by')}")
    if transcript.expects:
        lines += ["- the simulated caller expected:"]
        lines += [f"  - {line}" for line in transcript.expects]
    return "\n".join(lines)


# The org as the call spoke for it: its name, the opening sentence it set, and an opt-out it took.
async def surroundings_of(session: AsyncSession, org: str, call: str, declaration: Declaration | None) -> Surroundings:
    """What the judges that read facts are told beyond the call's log."""
    found = await accounts.find_org(session, org)
    name = org if found is None else found.name
    policy = await compliance.policy_of(session, org)
    language = None if declaration is None else declaration.language
    return Surroundings(
        org=name,
        disclosure=policy.disclosure_for(name, language),
        opted_out=await compliance.has_opt_out_on(session, call),
    )


# Each block's last text, as the call's last turn was told it; a block the org never kept is
# left out rather than guessed.
async def prompt_of(session: AsyncSession, prompts: PromptTexts, org: str, entries: Sequence[Entry]) -> str:
    """The prompt the call ran on, block by block, for a judge that reads the agent's prompt."""
    latest: dict[str, str] = {}
    for entry in entries:
        if entry.type == "prompt.changed":
            latest[str(entry.data["name"])] = str(entry.data["hash"])
    texts = await prompts.texts_of(session, org, set(latest.values()))
    return "\n\n".join(f"## {name}\n{texts[kept]}" for name, kept in latest.items() if kept in texts)


def evidence_at(positions: Sequence[int], entries: Sequence[Entry]) -> JudgmentEvidence:
    """The log positions an answer rests on that the log has, and the first words said at one."""
    by_seq = {entry.seq: entry for entry in entries}
    seqs = [seq for seq in positions if seq in by_seq]
    words = (by_seq[seq].data.get("text") for seq in seqs)
    spoken = next((text for text in words if isinstance(text, str) and text), None)
    return JudgmentEvidence(seqs=seqs, said=spoken) if spoken else JudgmentEvidence(seqs=seqs)


# ── private ──


async def _read_panel(
    session: AsyncSession,
    prompts: PromptTexts,
    entries: Sequence[Entry],
    declaration: Declaration | None,
    scope: Scope,
    only: JudgeSpec | None,
) -> Panel:
    transcript = transcript_of(entries, declaration)
    if only is None:
        class_judges = None if declaration is None else declaration.judges
        roster = await judges.roster_of(session, scope.org, transcript.agent, class_judges)
    else:
        roster = alone(only)
    around = await surroundings_of(session, scope.org, transcript.call, declaration)
    context = context_of(transcript, around, await prompt_of(session, prompts, scope.org, entries))
    return Panel(transcript, panel_of(roster, transcript), context, await providers.get_catalog(session))


# A question written under a library judge's name is asked as written, without the library's gate.
def alone(spec: JudgeSpec) -> tuple[RosterJudge, ...]:
    """The roster of one judge asked alone: Pinecall's, gate and all, when the question is its own; else the org's."""
    found = library.library_judges().get(spec.name)
    if found is not None and found.spec == spec:
        return (RosterJudge(spec, owner=judges.PINECALL, on=True, gate=found.gate, version=found.version),)
    return (RosterJudge(spec, owner=judges.THE_ORG, on=True),)


# With no judge model, a judge is settled by its gate or skipped, saying why there is none.
def skip_unjudged(panel: Panel, entries: Sequence[Entry], why: str) -> Judged:
    """The score of a call no model may judge: each judge settled by its gate, or skipped saying why."""
    judged: list[Judgment] = []
    for judge in panel.judges:
        gate = gate_of(judge, panel.transcript)
        answered = Answered("skipped", why) if gate is None else Answered("na", gate)
        judged.append(_judgment(judge, answered, entries))
    return Judged(_score_of(judged, panel.judges, (0, 0), 0.0, None))


# Each judge in the panel's order: settled by its gate, else held to the ceiling and the evals, else
# asked. A judge whose model fails is skipped, saying so, and the others are still asked.
async def ask_panel(panel: Panel, judge: JudgeModel, entries: Sequence[Entry], model: providers.Answerer) -> Judged:
    """The score of a call: each judge of its panel settled by its gate, held to the ceiling and the evals, or asked."""
    judged: list[Judgment] = []
    spent: list[LLMModelUsage] = []
    evals = 0
    out_of_evals = False
    for member in panel.judges:
        gate = gate_of(member, panel.transcript)
        refusal = _refusal_of(judge, price_of(spent, judge.running, panel.catalog), evals)
        if gate is not None:
            answered = Answered("na", gate)
        elif refusal is not None:
            answered = Answered("skipped", refusal.reason)
            out_of_evals = out_of_evals or refusal.out_of_evals
        else:
            answered = await _ask_and_survive(member, panel, model)
            spent += answered.spent
            evals += int(answered.is_an_eval)
        judged.append(_judgment(member, answered, entries))
    cost = price_of(spent, judge.running, panel.catalog)
    return Judged(_score_of(judged, panel.judges, (evals, len(spent)), cost, judge.running), out_of_evals)


# The evals are spent in panel order: the library's first, so the org's own are the ones skipped.
def _refusal_of(judge: JudgeModel, spent_usd: float, evals: int) -> Refusal | None:
    if spent_usd >= judge.ceiling_usd:
        return Refusal(OVER_THE_CEILING.format(ceiling=judge.ceiling_usd))
    if judge.evals_left is not None and evals >= judge.evals_left:
        return Refusal(OUT_OF_EVALS, out_of_evals=True)
    return None


# The vendor's no and its silence reach here as our errors (`providers.Answerer`), as does a judge
# model that answered without its tool, or whose arguments a vendor cut short.
async def _ask_and_survive(judge: RosterJudge, panel: Panel, model: providers.Answerer) -> Answered:
    try:
        return await asking.ask(judge.spec, panel.transcript, panel.context, model)
    except PinecallError as failed:
        logger.warning("judge %s failed; the call is sealed without it", judge.spec.name, exc_info=True)
        return Answered("skipped", f"the judge model failed: {failed}")


def _judgment(judge: RosterJudge, answered: Answered, entries: Sequence[Entry]) -> Judgment:
    return Judgment(
        name=judge.spec.name,
        verdict=answered.verdict,
        criteria=judge.spec.question,
        reason=answered.reason,
        evidence=evidence_at(answered.positions, entries),
        choice=answered.choice,
        score=answered.score,
    )


# `counted` is the evals billed and the model calls made, the trigger questions among them.
def _score_of(
    judged: Sequence[Judgment],
    panel: Sequence[RosterJudge],
    counted: tuple[int, int],
    cost_usd: float,
    running: Running | None,
) -> CallScore:
    evals, calls = counted
    settled = [judgment for judgment in judged if judgment.verdict in {"held", "broken"}]
    answered = [judgment for judgment in judged if judgment.verdict not in {"skipped", "deferred"}]
    scored: JsonObject = {
        "judges": [judgment.dump() for judgment in judged],
        "panel": [judge.spec.name for judge in panel],
        "judge_calls": calls,
        "evals": evals,
    }
    if running is not None and not running.lent:
        scored["own_key"] = True
    if settled:
        scored["passed"] = not any(judgment.verdict == "broken" for judgment in settled)
    elif not panel:
        scored["not_judged"] = NO_JUDGE_ON
    elif not answered:
        scored["not_judged"] = NOTHING_ANSWERED if running is not None else _why_not(judged)
    if cost_usd:
        scored["judge_cost_usd"] = cost_usd
    if judged:
        scored["judged_by"] = _name_who_judged(judged, running)
    return CallScore.model_validate(scored)


def _why_not(judged: Sequence[Judgment]) -> str:
    return next((judgment.reason for judgment in judged if judgment.reason), NOTHING_ANSWERED)


# The panel's questions in its order: the same questions hash the same, whatever the call said.
def _name_who_judged(judged: Sequence[Judgment], running: Running | None) -> JsonObject:
    questions = "\n".join(f"{judgment.name}\n{judgment.criteria}" for judgment in judged)
    return {
        "provider": None if running is None else running.vendor,
        "model": None if running is None else running.model,
        "criteria": sha256_of(questions),
    }


def _ran_irreversible(transcript: Transcript) -> bool:
    return any(line.kind == "tool.call" and line.side_effect == "irreversible" for line in transcript.gate)


def _effects_of(transcript: Transcript) -> dict[str, str]:
    if transcript.declaration is None:
        return {}
    return {name: spec.side_effect for name, spec in transcript.declaration.tools_by_name.items()}
