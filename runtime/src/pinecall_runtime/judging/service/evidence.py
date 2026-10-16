"""What a call's agent could know, as a judge that reads the evidence is shown it."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from pinecall_runtime.judging.service.case import Called, Case, calls_of
from pinecall_runtime.kit.text import JsonObject


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the agent could know: the written text, its tool calls and answers, its states."""

    text: tuple[str, ...]
    # `name(arguments) → answer`: an empty answer means something only beside its arguments.
    calls: tuple[str, ...]
    state: tuple[str, ...] = ()


# A seeded state is rendered into the prompt with no tool running, so it is evidence too. The
# day the call began is: an agent that says what day it is was judged to have invented it.
def evidence_of(case: Case) -> Evidence:
    """What the agent could know: text shown to it, tool calls with their answers, its states."""
    retrieved = [chunk for turn in case.turns for chunk in turn.retrieved]
    began = () if case.began is None else (began_text(case.began),)
    return Evidence(
        text=(*began, *case.evidence, *retrieved),
        calls=tuple(tool_call_text(called) for called in calls_of(case) if called.answer is not None),
        state=tuple(dict.fromkeys(_as_json(state) for state in case.states)),
    )


def began_text(began: float) -> str:
    """When the call began, as a judge reads it: the weekday, the date and the hour, in UTC."""
    moment = datetime.fromtimestamp(began, tz=UTC)
    return f"The call began on {moment:%A, %-d %B %Y at %H:%M} UTC."


# A judge reads a bare `[]` as "no information": the name and the arguments say what it answers.
def tool_call_text(called: Called) -> str:
    """A tool call as a judge reads it: `name(arguments) → answer`."""
    return f"{called.name}({_as_json(called.arguments)}) → {called.answer}"


def as_text(evidence: Evidence) -> str:
    """Every piece of the evidence, one block apart, as a judge model reads it."""
    return "\n\n".join((*evidence.text, *evidence.calls, *evidence.state))


def _as_json(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
