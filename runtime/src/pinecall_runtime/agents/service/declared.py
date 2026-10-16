"""What an app declares of its agent, laid over the config held: the fields it sends, the settings it fixes."""

import dataclasses
from collections.abc import Mapping
from typing import Any

from pinecall_runtime.agents.declaration import (
    DEFAULT_LAYOUT,
    DEFAULT_TOOL_TIMEOUT_S,
    AgentConfig,
    Docs,
    Greeting,
    Hangup,
    MemoryPolicy,
    PromptBlock,
    ToolSpec,
    Turn,
    Voice,
)
from pinecall_runtime.agents.service.tuning import model_from_wire
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.parts import AgentConfig as Declaration
from pinecall_runtime.wire.parts import GreetingConfig, VoiceConfig

NO_VENDOR = "a voice the class declares names its vendor and the voice: @voice('<vendor>', '<voice>')"


# Sent as null, a setting goes back to the org's; left out, it stays as it was declared before.
def with_app_fields(current: AgentConfig, declaration: Declaration) -> AgentConfig:
    """The agent's config with the fields the app sent in place, and the settings it fixes."""
    sent = declaration.model_fields_set
    changed: dict[str, Any] = _settings_fixed(current, declaration)
    if "prompt" in sent:
        changed["prompt"] = (
            tuple(PromptBlock(block.name, block.region) for block in declaration.prompt)
            if declaration.prompt
            else DEFAULT_LAYOUT
        )
    if "uses_knowledge" in sent:
        changed["uses_knowledge"] = declaration.uses_knowledge
    if "tools" in sent:
        changed["tools"] = tuple(
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                side_effect=tool.side_effect,
                pii=frozenset(tool.pii or ()),
                confirm=tool.confirm,
                announce=tool.announce,
                timeout_s=DEFAULT_TOOL_TIMEOUT_S if tool.timeout_s is None else tool.timeout_s,
            )
            for tool in declaration.tools or ()
        )
    if "state_fields" in sent:
        changed["state_fields"] = {item.name: item.visibility for item in declaration.state_fields or ()}
    if "view" in sent:
        changed["view"] = None if declaration.view is None else declaration.view.name
    if "events" in sent:
        changed["events"] = {item.name: frozenset(item.from_) for item in declaration.events or ()}
    return dataclasses.replace(current, **changed)


def changed_by(declaration: Declaration) -> list[str]:
    """The fields a declaration sets, sorted."""
    return sorted(declaration.model_fields_set)


# A setting the class declares is fixed: the org's settings no longer move it.
def _settings_fixed(current: AgentConfig, declaration: Declaration) -> dict[str, object]:
    converted = _settings_of(declaration)
    changed: dict[str, Any] = {}
    fixed = set(current.fixed)
    for name in declaration.model_fields_set & converted.keys():
        if getattr(declaration, name) is None:
            fixed.discard(name)
            continue
        fixed.add(name)
        field, value = converted[name]
        changed[field] = value
    changed["fixed"] = frozenset(fixed)
    return changed


# Each setting a class may declare, by the declaration's name: the config's field it becomes and
# its value there. A setting not sent is converted too and never used.
def _settings_of(declaration: Declaration) -> dict[str, tuple[str, object]]:
    memory = declaration.memory
    return {
        "language": ("language", declaration.language),
        "voice": ("voice", _voice_of(declaration.voice)),
        "llm": ("llm", model_from_wire(declaration.llm, "llm")),
        "stt": ("stt", model_from_wire(declaration.stt, "stt")),
        "judge": ("judge", model_from_wire(declaration.judge, "llm")),
        "greeting": ("greeting", _greeting_of(declaration.greeting)),
        "hangup": ("hangup", None if declaration.hangup is None else Hangup(declaration.hangup.when)),
        "turn": ("turn", None if declaration.turn is None else Turn(**declaration.turn.model_dump())),
        "says": ("says", {item.word: item.spoken for item in declaration.says or ()}),
        "hears": ("hears", tuple(declaration.hears or ())),
        "knowledge": ("knowledge", None if declaration.knowledge is None else declaration.knowledge.text),
        "docs": ("bases", () if declaration.docs is None else (Docs(**declaration.docs.model_dump()),)),
        "memory": (
            "memory",
            None if memory is None else MemoryPolicy(remember=tuple(memory.remember), forget=tuple(memory.forget)),
        ),
        "record": ("record", declaration.record),
    }


def _greeting_of(wanted: GreetingConfig | None) -> Greeting | None:
    return None if wanted is None else Greeting(**wanted.model_dump())


def _voice_of(wanted: VoiceConfig | None) -> Voice | None:
    if wanted is None:
        return None
    if not wanted.provider or not (wanted.voice_id or wanted.name):
        raise ValidationError(NO_VENDOR)
    return Voice(
        provider=providers.vendor_doing(wanted.provider.lower(), "tts"),
        model=wanted.model,
        voice_id=wanted.voice_id or wanted.name,
        builds=wanted.builds,
        options=_options(wanted.options),
    )


def _options(given: Mapping[str, Any] | None) -> dict[str, Any]:
    return {} if given is None else dict(given)
