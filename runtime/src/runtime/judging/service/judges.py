"""The judges an agent's calls meet, resolved once: Pinecall's as switched, the org's own, its own or its class's."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import THE_ORGS_OWN
from runtime.agents import service as agents
from runtime.agents.declaration import Agent
from runtime.enums import JudgeAnswer, JudgeRunsWhen
from runtime.exceptions import Conflict, NotFound
from runtime.judging.models import AgentJudge
from runtime.judging.repository.judges import JudgeRepository
from runtime.judging.repository.switches import JudgeSwitchRepository
from runtime.judging.service import library
from runtime.judging.service.library import Gate
from runtime.judging.service.specs import READS, JudgeSpec
from runtime.wire.declaration import JudgeDeclaration, JudgesDeclared
from runtime.wire.parts import JudgeRead

PINECALL = "pinecall"
THE_ORG = "org"
THE_CLASS = "class"
NOBODY = "{whose} has no judge called {name}"
TAKEN = "{name} is {whose} judge already: one name asks one question of a call"
ONLY_ON = (
    "{name} is one of Pinecall's judges: it is switched on or off (`pinecall judges on|off {name}`), "
    "never rewritten; a question of your own takes a name of your own"
)
NOT_A_SWITCH = "{name} is a judge of your own: it runs while it is written, and `pinecall judges rm {name}` stops it"
NOT_YOURS = "{name} is one of Pinecall's judges and is never deleted: `pinecall judges off {name}` turns it off"


# The question "which judges does a call of this agent meet" was answered three times until 2026-11
# (the list an endpoint shows, one judge by its name, the panel), each branching on whether the class
# declares them. It is answered here once, and the three read this.
@dataclass(frozen=True, slots=True)
class RosterJudge:
    """One judge an agent's calls may meet: its question, whose it is, and whether it runs."""

    spec: JudgeSpec
    # "pinecall" for the library's, "org" for the org's own, "class" for the agent's class's, else the agent's slug.
    owner: str
    on: bool
    # True on one the class declares, its switch of a library judge or its own: no endpoint writes it.
    fixed: bool = False
    # What may settle a library judge as N/A before any model is asked.
    gate: Gate = "none"
    # The library's: the version of its question, so a changed question reads as a changed judge; what it
    # holds a call to, what it saves an org from, and whether Pinecall says to switch it on first.
    version: int | None = None
    summary: str | None = None
    why: str | None = None
    recommended: bool = False
    # One of the org's own: who wrote it last, and when.
    author: str | None = None
    set_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Wanted:
    """What a write says of a judge: a question of the org's own whole, or for one of Pinecall's only `on`."""

    question: str = ""
    answer: JudgeAnswer = JudgeAnswer.verdict
    choices: Sequence[str] = ()
    when: JudgeRunsWhen = JudgeRunsWhen.always
    trigger: str = ""
    reads: Sequence[JudgeRead] = ()
    # One of Pinecall's judges: whether the org's calls (or the agent's) meet it. Nothing else.
    on: bool | None = None
    # The fields the write named, so one of Pinecall's is told apart from a question written whole.
    named: frozenset[str] = frozenset()


# The class, when it declares its judges, is the agent's list: its switches and its own, and the
# agent's rows are not read; the org's own judges meet its calls either way. An agent's roster
# carries the org's own too, since its calls meet them; the org's ('') is the org's alone.
async def roster_of(
    session: AsyncSession, org: str, agent: str, class_judges: JudgesDeclared | None = None
) -> tuple[RosterJudge, ...]:
    """Every judge the agent's calls may meet: Pinecall's as switched, the org's own, the agent's or its class's."""
    written = library.library_judges()
    if class_judges is None:
        switches = {row.name: row.is_on for row in await JudgeSwitchRepository(session).list_for_agent(org, agent)}
        rows = await JudgeRepository(session).list_for_call(org, agent)
        own = tuple(_judge_of_row(row) for row in rows)
    else:
        switches, of_the_class = judges_of_class(class_judges)
        rows = await JudgeRepository(session).list_for_call(org, THE_ORGS_OWN)
        own = (
            *(_judge_of_row(row) for row in rows),
            *(RosterJudge(spec, owner=THE_CLASS, on=True, fixed=True) for spec in of_the_class),
        )
    fixed = class_judges is not None
    return (*(_library_judge(judge, switches, fixed=fixed) for judge in written.values()), *own)


async def list_judges(session: AsyncSession, org: str, agent: Agent | None) -> tuple[RosterJudge, ...]:
    """The roster of the org's own level (no agent), or of the agent with what its class declares."""
    if agent is None:
        return await roster_of(session, org, THE_ORGS_OWN)
    class_judges = None if agent.declaration is None else agent.declaration.judges
    return await roster_of(session, org, agent.slug, class_judges)


async def judge_named(
    session: AsyncSession, org: str, agent: str, name: str, class_judges: JudgesDeclared | None = None
) -> JudgeSpec:
    """One of Pinecall's judges by its name, else the org's own or the agent's (its class's when it declares them)."""
    roster = await roster_of(session, org, agent, class_judges)
    found = next((judge.spec for judge in roster if judge.spec.name == name), None)
    if found is None:
        raise NotFound(NOBODY.format(whose=agent, name=name))
    return found


def judges_of_class(class_judges: JudgesDeclared) -> tuple[dict[str, bool], tuple[JudgeSpec, ...]]:
    """The library's switches and the agent's own judges as the class declares them; refused by sentence."""
    written = library.library_judges()
    switches = library.switches_of_class(class_judges.on, written, "judges")
    own = tuple(spec_of(judge.name, judge) for judge in class_judges.own)
    library.check_own_names([spec.name for spec in own], written, "judges")
    return switches, own


# One of Pinecall's is switched, one of the org's own is written whole; never the other way. An agent
# whose class declares its judges writes none of them here: 409 naming the class.
async def write_judge(
    session: AsyncSession, org: str, agent: Agent | None, name: str, wanted: Wanted, *, by: str
) -> tuple[RosterJudge, ...]:
    """Switch one of Pinecall's judges for the org (no agent) or an agent, or write an own one; the roster after."""
    level = _level_of(agent)
    if name in library.library_judges():
        if wanted.on is None or wanted.named - {"on"}:
            raise Conflict(ONLY_ON.format(name=name))
        await JudgeSwitchRepository(session).switch(org, level, (name,), on=wanted.on, author=by)
    elif wanted.on is not None:
        # A switch of a name nobody wrote is a name typed wrong, not a judge of the org's.
        await judge_named(session, org, level, name)
        raise Conflict(NOT_A_SWITCH.format(name=name))
    else:
        await put_judge(session, org, level, spec_of(name, wanted), by=by)
    return await roster_of(session, org, level)


# A name is one question per call. A class is refused the org's name where it declares itself
# (`declaration.check_judges_of_class`); until 2026-11 nothing refused the org's own judge written
# after it, and a call of that agent carried two verdicts under the one name.
async def put_judge(session: AsyncSession, org: str, agent: str, spec: JudgeSpec, *, by: str) -> None:
    """Write a judge whole, the org's (agent '') or one agent's; the same name again replaces it."""
    repository = JudgeRepository(session)
    clash = await repository.find_clash(org, agent, spec.name)
    if clash is not None:
        raise Conflict(TAKEN.format(name=spec.name, whose=_owner(clash)))
    if agent == THE_ORGS_OWN:
        holding = await repository.find_class_holding(org, spec.name)
        if holding is not None:
            raise Conflict(TAKEN.format(name=spec.name, whose=f"the class of {holding}'s"))
    await repository.put(
        org,
        agent,
        name=spec.name,
        author=by,
        question=spec.question,
        answer=spec.answer,
        choices=list(spec.choices),
        runs_when=spec.when,
        trigger=spec.trigger,
        reads=spec.list_reads(),
    )


async def delete_judge(session: AsyncSession, org: str, agent: Agent | None, name: str) -> tuple[RosterJudge, ...]:
    """Forget one of the org's own judges (no agent) or the agent's; 404 for a name nobody wrote, 409 for Pinecall's."""
    level = _level_of(agent)
    if name in library.library_judges():
        raise Conflict(NOT_YOURS.format(name=name))
    if not await JudgeRepository(session).delete_named(org, level, name):
        raise NotFound(NOBODY.format(whose=_owner(level), name=name))
    return await roster_of(session, org, level)


def spec_of(name: str, said: Wanted | JudgeDeclaration) -> JudgeSpec:
    """A judge as a write says it, or as a class declares it."""
    return JudgeSpec(
        name=name,
        question=said.question,
        answer=said.answer,
        choices=tuple(said.choices),
        when=said.when,
        trigger=said.trigger,
        reads=frozenset(said.reads),
    )


def _judge_of_row(row: AgentJudge) -> RosterJudge:
    kept = {str(item) for item in row.reads}
    spec = JudgeSpec(
        name=row.name,
        question=row.question,
        answer=row.answer,
        choices=tuple(str(choice) for choice in row.choices),
        when=row.runs_when,
        trigger=row.trigger,
        reads=frozenset(read for read in READS if read in kept),
    )
    return RosterJudge(spec, owner=row.agent or THE_ORG, on=True, author=row.author, set_at=row.set_at)


def _library_judge(judge: library.Written, switches: dict[str, bool], *, fixed: bool) -> RosterJudge:
    return RosterJudge(
        judge.spec,
        owner=PINECALL,
        on=switches.get(judge.spec.name, judge.on_by_default),
        fixed=fixed,
        gate=judge.gate,
        version=judge.version,
        summary=judge.summary,
        why=judge.why,
        recommended=judge.recommended,
    )


# The level a write is at: the org's own, or an agent's, refused while its class declares its judges.
def _level_of(agent: Agent | None) -> str:
    if agent is None:
        return THE_ORGS_OWN
    agents.refuse_what_the_class_sets(agent, ("judges",))
    return agent.slug


def _owner(agent: str) -> str:
    """The owner of a judge as a sentence names it: the org, or the agent's slug."""
    return "the org" if agent == THE_ORGS_OWN else agent
