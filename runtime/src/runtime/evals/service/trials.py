"""A judge asked again of finished calls: one tried without being kept, and a call's panel run after its hang-up."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.calls import service as calls
from runtime.enums import JudgeRunsWhen
from runtime.evals.parts import Harness
from runtime.evals.service.turns import is_call_over
from runtime.exceptions import Conflict, ValidationError
from runtime.insights import service as insights
from runtime.judging import service as judging
from runtime.wire.base import Entry
from runtime.wire.scores import CallScore, EvalsSpent, Judgment

NOT_FINISHED = "the call has not finished"
ON_SIMULATIONS = "{name} runs on calls a simulated caller played, and a person made this one"


@dataclass(frozen=True, slots=True)
class Tried:
    """What the judge answered of one call, or why it did not."""

    call: str
    judgment: Judgment | None
    not_judged: str | None = None


@dataclass(frozen=True, slots=True)
class Trial:
    """The judge's answer on every call it was tried on, the evals spent and what they cost."""

    rows: list[Tried]
    evals: int
    cost_usd: float


# Asked as the seal asks it, on the model the seal would judge the call on, and written on no log but
# the agent's, which keeps what the try spent. `written` is a judge said whole in the request; None
# is one of the agent's roster by its name.
async def try_judge(
    parts: Harness,
    actor: Actor,
    slug: str,
    name: str,
    written: judging.JudgeWanted | None,
    *,
    last: int | None,
    named: Sequence[str],
) -> Trial:
    """Ask one judge, kept or only said, of finished calls of the agent."""
    if last is not None and named:
        raise ValidationError("a try names the agent's last calls or the calls themselves, never both")
    async with parts.sessions.begin() as session_:
        if written is not None:
            spec = judging.spec_of(name, written)
        else:
            declaration = await agents.declaration_of(session_, actor.scope, slug)
            class_judges = None if declaration is None else declaration.judges
            spec = await judging.judge_named(session_, actor.org, slug, name, class_judges)
        if not named:
            if last is None:
                raise ValidationError("a try names the agent's last calls (last) or the calls themselves (calls)")
            named = await calls.list_newest_sealed(session_, actor.scope, slug, last)
    tried = [await _try_on(parts, actor, call, spec) for call in named]
    scores = [score for _, score in tried]
    spent = EvalsSpent(
        kind="try",
        name=spec.name,
        env=actor.env,
        calls=list(named),
        evals=sum(score.evals for score in scores),
        judge_calls=sum(score.judge_calls for score in scores),
        judge_cost_usd=sum(score.judge_cost_usd or 0.0 for score in scores) or None,
        own_key=any(score.own_key for score in scores),
    )
    if spent.judge_calls:
        await parts.logs.agent(slug).append(judging.EVALS_SPENT, spent.dump())
    return Trial([row for row, _ in tried], spent.evals, spent.judge_cost_usd or 0.0)


# Hang-up judging run later: the org judged nothing then, the judge failed, or a judge again. The
# verdict is written on the call's log, the one entry a sealed log still takes, and counted into its
# day's drift as the seal counts it.
async def judge_again(parts: Harness, actor: Actor, call: str, *, again: bool) -> CallScore:
    """Judge a finished call, write the verdict on its log, and answer it."""
    async with parts.sessions.begin() as session_:
        read = await calls.read_for_key(session_, actor, call)
    if not is_call_over(read.entries):
        raise Conflict(f"call {call} is still going: it is judged when it hangs up")
    if not again and any(entry.type == "call.score" and entry.data.get("passed") is not None for entry in read.entries):
        raise Conflict(f"call {call} was judged at hang-up: ?again=true judges it again, and pays for it again")
    judged = await judging.judge_call(
        parts.sessions, parts.vault, parts.prompts, read.entries, read.declaration, actor.scope
    )
    await parts.logs.writing(call, read.agent).rescore(judged.score.dump())
    async with parts.sessions.begin() as session_:
        await insights.fold_call(session_, call, read.entries, judged.score)
    return judged.score


async def _try_on(parts: Harness, actor: Actor, call: str, spec: judging.JudgeSpec) -> tuple[Tried, CallScore]:
    async with parts.sessions.begin() as session_:
        read = await calls.read_for_key(session_, actor, call)
        if not is_call_over(read.entries):
            return _skip(call, NOT_FINISHED)
        # As the seal reads it: the agent's settings over its class, for the judge it names is theirs to set.
        declaration = await _as_the_call_ran(session_, actor, read.entries, read.declaration, call)
    transcript = judging.transcript_of(read.entries, declaration)
    if spec.when is JudgeRunsWhen.simulations and not transcript.simulated:
        return _skip(call, ON_SIMULATIONS.format(name=spec.name))
    judged = await judging.judge_call(
        parts.sessions, parts.vault, parts.prompts, read.entries, declaration, actor.scope, only=spec
    )
    score = judged.score
    return Tried(call, next(iter(score.judges), None), score.not_judged), score


async def _as_the_call_ran(
    session_: AsyncSession, actor: Actor, entries: Sequence[Entry], declaration: Declaration | None, call: str
) -> Declaration:
    bare = declaration or Declaration(slug=entries[0].agent)
    return await agents.declaration_for_call(session_, bare, actor.scope, agents.Picked(call=call))


def _skip(call: str, why: str) -> tuple[Tried, CallScore]:
    return Tried(call, None, why), CallScore(judges=[], judge_calls=0, not_judged=why)
