"""A finished call checked again by code alone, no model: the replay, six checks over its transcript and its times."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from runtime.agents.declaration import Declaration
from runtime.calls import folds
from runtime.judging import service as judging
from runtime.wire.base import Entry
from runtime.wire.parts import EndedBy, ScoreVerdict

# ungated and undeclared are apart from kept, so neither is ever read as a pass.
type ConsentOutcome = Literal["kept", "broken", "ungated", "undeclared"]
# Each measure's values, per turn; talk_share is one value for the call, and interruption_delay one per
# reply the caller cut off.
type Measured = Mapping[str, Sequence[float]]

CONFIRMATIONS: frozenset[str] = frozenset({"confirm.request", "confirm.granted", "confirm.declined"})

# This runtime writes no confirm.* yet: a call it wrote is reported, not failed.
UNGATED = (
    "the confirmation gate is not built yet: {count} irreversible tool call(s) ran and the log "
    "carries no confirm.* at all"
)
NO_SIDE_EFFECT_SAID = (
    "{count} tool call(s) and not one declared side effect, so nothing here says which of them are irreversible"
)
NO_DECLARATION = (
    "agent {agent} is not registered on this gateway, so no tool's side effect is known: "
    "run this while the app that declares the tools is connected"
)
NO_WORDS = (
    "no banned words were declared for this call: `pinecall eval <call> --policy <file>` reads them "
    'from a file of {"banned": […]}'
)
NOTHING_MEASURED = "no turn of this call carried any of {names}"
# A budget may name it like any latency: the worst barge-in of the call, in seconds.
INTERRUPTION_DELAY = "interruption_delay"
# A share of the talking time, 0 to 1, judged by its own check and never as seconds.
TALK_SHARE = "talk_share"
NO_TALK_BUDGET = (
    'no talk_share in the budget: a policy file of {"budget": {"talk_share": 0.6}} sets the most of the '
    "talking the agent may do, 0 to 1"
)
NOTHING_TIMED = "no turn of this call said when anybody started and stopped speaking"
NOTHING_CUT_OFF = "no reply of the agent's was cut off in this call"
# A cut-off reply the caller said no words over (a cough, a false start) is livekit's to resume,
# and one the caller hung up after has nothing left to answer: neither is judged.
NOTHING_TO_ANSWER = "the caller cut the agent off {count} time(s) and said nothing it could answer, or hung up"
# The agent that starts its cut-off reply over, rather than answering, opens with the same
# words: four in a row is not a coincidence of Spanish or English.
STARTED_OVER_WORDS = 4
# Seconds, under livekit's own metric names; a request may bring its own.
DEFAULT_BUDGET: Mapping[str, float] = {"e2e_latency": 2.0, "llm_node_ttft": 1.0, "tts_node_ttfb": 0.6}
# The marks around a word, markdown's among them: a banned word right after `**` is the word.
PUNCTUATION = ".,;:¿?¡!()\"'*_`~[]"

# ungated is deferred, not broken: the gate is missing from the runtime, not from the agent.
AS_A_STATUS: Mapping[ConsentOutcome, ScoreVerdict] = {
    "kept": "held",
    "broken": "broken",
    "ungated": "deferred",
    "undeclared": "skipped",
}


@dataclass(frozen=True, slots=True)
class Policy:
    """What a replay holds a call to: the words the agent may not say, and the most each measure may take."""

    banned: tuple[str, ...] = ()
    budget: Mapping[str, float] = field(default_factory=dict[str, float])


@dataclass(frozen=True, slots=True)
class Checked:
    """One code check's answer: its name, its status and why."""

    check: str
    status: ScoreVerdict
    detail: str


@dataclass(frozen=True, slots=True)
class Replay:
    """A finished call checked again: the six checks, in order."""

    call: str
    agent: str
    verdicts: tuple[Checked, ...]

    @property
    def passed(self) -> bool:
        """Whether no check broke."""
        return not any(verdict.status == "broken" for verdict in self.verdicts)


@dataclass(frozen=True, slots=True)
class ConsentRead:
    """What the consent rule found, and the sentence that says it."""

    outcome: ConsentOutcome
    detail: str


# Grants match by call id, never by tool name: two calls of one tool each need their own yes.
def consent_of(gate: Sequence[judging.GateLine]) -> ConsentRead:
    """Whether every irreversible tool call ran after its own granted confirmation, by seq."""
    tool_calls = tuple(line for line in gate if line.kind == "tool.call")
    if tool_calls and all(line.side_effect is None for line in tool_calls):
        return ConsentRead("undeclared", NO_SIDE_EFFECT_SAID.format(count=len(tool_calls)))
    ran = tuple(line for line in tool_calls if line.side_effect == "irreversible")
    if not ran:
        return ConsentRead("kept", f"none of the {len(tool_calls)} tool call(s) in this call was irreversible")
    confirmations = tuple(line for line in gate if line.kind in CONFIRMATIONS)
    if not confirmations:
        return ConsentRead("ungated", UNGATED.format(count=len(ran)))
    faults = [
        fault
        for tool in ran
        if (fault := _find_fault(tool, [c for c in confirmations if c.call_id == tool.call_id])) is not None
    ]
    if faults:
        return ConsentRead("broken", "; ".join(faults))
    return ConsentRead("kept", f"{len(ran)} irreversible tool call(s), each after a granted confirmation")


# The log carries no side effect: the irreversible tools are the agent's declaration, which the
# transcript read them from. A tool the declaration no longer names reads as one that changes nothing.
def check_consent(transcript: judging.Transcript, _measured: Measured, _policy: Policy) -> Checked:
    """Consent, from the gate trace and the tools the agent declares irreversible."""
    if transcript.declaration is None:
        return Checked("consent", "skipped", NO_DECLARATION.format(agent=transcript.agent))
    gate = [
        replace(line, side_effect=line.side_effect or "read") if line.kind == "tool.call" else line
        for line in transcript.gate
    ]
    read = consent_of(gate)
    return Checked("consent", AS_A_STATUS[read.outcome], read.detail)


# A lone word matches whole words (`tú` is not `tútem`); a phrase matches anywhere.
def check_register(transcript: judging.Transcript, _measured: Measured, policy: Policy) -> Checked:
    """Whether the agent said none of the banned words, case-insensitively."""
    if not policy.banned:
        return Checked("register", "skipped", NO_WORDS)
    said = transcript.lines_by(judging.AGENT)
    found = [
        (turn, word)
        for turn, text in enumerate(said, 1)
        for word in policy.banned
        if (word.casefold() in text.casefold() if " " in word else word.casefold() in _words_in_order(text))
    ]
    if found:
        spoken = "; ".join(f"{word!r} in turn {turn}" for turn, word in found)
        return Checked("register", "broken", f"the agent said {spoken}")
    return Checked(
        "register", "held", f"none of the {len(policy.banned)} declared word(s) was said in {len(said)} agent turns"
    )


def check_errors(transcript: judging.Transcript, _measured: Measured, _policy: Policy) -> Checked:
    """Broken on an error the session did not recover from; the recovered ones named."""
    fatal = [failed for failed in transcript.errors if not failed.recoverable]
    if fatal:
        return Checked("errors", "broken", "; ".join(_say(failed) for failed in fatal))
    if transcript.errors:
        recovered = "; ".join(_say(failed) for failed in transcript.errors)
        return Checked("errors", "held", f"recovered from {len(transcript.errors)} error(s): {recovered}")
    return Checked("errors", "held", "the call logged no error")


# The worst turn, not the median: the caller who waited four seconds once heard four seconds.
def check_latency(_transcript: judging.Transcript, measured: Measured, policy: Policy) -> Checked:
    """Each budgeted measure's worst turn, against its limit."""
    budget = policy.budget or DEFAULT_BUDGET
    worst = {name: max(values) for name, values in measured.items() if name in budget and name != TALK_SHARE and values}
    if not worst:
        return Checked("latency", "skipped", NOTHING_MEASURED.format(names=", ".join(budget)))
    over = any(seconds > budget[name] for name, seconds in worst.items())
    detail = "; ".join(
        f"{name} {seconds:.3f}s {'>' if seconds > budget[name] else '<='} {budget[name]:.3f}s "
        f"at its worst of {len(measured[name])} turns"
        for name, seconds in worst.items()
    )
    return Checked("latency", "broken" if over else "held", detail)


def check_talk(_transcript: judging.Transcript, measured: Measured, policy: Policy) -> Checked:
    """Broken when the agent took more of the talking than the budget's talk_share allows."""
    limit = policy.budget.get(TALK_SHARE)
    if limit is None:
        return Checked("talk", "skipped", NO_TALK_BUDGET)
    shares = measured.get(TALK_SHARE)
    if not shares:
        return Checked("talk", "skipped", NOTHING_TIMED)
    share = shares[0]
    over = share > limit
    detail = f"the agent spoke {share:.0%} of the talking time, {'>' if over else '<='} {limit:.0%}"
    return Checked("talk", "broken" if over else "held", detail)


# Only the replies the caller cut off with words are judged: those words want an answer.
def check_interruptions(transcript: judging.Transcript, _measured: Measured, _policy: Policy) -> Checked:
    """Each reply the caller cut off, followed by the agent answering them, not starting over."""
    turns = _list_spoken(transcript)
    cut = [index for index, turn in enumerate(turns) if turn.interrupted]
    if not cut:
        return Checked("interruptions", "skipped", NOTHING_CUT_OFF)
    faults: list[str] = []
    answered = unanswerable = 0
    for index in cut:
        found = _answer_to(turns, transcript.ended_by, index)
        if found is None:
            unanswerable += 1
            continue
        heard, answer = found
        if answer is None:
            faults.append(f"the caller cut in at seq {heard.seq} and the agent never answered")
        elif _is_started_over(turns[index].text, answer.text):
            faults.append(
                f"the reply at seq {answer.seq} started over the one cut off at seq "
                f"{turns[index].seq} instead of answering the caller at seq {heard.seq}"
            )
        else:
            answered += 1
    if faults:
        return Checked("interruptions", "broken", "; ".join(faults))
    if not answered:
        return Checked("interruptions", "skipped", NOTHING_TO_ANSWER.format(count=unanswerable))
    return Checked(
        "interruptions",
        "held",
        f"the agent stopped and answered the caller each of the {answered} time(s) it was cut off",
    )


# Until 2026-11 six calls with six signatures, and "passed" worked out in the endpoint.
type Check = Callable[[judging.Transcript, Measured, Policy], Checked]
CHECKS: tuple[Check, ...] = (
    check_consent,
    check_register,
    check_errors,
    check_latency,
    check_talk,
    check_interruptions,
)


def replay(transcript: judging.Transcript, measured: Measured, policy: Policy) -> Replay:
    """The six checks over a finished call: consent, register, errors, latency, talk, barge-ins."""
    verdicts = tuple(check(transcript, measured, policy) for check in CHECKS)
    return Replay(transcript.call, transcript.agent, verdicts)


# The call is read once as a judge reads it and once for its times: until 2026-11 the replay folded
# the log a third time, into a value that held nothing the other two did not.
def replay_call(entries: Sequence[Entry], declaration: Declaration | None, policy: Policy) -> Replay:
    """A finished call's log checked again, on what its agent declares."""
    return replay(judging.transcript_of(entries, declaration), measure(entries), policy)


def measure(entries: Sequence[Entry]) -> Measured:
    """Every measure a budget may name, of each turn of the call."""
    measured = folds.samples(folds.reduce(entries).turns)
    barged = folds.interruption_delays(entries)
    if barged:
        measured[INTERRUPTION_DELAY] = barged
    return measured


def _find_fault(tool: judging.GateLine, about: Sequence[judging.GateLine]) -> str | None:
    granted = _first(about, "confirm.granted")
    if granted is None:
        declined = _first(about, "confirm.declined")
        if declined is not None:
            return f"{tool.tool} ran at seq {tool.seq}, after its confirm.declined at seq {declined.seq}"
        return f"{tool.tool} ran at seq {tool.seq} with no confirm.granted before it"
    if granted.seq > tool.seq:
        return f"{tool.tool} ran at seq {tool.seq}, before its confirm.granted at seq {granted.seq}"
    request = _first(about, "confirm.request")
    if request is not None and request.audience is not None and request.audience != granted.audience:
        return (
            f"{tool.tool} at seq {tool.seq} was confirmed by {granted.audience} "
            f"and asked of {request.audience} at seq {request.seq}"
        )
    return None


def _first(about: Sequence[judging.GateLine], kind: judging.GateKind) -> judging.GateLine | None:
    return next((line for line in about if line.kind == kind), None)


def _say(failed: judging.Failed) -> str:
    return f"seq {failed.seq} {failed.code}: {failed.message}"


# The caller's next words after the cut, and the agent's next reply after them: None when the
# agent spoke again before the caller said anything, or the caller hung up with no reply owed.
def _answer_to(
    turns: Sequence[judging.Said], ended_by: EndedBy | None, index: int
) -> tuple[judging.Said, judging.Said | None] | None:
    after = turns[index + 1 :]
    heard = next(iter(after), None)
    if heard is None or heard.role != judging.CALLER:
        return None
    answer = next((turn for turn in after if turn.role == judging.AGENT), None)
    if answer is None and ended_by == "caller":
        return None
    return heard, answer


# The transcript gives a tool called without a word a turn of its own, which said nothing: no reply.
def _list_spoken(transcript: judging.Transcript) -> list[judging.Said]:
    return [turn for turn in transcript.turns if turn.role == judging.CALLER or turn.text]


def _is_started_over(cut_off: str, answer: str) -> bool:
    opening = _words_in_order(cut_off)[:STARTED_OVER_WORDS]
    return len(opening) == STARTED_OVER_WORDS and _words_in_order(answer)[:STARTED_OVER_WORDS] == opening


def _words_in_order(text: str) -> list[str]:
    return [word.strip(PUNCTUATION).casefold() for word in text.split() if word.strip(PUNCTUATION)]
