"""Data collection: its tool, what it says each turn, what a call gave, and what is posted when the call ends."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from runtime.studio.service.definition import COLLECT, schema_of
from runtime.wire.parts import ToolSpec
from runtime.wire.studio import Collect, Param

# When the model may end a call that collects: once it has what it came for.
HANG_UP_WHEN = "once every required field of data collection is in and you have said goodbye"
DESCRIPTION = (
    "Saves what the caller told you, field by field. Call it as soon as the caller gives any of "
    "these, with only the ones they gave: {fields}."
)
HAVE = "Collected so far:"
MISSING = "Still to collect, one question at a time:"
ALL_IN = "Every required field is in. {closing}"
TOOL_TIMEOUT_S = 5.0
# How long the business's endpoint is given to take a call's results.
RESULTS_TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class Taken:
    """What one call of the tool saved: the fields it gave, the ones still missing, whether all required are in."""

    saved: list[str]
    missing: list[str]
    complete: bool

    def dump(self) -> dict[str, Any]:
        """As the model reads the tool's answer."""
        return {"saved": self.saved, "missing": self.missing, "complete": self.complete}


def describe(collect: Collect) -> str:
    """What the tool says it does, naming every field."""
    return DESCRIPTION.format(fields=", ".join(field.name for field in collect.fields))


def tool_spec(collect: Collect) -> ToolSpec:
    """The tool as the gateway is told of it: every field an argument, none required."""
    fields = [field.model_copy(update={"required": False}) for field in collect.fields]
    return ToolSpec(
        name=COLLECT,
        description=describe(collect),
        parameters=schema_of(fields),
        side_effect="write",
        timeout_s=TOOL_TIMEOUT_S,
    )


def is_complete(collect: Collect, collected: Mapping[str, Any]) -> bool:
    """Whether every required field is in."""
    return all(field.name in collected for field in collect.fields if field.required)


def close_with(collect: Collect) -> str:
    """What the view says once every required field is in."""
    return ALL_IN.format(closing=collect.closing)


# The one block that changes during a call: what is in, what is missing, and when to close.
def view(collect: Collect, collected: Mapping[str, Any]) -> str:
    """What data collection says this turn."""
    have = [field for field in collect.fields if field.name in collected]
    missing = [field for field in collect.fields if field.name not in collected]
    lines: list[str] = []
    if have:
        lines.append(HAVE)
        lines.extend(f"- {field.name}: {json.dumps(collected[field.name], ensure_ascii=False)}" for field in have)
    if missing:
        lines.append(MISSING)
        lines.extend(describe_field(field) for field in missing)
    if is_complete(collect, collected):
        lines.append(close_with(collect))
    return "\n".join(lines)


def describe_field(field: Param) -> str:
    """One field still to collect, as the view lists it: its type, whether it is required, its values, what it is."""
    about = f": {field.description}" if field.description else ""
    values = f", one of: {', '.join(field.enum)}" if field.enum else ""
    return f"- {field.name} ({field.type}{', required' if field.required else ', optional'}{values}){about}"


def take(collect: Collect, collected: dict[str, Any], arguments: Mapping[str, Any]) -> Taken:
    """Keep the fields the model handed over, an empty one left out; what was saved and what is missing."""
    names = {field.name for field in collect.fields}
    got = {name: value for name, value in arguments.items() if name in names and value not in (None, "")}
    collected.update(got)
    missing = [field.name for field in collect.fields if field.name not in collected]
    return Taken(saved=sorted(got), missing=missing, complete=is_complete(collect, collected))


# What the business's endpoint is posted when the call ends: the same body from the gateway and from
# the class a definition is exported as.
def results(
    collect: Collect,
    collected: Mapping[str, Any],
    *,
    agent: str,
    call: str,
    env: str,
    values: Mapping[str, Any],
    reason: str | None,
    transcript: list[dict[str, str]],
) -> dict[str, Any]:
    """The call's results as they are posted: whose call, what was collected, why it ended, what was said."""
    said: Mapping[str, Any] = values.get("call") or {}
    return {
        "agent": agent,
        "call": call,
        "env": env,
        "from": said.get("from"),
        "to": said.get("to"),
        "channel": said.get("channel"),
        "fields": dict(collected),
        "complete": is_complete(collect, collected),
        "reason": reason,
        "transcript": transcript,
    }
