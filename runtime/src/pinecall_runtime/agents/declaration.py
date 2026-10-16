"""What an agent declares (prompt, tools, voice, turns) and what the org sets on top of it."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import a_mapping, parse_slug
from pinecall_runtime.wire.parts import (
    DocsMode,
    EndOfTurn,
    EventSource,
    PromptRegion,
    SideEffect,
    Visibility,
)

A_FUNCTION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Written by the platform, never the app, so a knowledge file carries the operator's authority.
KNOWLEDGE_BLOCK = "knowledge"
DEFAULT_CHUNKS_PER_TURN = 8
# The default ends abandoned lines and machine-to-machine loops; 0 is no limit, else 1 to 60 min.
LONGEST_VOICE_CALL_S = 600
SHORTEST_LIMIT_S = 60
LONGEST_LIMIT_S = 3600
NO_LIMIT = 0
LONGEST_TOOL_S = 300
# What a tool is given to answer when it declares no timeout_s.
DEFAULT_TOOL_TIMEOUT_S = 30.0
# The argument the platform adds to every tool: the line the model says as the tool runs.
SAY = "say"

# Unset knobs are None, never "": an empty string reaches the vendor as a value (an empty voice once
# made every call silent).
BLANK = (
    "a blank {field} is not a change: an empty value once silenced a whole line of calls. "
    "Leave the field out to go back to what the app declared."
)


@dataclass(frozen=True, slots=True)
class Voice:
    """The agent's TTS voice."""

    provider: str
    model: str | None = None
    voice_id: str | None = None
    builds: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True)
class Model:
    """An LLM or STT model and its knobs."""

    provider: str
    model: str
    temperature: float | None = None
    builds: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])
    end_of_turn: EndOfTurn | None = None


@dataclass(frozen=True, slots=True)
class Turn:
    """Turn detection and interruption settings."""

    min_interruption_words: int | None = None
    endpointing_ms: int | None = None
    eot_threshold: float | None = None
    eager_eot_threshold: float | None = None
    min_interruption_ms: int | None = None

    def __post_init__(self) -> None:
        for name in ("min_interruption_ms", "endpointing_ms", "min_interruption_words"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValidationError(f"{name} is a count, 0 or more")
        # Deepgram rejects the connection when eager > eot, leaving the call without STT.
        eager, eot = self.eager_eot_threshold, self.eot_threshold
        if eager is not None and eot is not None and eager > eot:
            raise ValidationError(
                f"eager_eot_threshold {self.eager_eot_threshold} is the bar for GUESSING the turn "
                f"is over, so it cannot sit above eot_threshold {self.eot_threshold}"
            )


@dataclass(frozen=True, slots=True)
class Greeting:
    """The opening turn: fixed words (`say`) or an instruction for the model (`reply`)."""

    say: str | None = None
    reply: str | None = None
    allow_interruptions: bool | None = None

    def __post_init__(self) -> None:
        if (self.say is None) == (self.reply is None):
            raise ValidationError(
                "a greeting is one of two things: `say` the words, or `reply` what the model reads first"
            )


@dataclass(frozen=True, slots=True)
class Hangup:
    """Lets the model end the call, with instructions on when."""

    when: str = ""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool as the app declares it, validated on construction."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    side_effect: SideEffect = "read"
    pii: frozenset[str] = frozenset()
    confirm: str | None = None
    announce: str | None = None
    preview: int | None = None
    timeout_s: float = DEFAULT_TOOL_TIMEOUT_S

    def __post_init__(self) -> None:
        if not A_FUNCTION_NAME.match(self.name):
            raise ValidationError(f"a tool name is one word a model can call, not {self.name!r}")
        if not self.description.strip():
            raise ValidationError(f"tool {self.name}: without a description no model can choose it")
        if self.parameters.get("type") != "object":
            raise ValidationError(f"tool {self.name}: parameters are a JSON Schema of type object")
        if self.side_effect == "irreversible" and not self.confirm:
            raise ValidationError(f"tool {self.name}: an irreversible tool needs a confirm template to read back")
        if self.announce is not None and not self.announce.strip():
            raise ValidationError(f"tool {self.name}: an announcement is words the caller hears, or none")
        if SAY in self.parameter_names:
            raise ValidationError(f"tool {self.name}: {SAY!r} is the platform's argument, never a tool's own")
        if unknown := self.pii - self.parameter_names:
            raise ValidationError(f"tool {self.name}: pii names parameters the tool has; unknown: {sorted(unknown)}")
        if self.preview is not None and self.preview < 1:
            raise ValidationError(f"tool {self.name}: a preview shows at least one item")
        if not 0 < self.timeout_s <= LONGEST_TOOL_S:
            raise ValidationError(f"tool {self.name}: timeout_s is seconds above 0, {LONGEST_TOOL_S} at most")

    @property
    def parameter_names(self) -> frozenset[str]:
        """The property names of the parameter schema."""
        properties = self.parameters.get("properties")
        return frozenset(properties) if a_mapping(properties) else frozenset[str]()


@dataclass(frozen=True, slots=True)
class PromptBlock:
    """A named prompt block and its region."""

    name: str
    region: PromptRegion


@dataclass(frozen=True, slots=True)
class Docs:
    """A knowledge base the agent uses, and how results reach the model."""

    base: str
    mode: DocsMode = "retrieved"
    k: int = DEFAULT_CHUNKS_PER_TURN
    min_score: float | None = None

    def __post_init__(self) -> None:
        if not self.base:
            raise ValidationError("docs name the knowledge base they were pushed to")
        if self.k < 1:
            raise ValidationError("docs hand the model at least one chunk")
        if self.min_score is not None and self.min_score < 0:
            raise ValidationError("a fused rank score is never negative; min_score cannot be")


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """What memory keeps about a contact across calls, and what it never keeps."""

    remember: tuple[str, ...] = ()
    forget: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if both := set(self.remember) & set(self.forget):
            raise ValidationError(f"memory cannot both remember and forget {sorted(both)}")


@dataclass(frozen=True, slots=True)
class Tuning:
    """One agent's settings as the org set them; every knob is None until set."""

    voice: str | None = None
    tts: str | None = None
    tts_model: str | None = None
    stt: str | None = None
    llm: str | None = None
    temperature: float | None = None
    end_of_turn: EndOfTurn | None = None
    llm_builds: str | None = None
    llm_options: Mapping[str, Any] | None = None
    stt_builds: str | None = None
    stt_options: Mapping[str, Any] | None = None
    tts_builds: str | None = None
    tts_options: Mapping[str, Any] | None = None
    judge: str | None = None
    judge_builds: str | None = None
    judge_options: Mapping[str, Any] | None = None
    language: str | None = None
    greeting: Greeting | None = None
    hangup: Hangup | None = None
    turn: Turn | None = None
    memory: MemoryPolicy | None = None
    record: bool | None = None
    max_duration_s: int | None = None
    llm_timeout_s: float | None = None
    knowledge: str | None = None
    bases: tuple[Docs, ...] | None = None

    def __post_init__(self) -> None:
        for name in (
            "voice",
            "tts",
            "tts_model",
            "stt",
            "llm",
            "llm_builds",
            "stt_builds",
            "tts_builds",
            "judge",
            "judge_builds",
            "language",
            "knowledge",
        ):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValidationError(BLANK.format(field=name))
        if self.max_duration_s is not None:
            check_call_limit(self.max_duration_s)
        if self.llm_timeout_s is not None and self.llm_timeout_s <= 0:
            raise ValidationError("llm_timeout_s is a positive number of seconds")
        if self.temperature is not None and self.temperature < 0:
            raise ValidationError("temperature is a number from 0, in the model vendor's range")


@dataclass(frozen=True, slots=True)
class Lexicon:
    """An agent's lexicon: TTS pronunciations and STT keyterms."""

    said: Mapping[str, str] = field(default_factory=dict[str, str])
    heard: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        check_pronunciations(self.said, "the lexicon")
        if any(not word.strip() for word in self.heard):
            raise ValidationError("the lexicon: a word the ears must know is not blank")


@dataclass(frozen=True, slots=True)
class Version[T]:
    """A stored version of a value, with its holder, number, author and timestamp."""

    holder: str
    version: int
    author: str
    note: str | None
    set_at: datetime
    value: T


@dataclass(frozen=True, slots=True)
class Versions:
    """Tuning and lexicon versions a call was built on; None where nothing was set."""

    config: int | None = None
    lexicon: int | None = None


DEFAULT_LAYOUT: tuple[PromptBlock, ...] = (
    PromptBlock("identity", "static"),
    PromptBlock(KNOWLEDGE_BLOCK, "static"),
    PromptBlock("tools", "static"),
    PromptBlock("view", "dynamic"),
)


# Field names match the wire's AgentConfig.
@dataclass(frozen=True, slots=True)
class AgentConfig:
    """An agent's resolved declaration: what the app declared, with the org's settings applied."""

    slug: str
    name: str | None = None
    prompt: tuple[PromptBlock, ...] = DEFAULT_LAYOUT
    greeting: Greeting | None = None
    language: str | None = None
    voice: Voice | None = None
    llm: Model | None = None
    stt: Model | None = None
    judge: Model | None = None
    turn: Turn | None = None
    says: Mapping[str, str] = field(default_factory=dict[str, str])
    hears: tuple[str, ...] = ()
    knowledge: str | None = None
    bases: tuple[Docs, ...] = ()
    uses_knowledge: bool = False
    memory: MemoryPolicy | None = None
    hangup: Hangup | None = None
    record: bool = True
    max_duration_s: int = LONGEST_VOICE_CALL_S
    llm_timeout_s: float | None = None
    tools: tuple[ToolSpec, ...] = ()
    state_fields: Mapping[str, Visibility] = field(default_factory=dict[str, Visibility])
    view: str | None = None
    events: Mapping[str, frozenset[EventSource]] = field(default_factory=dict[str, frozenset[EventSource]])
    # The settings the class itself declares, by their wire names: each wins over the org's.
    fixed: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        parse_slug(self.slug)
        names = [tool.name for tool in self.tools]
        if repeated := {name for name in names if names.count(name) > 1}:
            raise ValidationError(f"agent {self.slug}: tool names repeat: {sorted(repeated)}")
        blocks = [block.name for block in self.prompt]
        if repeated := {name for name in blocks if blocks.count(name) > 1}:
            raise ValidationError(f"agent {self.slug}: prompt block names repeat: {sorted(repeated)}")
        check_pronunciations(self.says, f"agent {self.slug}")
        check_call_limit(self.max_duration_s)
        for event, sources in self.events.items():
            if not event or not sources:
                raise ValidationError(f"agent {self.slug}: event {event!r} names who may send it: app, participant")

    def visibility_of(self, state_field: str) -> Visibility:
        """A state field's visibility, tenant unless declared."""
        return self.state_fields.get(state_field, "tenant")

    def accepts(self, event: str, source: EventSource) -> bool:
        """Whether the event may be sent by this source."""
        return source in self.events.get(event, frozenset())

    @property
    def tools_by_name(self) -> Mapping[str, ToolSpec]:
        """The tools keyed by name."""
        return {tool.name: tool for tool in self.tools}


def block_hash(text: str) -> str:
    """A block of the prompt as the log names it: the sha256 of its text."""
    return sha256(text.encode()).hexdigest()


def check_call_limit(seconds: int) -> None:
    """ValidationError unless seconds is 0 or between 60 and 3600."""
    if seconds != NO_LIMIT and not SHORTEST_LIMIT_S <= seconds <= LONGEST_LIMIT_S:
        raise ValidationError(
            f"max_duration_s {seconds}: 0 for no limit, or {SHORTEST_LIMIT_S} to {LONGEST_LIMIT_S} seconds"
        )


def check_pronunciations(says: Mapping[str, str], owner: str) -> None:
    """ValidationError when a word or its spoken form is blank."""
    if blank := {word for word, spoken in says.items() if not word or not spoken}:
        raise ValidationError(f"{owner}: a pronunciation is a word and how it is said: {sorted(blank)}")


type Modality = Literal["llm", "stt", "tts"]
