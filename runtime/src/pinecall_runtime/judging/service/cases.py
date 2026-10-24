"""The org's dataset: real calls kept as goldens, born at hang-up, decided, and played again."""

import datetime as dt
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import CaseSource, CaseStatus, Env
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from pinecall_runtime.judging.models import EvalCase
from pinecall_runtime.judging.repository import CaseRepository
from pinecall_runtime.judging.schemas import BrokeOn, CaseDecision, CaseRow
from pinecall_runtime.judging.service import groups
from pinecall_runtime.judging.service.case import is_simulated
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import (
    CallStarted,
    EventReceived,
    MemoryOps,
    StateChanged,
    ToolCall,
    UserTurnEnded,
    event_of,
)
from pinecall_runtime.wire.goldens import Expect, Golden, InjectedEvent, Turn
from pinecall_runtime.wire.scores import CallScore, Judgment

# The inbox is for reading: past this many cases waiting on one agent, a broken call is judged as
# ever and not kept, until a person decides some.
PENDING_AT_MOST = 50
# Born at hang-up, a case is the platform's, not a person's.
THE_PANEL = "the hang-up panel"
# Written into the golden's own fields (the tools consent broke on, `grounded`); every other judge
# is asked again by name in `expect.judges`.
IN_FIELDS = frozenset({"consent", "grounded"})
# Its rule is the simulated caller's, and a case plays written lines: nobody holds it.
UNPLAYABLE = frozenset({"expected-outcome"})
# The words of the first caller line a born case is named by.
NAMED_BY_WORDS = 4

TAKEN = "agent {agent} has a case named {name} already: forget it first, or promote under another"
NOT_WRITTEN_BY_HAND = (
    "agent {agent}'s case {name} was kept from {source} {call}, not written by hand: "
    "forget it first, or write another name"
)
NOTHING_SAID = "call {call} has no line of the caller's to play again"
NO_SUCH_CASE = "no case {id} in this key's org"
UNKNOWN_CASES = "agent {agent} has no case named {names}"
WRONG_ONLY_WHEN_DISMISSED = (
    "judge_was_wrong says a judge broke where it should have held, so it dismisses the case: "
    "send it with status dismissed"
)
NOT_WHAT_BROKE = "case {name} did not break on {judge}: it broke on {broke}"
# The note is kept on the judge's calibration label: with no judge it would be dropped unsaid.
A_NOTE_ALONE = "note is kept on the calibration label of the judge that was wrong: send judge_was_wrong"
# A decision that moves nothing is said so, as a settings write that changes nothing is.
ALREADY = "case {name} is already {status}"


@dataclass(frozen=True, slots=True)
class Promoted:
    """A golden to keep as a case, a finished call's or a person's own: whose, from which env, named how, by whom."""

    org: str
    env: Env
    name: str
    author: str
    held_out: bool = False
    status: CaseStatus = CaseStatus.approved
    broke: Sequence[BrokeOn] = ()
    source_version: int | None = None


@dataclass(frozen=True, slots=True)
class Born:
    """Where a call that broke was answered: the org, the env, the agent, the settings version."""

    org: str
    env: Env
    agent: str
    version: int | None


def golden_of(entries: Sequence[Entry], name: str, expect: Expect) -> Golden:
    """The call's caller lines and the app's facts as turns, its first state, what it recalled."""
    turns: list[Turn] = []
    state: dict[str, object] = {}
    recalled: list[str] = []
    for entry in entries:
        if entry.type not in {"turn.user", "state.changed", "event.received", "memory.ops"}:
            continue
        match event_of(entry):
            case UserTurnEnded() as heard if heard.text.strip():
                turns.append(Turn(say=heard.text))
            case StateChanged() as changed if not turns and not state:
                state = dict(changed.state)
            case EventReceived() as arrived if arrived.source == "app":
                turns.append(Turn(event=InjectedEvent(name=arrived.name, data=arrived.data)))
            case MemoryOps() as memory:
                facts = (fact.text for op in memory.ops if op.op == "recall" for fact in op.facts)
                recalled.extend(fact for fact in facts if fact not in recalled)
            case _:
                continue
    call = next((entry.call for entry in entries if entry.call is not None), "")
    if not any(turn.say is not None for turn in turns):
        raise Conflict(NOTHING_SAID.format(call=call))
    started = entries[0].ts if entries else 0.0
    # A field the call gave nothing for is left out, as a golden written by hand leaves it out.
    given = {"state": state, "memory": recalled}
    return Golden.model_validate(
        {
            "name": name,
            "turns": [turn.dump() for turn in turns],
            "today": dt.datetime.fromtimestamp(started, dt.UTC).date(),
            "expect": expect.dump(),
            "promoted_from": call,
            **{field: value for field, value in given.items() if value},
        }
    )


# `state.changed` holds the whole state, so the last one at or before the cut is where it opens.
def cut_at(entries: Sequence[Entry], seq: int) -> list[Entry]:
    """The call from after a seq on, opening in the state it was in at that seq."""
    if seq == 0:
        return list(entries)
    states = [entry for entry in entries if entry.type == "state.changed" and entry.seq <= seq]
    return [*states[-1:], *(entry for entry in entries if entry.seq > seq)]


# A verdict knows what broke, never what was right: the expect says "not like this again", and a
# person writes what the agent should have done.
def expect_of(judgments: Sequence[Judgment], entries: Sequence[Entry]) -> Expect:
    """What a call's broken verdicts say must not happen again, as a golden's expect."""
    broken = [judgment for judgment in judgments if judgment.verdict == "broken"]
    not_tools: list[str] = []
    for judgment in broken:
        if judgment.name == "consent":
            seqs = frozenset(judgment.evidence.seqs)
            ran = (entry for entry in entries if entry.type == "tool.call" and entry.seq in seqs)
            named = (event_of(entry) for entry in ran)
            not_tools.extend(call.name for call in named if isinstance(call, ToolCall) and call.name not in not_tools)
    by_name = [
        judgment.name for judgment in broken if judgment.name not in IN_FIELDS and judgment.name not in UNPLAYABLE
    ]
    # Only what broke is set, so the golden a person reads or pulls says nothing it does not mean.
    fields: dict[str, object] = {}
    if not_tools:
        fields["not_tools"] = not_tools
    if any(judgment.name == "grounded" for judgment in broken):
        fields["grounded"] = True
    if by_name:
        fields["judges"] = list(dict.fromkeys(by_name))
    return Expect.model_validate(fields)


def broke_of(score: CallScore) -> list[BrokeOn]:
    """The judges that broke on a call, each with its reason."""
    return [
        BrokeOn(judge=judgment.name, reason=judgment.reason)
        for judgment in score.judges
        if judgment.verdict == "broken"
    ]


# A call a run opened is never judged at hang-up, so it never gets here; a call nobody spoke in
# has nothing to play again. A simulation a judge broke on is kept, with the persona that played.
async def keep_at_hangup(session: AsyncSession, entries: Sequence[Entry], score: CallScore, born: Born) -> None:
    """Keep a call one of its judges broke on as a pending case in its group, unless full."""
    broke = broke_of(score)
    if not broke or not _caller_spoke(entries):
        return
    call = next((entry.call for entry in entries if entry.call is not None), "")
    name = _name_of(broke[0].judge, entries, call)
    golden = golden_of(entries, name, expect_of(score.judges, entries))
    kept = await CaseRepository(session).born(
        id=random_id("case_", 6),
        org=born.org,
        agent=born.agent,
        name=name,
        golden=golden.dump(),
        source_call=call,
        source_env=born.env,
        author=THE_PANEL,
        broke=[judgment.dump() for judgment in broke],
        source_version=born.version,
        source=CaseSource.simulation if is_simulated(entries) else CaseSource.call,
        persona=_persona_of(entries),
        at_most=PENDING_AT_MOST,
    )
    if kept is not None:
        first = broke[0]
        await groups.join_group(session, born.org, born.agent, first.judge, kept, cause=first.reason)


async def promote_case(session: AsyncSession, golden: Golden, agent: str, promoting: Promoted) -> CaseRow:
    """Keep the golden as a case of the org's dataset; a name the agent has already is refused."""
    named = golden.model_copy(update={"name": promoting.name})
    row = EvalCase(
        id=random_id("case_", 6),
        org=promoting.org,
        agent=agent,
        name=promoting.name,
        golden=named.dump(),
        source_call=named.promoted_from,
        source_env=promoting.env,
        held_out=promoting.held_out,
        author=promoting.author,
        status=promoting.status,
        broke=[judgment.dump() for judgment in promoting.broke],
        source_version=promoting.source_version,
    )
    try:
        async with session.begin_nested():
            await CaseRepository(session).add(row)
    except IntegrityError as taken:
        raise Conflict(TAKEN.format(agent=agent, name=promoting.name)) from taken
    return CaseRow.of(row)


# A case a person wrote is theirs to write again: the same name rewrites its golden and held-out,
# and keeps its status, author and age. A name a call or a simulation made is refused, so a hand
# never rewrites the evidence a judge broke on.
async def write_case(session: AsyncSession, golden: Golden, agent: str, writing: Promoted) -> CaseRow:
    """Keep a golden a person wrote as an approved case of the agent; their own name again rewrites it."""
    named = golden.model_copy(update={"name": writing.name})
    repository = CaseRepository(session)
    had = await repository.named(writing.org, agent, writing.name)
    if had is None:
        row = EvalCase(
            id=random_id("case_", 6),
            org=writing.org,
            agent=agent,
            name=writing.name,
            golden=named.dump(),
            source_call=None,
            source_env=writing.env,
            held_out=writing.held_out,
            author=writing.author,
            status=CaseStatus.approved,
            broke=[],
            source=CaseSource.person,
        )
        try:
            async with session.begin_nested():
                await repository.add(row)
        except IntegrityError as taken:
            raise Conflict(TAKEN.format(agent=agent, name=writing.name)) from taken
        return CaseRow.of(row)
    if had.source is not CaseSource.person:
        raise Conflict(
            NOT_WRITTEN_BY_HAND.format(agent=agent, name=writing.name, source=had.source, call=had.source_call)
        )
    return CaseRow.of(await repository.update(had, golden=named.dump(), held_out=writing.held_out))


async def list_cases(
    session: AsyncSession, org: str, agent: str | None, status: CaseStatus | None = None, group: str | None = None
) -> list[CaseRow]:
    """The org's cases, one agent's or every one, one status or group or all, pending first."""
    return [CaseRow.of(row) for row in await CaseRepository(session).listed(org, agent, status, group)]


async def waiting_cases(session: AsyncSession, org: str, agent: str | None) -> int:
    """How many cases wait for a person, one agent's or the org's."""
    return await CaseRepository(session).waiting(org, agent)


async def pick_cases(session: AsyncSession, org: str, agent: str, names: Sequence[str], *, every: bool) -> list[Golden]:
    """The goldens a run plays: the cases named, and with every, the approved ones not held out."""
    found = await CaseRepository(session).picked(org, agent, names, every=every)
    missing = sorted(set(names) - {case.name for case in found})
    if missing:
        raise NotFound(UNKNOWN_CASES.format(agent=agent, names=", ".join(missing)))
    return [Golden.model_validate(case.golden) for case in found]


async def get_case(session: AsyncSession, org: str, case: str) -> CaseRow:
    """One of the org's cases; another org's, or nobody's, is a 404."""
    return CaseRow.of(await _found(session, org, case))


def check_decision(case: CaseRow, decision: CaseDecision) -> None:
    """Refuse a decision that moves nothing, a judge wrongly named as wrong, and a note alone."""
    wrong = decision.judge_was_wrong
    if wrong is None:
        if decision.note is not None:
            raise ValidationError(A_NOTE_ALONE)
        if _moves_nothing(case, decision):
            raise Conflict(ALREADY.format(name=case.name, status=case.status))
        return
    if decision.status is not CaseStatus.dismissed:
        raise ValidationError(WRONG_ONLY_WHEN_DISMISSED)
    broke = [judgment.judge for judgment in case.broke]
    if wrong not in broke:
        named = ", ".join(broke) or "no judge (a person kept it)"
        raise ValidationError(NOT_WHAT_BROKE.format(name=case.name, judge=wrong, broke=named))


async def decide_case(session: AsyncSession, org: str, case: str, decision: CaseDecision, *, by: str) -> CaseRow:
    """Write what a person decided of one case: its status, held out, kept in the repository."""
    row = await _found(session, org, case)
    changes: dict[str, object] = {}
    if decision.status is not None:
        changes.update(status=decision.status, decided_by=by, decided_at=dt.datetime.now(dt.UTC))
    if decision.held_out is not None:
        changes["held_out"] = decision.held_out
    if decision.kept_in_repo is not None:
        changes["kept_in_repo"] = decision.kept_in_repo
    decided = await CaseRepository(session).update(row, **changes)
    if decision.status is not None and decided.group_id is not None:
        await groups.settle_group(session, org, decided.group_id)
    return CaseRow.of(decided)


async def delete_case(session: AsyncSession, org: str, case: str) -> None:
    """Forget one of the org's cases; another org's, or nobody's, is a 404."""
    await CaseRepository(session).delete(await _found(session, org, case))


def _moves_nothing(case: CaseRow, decision: CaseDecision) -> bool:
    return (
        decision.status is not None
        and decision.status == case.status
        and decision.held_out in (None, case.held_out)
        and decision.kept_in_repo in (None, case.kept_in_repo)
    )


async def _found(session: AsyncSession, org: str, case: str) -> EvalCase:
    row = await CaseRepository(session).get(org, case)
    if row is None:
        raise NotFound(NO_SUCH_CASE.format(id=case))
    return row


def _name_of(judge: str, entries: Sequence[Entry], call: str) -> str:
    """The first judge that broke, the caller's first words, and the call's last six characters."""
    first = next((heard.text for heard in _heard(entries) if heard.text.strip()), "")
    bare = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode().casefold()
    words = re.findall(r"[a-z0-9]+", bare)[:NAMED_BY_WORDS]
    return "-".join([judge, *words, call[-6:].casefold()])


def _persona_of(entries: Sequence[Entry]) -> str | None:
    for entry in entries:
        if entry.type == "call.started":
            return CallStarted.model_validate(entry.data).persona
    return None


def _caller_spoke(entries: Sequence[Entry]) -> bool:
    return any(heard.text.strip() for heard in _heard(entries))


def _heard(entries: Sequence[Entry]) -> list[UserTurnEnded]:
    return [UserTurnEnded.model_validate(entry.data) for entry in entries if entry.type == "turn.user"]
