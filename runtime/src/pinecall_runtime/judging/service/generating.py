"""Personas written for an agent by a model: from its prompt, its tools, what it knows, a call."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Never

from livekit.agents import llm
from pydantic import BaseModel, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.judging.service.asking import forced
from pinecall_runtime.judging.service.specs import Behavior, Persona
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.metrics import LLMModelUsage

# Cekura's rules for an expectation, which a judge can hold a call to: one demand, verifiable from
# the conversation, licensed by what the agent was told, and never about hanging up.
WRITER = (
    "You write test callers for a phone or chat agent: people who call it, each wanting one "
    "thing, each talking their own way. Write each caller's goal in the first person, as the "
    "caller would think it, with the facts they know. Write what the caller expects of the agent "
    "as separate lines, each one verifiable from the conversation alone and starting with "
    '"The agent should": something the agent\'s prompt, tools or knowledge say it can do or must '
    "do. Never an expectation about how the call ends or who hangs up. Vary the callers: easy and "
    "hard, calm and difficult, ones that interrupt or pause, ones that test the agent's limits. "
    "Use the language the agent speaks for the goal, the style and the facts. Then call the tool."
)

# How much of each block the writer reads: enough to know the agent, never a whole base.
MOST_CHARS = 6000

TOOL: JsonObject = {
    "name": "write_personas",
    "description": "Hand in the callers.",
    "parameters": {
        "type": "object",
        "properties": {
            "personas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "lower-case words joined by hyphens: in-a-hurry"},
                        "about": {"type": "string", "description": "who they are, one line"},
                        "goal": {"type": "string", "description": "what they want, first person"},
                        "style": {"type": "string", "description": "how they talk"},
                        "facts": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "what they know: their name, a booking number…",
                        },
                        "expects": {"type": "array", "items": {"type": "string"}},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "interrupts": {
                            "type": "number",
                            "description": "share of the agent's answers they talk over, 0-1",
                        },
                        "pause_s": {"type": "number", "description": "seconds of silence before each line, 0 to 5"},
                    },
                    "required": ["name", "goal", "style", "expects"],
                },
            }
        },
        "required": ["personas"],
    },
}

NOT_A_NAME = re.compile(r"[^a-z0-9]+")
# Each row is read alone, so one the writer got wrong leaves the others standing.
ROWS = TypeAdapter(list[object])


class Proposed(BaseModel):
    """One caller as the writer handed it in, before it is a persona."""

    name: str
    about: str = ""
    goal: str
    style: str
    facts: dict[str, str] = Field(default_factory=dict[str, str])
    expects: list[str] = Field(default_factory=list[str])
    tags: list[str] = Field(default_factory=list[str])
    interrupts: float = Field(default=0.0, ge=0.0, le=1.0)
    pause_s: float = Field(default=0.0, ge=0.0, le=5.0)


@dataclass(frozen=True, slots=True)
class Brief:
    """What the writer reads of the agent: its prompt, its tools, what it knows, and more."""

    prompt: str = ""
    # `name: what it does`, one a line.
    tools: tuple[str, ...] = ()
    knowledge: str = ""
    # What the person asking wants the callers to be about.
    about: str = ""
    # A real call's conversation, for callers like its caller.
    call: str = ""
    # A persona of the library, for callers like it, written for this agent.
    template: Persona | None = None


async def write_personas(model: llm.LLM[Never], brief: Brief, n: int) -> tuple[list[Persona], LLMModelUsage | None]:
    """Up to `n` personas for the agent; one the writer got wrong is left out, never guessed."""
    fields, usage = await forced(model, WRITER, _question_of(brief, n), TOOL)
    rows = ROWS.validate_python(fields.get("personas") or [])
    personas = [persona for persona in (_persona_of(row) for row in rows) if persona is not None]
    return _named_apart(personas)[:n], usage


def _question_of(brief: Brief, n: int) -> str:
    blocks = [f"Write {n} callers for this agent."]
    if brief.about:
        blocks.append(f"They are about: {brief.about}")
    if brief.template is not None:
        template = brief.template
        blocks.append(
            f"Each is a version, for this agent, of this caller: {template.goal} "
            f"They talk this way: {template.style} "
            f"They expect: {' '.join(template.expects)}"
        )
    if brief.prompt:
        blocks.append(f"The agent's prompt:\n{brief.prompt[:MOST_CHARS]}")
    if brief.tools:
        blocks.append("The agent's tools:\n" + "\n".join(brief.tools))
    if brief.knowledge:
        blocks.append(f"What the agent knows:\n{brief.knowledge[:MOST_CHARS]}")
    if brief.call:
        blocks.append(f"A real call, whose caller these are like:\n{brief.call[:MOST_CHARS]}")
    return "\n\n".join(blocks)


def _persona_of(row: object) -> Persona | None:
    try:
        proposed = Proposed.model_validate(row)
        return Persona(
            name=NOT_A_NAME.sub("-", proposed.name.lower()).strip("-") or "caller",
            about=proposed.about,
            goal=proposed.goal,
            style=proposed.style,
            facts=proposed.facts,
            expects=tuple(line.strip() for line in proposed.expects if line.strip()),
            tags=tuple(tag.strip() for tag in proposed.tags if tag.strip()),
            behavior=Behavior(interrupts=proposed.interrupts, pause_s=proposed.pause_s),
        )
    except (ValidationError, PydanticValidationError):
        return None


# Two callers the writer named alike would overwrite each other when saved.
def _named_apart(personas: Sequence[Persona]) -> list[Persona]:
    seen: dict[str, int] = {}
    apart: list[Persona] = []
    for persona in personas:
        count = seen.get(persona.name, 0)
        seen[persona.name] = count + 1
        apart.append(persona if not count else replace(persona, name=f"{persona.name}-{count + 1}"))
    return apart
