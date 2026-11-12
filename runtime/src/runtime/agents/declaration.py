"""What an agent's class declares: its prompt, its tools, its turns and its words, and the declaration whole."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from runtime.exceptions import ValidationError
from runtime.kit.text import A_FUNCTION_NAME, a_mapping, parse_slug
from runtime.kit.time import parse_zone
from runtime.providers.stage import Model, Voice
from runtime.wire.declaration import (
    IDLE_AFTER_S,
    IDLE_TIMES,
    HoldConfig,
    JudgesDeclared,
    MonitorDeclared,
    PersonasDeclared,
    WidgetLook,
)
from runtime.wire.parts import DocsMode, EventSource, PromptRegion, SideEffect, Visibility

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
# When a tool that has a line for a long wait says it, unless it names its own moment.
DELAYED_AFTER_S = 5.0
# The ears that take these bars take them only inside these bands and refuse the connection
# outside one, so the call runs deaf: a setting and a declaration are held to them alike.
TURN_BANDS = {"eot_threshold": (0.5, 0.9), "eager_eot_threshold": (0.3, 0.9)}
# The argument the platform adds to every tool: the line the model says as the tool runs.
SAY = "say"
# The quiet an agent may be set to bear: a silence timeout ends the call, an idle line asks first.
SHORTEST_SILENCE_S = 5
LONGEST_SILENCE_S = 3600
SHORTEST_IDLE_S = 5.0
LONGEST_IDLE_S = 60.0
MOST_IDLE_TIMES = 10
NOT_A_TIMEOUT = "llm_timeout_s is a positive number of seconds"
OUT_OF_ORDER = "the prompt is every static block, then every dynamic one: static {block} comes after a dynamic one"

# An unset field is None, never "": an empty string reaches the vendor as a value (an empty voice once
# made every call silent).
BLANK = (
    "a blank {field} is not a change: an empty value once silenced a whole line of calls. "
    "Leave the field out to go back to what the app declared."
)


# A value here is built free and checked where it is written. Until 2026-11 each refused in its own
# constructor, and the same constructor ran where a stored row, another gateway's share or a call's
# opening was read: a rule made stricter later left every older row that broke it unreadable, and no
# call of that agent could be built. The `check_…` functions below are what a write calls.
@dataclass(frozen=True, slots=True)
class Turn:
    """Turn detection and interruption settings."""

    min_interruption_words: int | None = None
    endpointing_ms: int | None = None
    eot_threshold: float | None = None
    eager_eot_threshold: float | None = None
    min_interruption_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Greeting:
    """The opening turn: fixed words (`say`) or an instruction for the model (`reply`)."""

    say: str | None = None
    reply: str | None = None
    allow_interruptions: bool | None = None


@dataclass(frozen=True, slots=True)
class Hangup:
    """Lets the model end the call, with instructions on when."""

    when: str = ""


@dataclass(frozen=True, slots=True)
class Idle:
    """What the agent says when the caller has gone quiet: its lines, after how long, how many times."""

    says: tuple[str, ...]
    after_s: float = IDLE_AFTER_S
    times: int = IDLE_TIMES


@dataclass(frozen=True, slots=True)
class Voicemail:
    """Lets the model tell a machine from a person on a call it placed; with no message it just hangs up."""

    message: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool as the app declares it."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    side_effect: SideEffect = "read"
    pii: frozenset[str] = frozenset()
    confirm: str | None = None
    announce: str | None = None
    # Said when the wait has grown long, and when the tool failed, before the model reads why.
    delayed: str | None = None
    delayed_after_s: float = DELAYED_AFTER_S
    failed: str | None = None
    preview: int | None = None
    timeout_s: float = DEFAULT_TOOL_TIMEOUT_S
    # Runs as the model calls it, its words still playing, and asks for no answer (wire/parts.py).
    quiet: bool = False

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


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """What memory keeps about a contact across calls, and what it never keeps."""

    remember: tuple[str, ...] = ()
    forget: tuple[str, ...] = ()


DEFAULT_LAYOUT: tuple[PromptBlock, ...] = (
    PromptBlock("identity", "static"),
    PromptBlock(KNOWLEDGE_BLOCK, "static"),
    PromptBlock("tools", "static"),
    PromptBlock("view", "dynamic"),
)


# One type for the two states it has: as the class declared it, where `fixed` says what the class holds,
# and with the org's settings under it, as a call runs it. Two types would be the same forty fields twice.
@dataclass(frozen=True, slots=True)
class Declaration:
    """An agent as its class declares it, or with the org's settings laid under what the class fixes."""

    slug: str
    prompt: tuple[PromptBlock, ...] = DEFAULT_LAYOUT
    greeting: Greeting | None = None
    language: str | None = None
    # The IANA zone the agent's day and clock are read in; unset, the gateway's own.
    timezone: str | None = None
    voice: Voice | None = None
    llm: Model | None = None
    # A model that hears and speaks itself: a voice call runs on it alone, a written call on `llm`.
    realtime: Model | None = None
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
    silence_timeout_s: int | None = None
    idle: Idle | None = None
    voicemail: Voicemail | None = None
    stt_fallbacks: tuple[Model, ...] = ()
    tts_fallbacks: tuple[Model, ...] = ()
    tools: tuple[ToolSpec, ...] = ()
    state_fields: Mapping[str, Visibility] = field(default_factory=dict[str, Visibility])
    view: str | None = None
    events: Mapping[str, frozenset[EventSource]] = field(default_factory=dict[str, frozenset[EventSource]])
    # The judges and the personas the class owns, as the wire carried them; None: the org writes them.
    judges: JudgesDeclared | None = None
    personas: PersonasDeclared | None = None
    # The hold melody and the widget's look the class owns, as the wire carried them; None: the org sets them.
    hold: HoldConfig | None = None
    widget: WidgetLook | None = None
    # The numbers the class watches, as the wire carried them; None: the org's monitors alone.
    monitors: tuple[MonitorDeclared, ...] | None = None
    # The settings the class itself declares, by the names it declares them under: each wins over the org's.
    fixed: frozenset[str] = frozenset()

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


# What an endpoint is handed for the slug in its path (`auth.TheAgent`): the agent is the org's, and its
# declaration is the one a call in the scope is built from, found one way (`declaration_of`).
@dataclass(frozen=True, slots=True)
class Agent:
    """An agent of an org by its slug, and what its class declares in the scope asked; None where none declared it."""

    slug: str
    declaration: Declaration | None = None

    @property
    def fixed(self) -> frozenset[str]:
        """The settings its class declares itself, by the names it declares them under."""
        return frozenset[str]() if self.declaration is None else self.declaration.fixed

    @property
    def whole(self) -> Declaration:
        """What a call is built from: its class's declaration, or a bare one where no class declared it."""
        return Declaration(slug=self.slug) if self.declaration is None else self.declaration


# ── what a write refuses ──


def check_turn(turn: Turn) -> None:
    """Refuse a turn whose counts are negative, whose bars sit outside their band, or whose guess sits above its bar."""
    for name in ("min_interruption_ms", "endpointing_ms", "min_interruption_words"):
        value = getattr(turn, name)
        if value is not None and value < 0:
            raise ValidationError(f"{name} is a count, 0 or more")
    for bar, (low, high) in TURN_BANDS.items():
        value = getattr(turn, bar)
        if value is not None and not low <= value <= high:
            raise ValidationError(f"{bar} {value} is outside {low} to {high}, the band the ears take it in")
    # Deepgram rejects the connection when eager > eot, leaving the call without STT.
    eager, eot = turn.eager_eot_threshold, turn.eot_threshold
    if eager is not None and eot is not None and eager > eot:
        raise ValidationError(
            f"eager_eot_threshold {turn.eager_eot_threshold} is the bar for GUESSING the turn "
            f"is over, so it cannot sit above eot_threshold {turn.eot_threshold}"
        )


def check_greeting(greeting: Greeting) -> None:
    """Refuse a greeting that is both of its two things, or neither."""
    if (greeting.say is None) == (greeting.reply is None):
        raise ValidationError("a greeting is one of two things: `say` the words, or `reply` what the model reads first")


def check_idle(idle: Idle) -> None:
    """Refuse idle lines that are blank, said too soon or too late, or too many times."""
    if not idle.says or any(not line.strip() for line in idle.says):
        raise ValidationError("idle lines are words the caller hears: at least one, none blank")
    if not SHORTEST_IDLE_S <= idle.after_s <= LONGEST_IDLE_S:
        raise ValidationError(f"idle after_s is {SHORTEST_IDLE_S:g} to {LONGEST_IDLE_S:g} seconds")
    if not 1 <= idle.times <= MOST_IDLE_TIMES:
        raise ValidationError(f"idle times is 1 to {MOST_IDLE_TIMES}")


def check_voicemail(voicemail: Voicemail) -> None:
    """Refuse a voicemail whose message is blank."""
    if voicemail.message is not None and not voicemail.message.strip():
        raise ValidationError(BLANK.format(field="voicemail message"))


def check_tool(tool: ToolSpec) -> None:
    """Refuse a tool no model could call, or one whose lines, timings or parameters break its own rules."""
    if not A_FUNCTION_NAME.match(tool.name):
        raise ValidationError(f"a tool name is one word a model can call, not {tool.name!r}")
    if not tool.description.strip():
        raise ValidationError(f"tool {tool.name}: without a description no model can choose it")
    if tool.parameters.get("type") != "object":
        raise ValidationError(f"tool {tool.name}: parameters are a JSON Schema of type object")
    if tool.side_effect == "irreversible" and not tool.confirm:
        raise ValidationError(f"tool {tool.name}: an irreversible tool needs a confirm template to read back")
    for what, line in (("announcement", tool.announce), ("delayed", tool.delayed), ("failed", tool.failed)):
        if line is not None and not line.strip():
            raise ValidationError(f"tool {tool.name}: {what} is words the caller hears, or none")
    if not 0 < tool.delayed_after_s <= LONGEST_TOOL_S:
        raise ValidationError(f"tool {tool.name}: delayed_after_s is seconds above 0, {LONGEST_TOOL_S} at most")
    if SAY in tool.parameter_names:
        raise ValidationError(f"tool {tool.name}: {SAY!r} is the platform's argument, never a tool's own")
    if unknown := tool.pii - tool.parameter_names:
        raise ValidationError(f"tool {tool.name}: pii names parameters the tool has; unknown: {sorted(unknown)}")
    if tool.preview is not None and tool.preview < 1:
        raise ValidationError(f"tool {tool.name}: a preview shows at least one item")
    if not 0 < tool.timeout_s <= LONGEST_TOOL_S:
        raise ValidationError(f"tool {tool.name}: timeout_s is seconds above 0, {LONGEST_TOOL_S} at most")


def check_docs(docs: Docs) -> None:
    """Refuse docs that name no base, hand the model no chunk, or set a negative bar."""
    if not docs.base:
        raise ValidationError("docs name the knowledge base they were pushed to")
    if docs.k < 1:
        raise ValidationError("docs hand the model at least one chunk")
    if docs.min_score is not None and docs.min_score < 0:
        raise ValidationError("a fused rank score is never negative; min_score cannot be")


def check_memory(memory: MemoryPolicy) -> None:
    """Refuse a memory told to remember and to forget the same thing."""
    if both := set(memory.remember) & set(memory.forget):
        raise ValidationError(f"memory cannot both remember and forget {sorted(both)}")


def check_silence(seconds: int) -> None:
    """Refuse a silence timeout outside what a call may be set to bear."""
    if not SHORTEST_SILENCE_S <= seconds <= LONGEST_SILENCE_S:
        raise ValidationError(f"silence_timeout_s is {SHORTEST_SILENCE_S} to {LONGEST_SILENCE_S} seconds")


def check_call_limit(seconds: int) -> None:
    """Refuse a call limit that is neither 0 nor between 60 and 3600 seconds."""
    if seconds != NO_LIMIT and not SHORTEST_LIMIT_S <= seconds <= LONGEST_LIMIT_S:
        raise ValidationError(
            f"max_duration_s {seconds}: 0 for no limit, or {SHORTEST_LIMIT_S} to {LONGEST_LIMIT_S} seconds"
        )


def check_pronunciations(says: Mapping[str, str], owner: str) -> None:
    """Refuse a word or a spoken form that is blank."""
    if blank := {word for word, spoken in says.items() if not word or not spoken}:
        raise ValidationError(f"{owner}: a pronunciation is a word and how it is said: {sorted(blank)}")


# The parts an org's settings set too are checked by the same functions there (`settings.check_settings`).
def check_parts(
    *,
    turn: Turn | None,
    greeting: Greeting | None,
    idle: Idle | None,
    voicemail: Voicemail | None,
    memory: MemoryPolicy | None,
    bases: tuple[Docs, ...],
) -> None:
    """Refuse the parts a declaration and an org's settings share, each by its own rule."""
    if turn is not None:
        check_turn(turn)
    if greeting is not None:
        check_greeting(greeting)
    if idle is not None:
        check_idle(idle)
    if voicemail is not None:
        check_voicemail(voicemail)
    if memory is not None:
        check_memory(memory)
    for docs in bases:
        check_docs(docs)


# The static blocks are the cached prefix: one after a dynamic block would be re-sent on every turn,
# and the cache would never hold.
def check_layout(slug: str, layout: tuple[PromptBlock, ...]) -> None:
    """Refuse a prompt whose block names repeat, or with a static block after a dynamic one."""
    blocks = [block.name for block in layout]
    if repeated := {name for name in blocks if blocks.count(name) > 1}:
        raise ValidationError(f"agent {slug}: prompt block names repeat: {sorted(repeated)}")
    regions = [block.region for block in layout]
    if "dynamic" in regions and "static" in regions[regions.index("dynamic") :]:
        late = next(block.name for block in layout[regions.index("dynamic") :] if block.region == "static")
        raise ValidationError(OUT_OF_ORDER.format(block=late))


def check_words(declaration: Declaration) -> None:
    """Refuse a declaration by its own words alone: its slug, its tools, its prompt, its limits, its parts."""
    slug = declaration.slug
    parse_slug(slug)
    names = [tool.name for tool in declaration.tools]
    if repeated := {name for name in names if names.count(name) > 1}:
        raise ValidationError(f"agent {slug}: tool names repeat: {sorted(repeated)}")
    for tool in declaration.tools:
        check_tool(tool)
    check_layout(slug, declaration.prompt)
    check_pronunciations(declaration.says, f"agent {slug}")
    check_call_limit(declaration.max_duration_s)
    if declaration.timezone is not None:
        parse_zone(declaration.timezone)
    if declaration.silence_timeout_s is not None:
        check_silence(declaration.silence_timeout_s)
    if declaration.llm_timeout_s is not None and declaration.llm_timeout_s <= 0:
        raise ValidationError(NOT_A_TIMEOUT)
    for event, sources in declaration.events.items():
        if not event or not sources:
            raise ValidationError(f"agent {slug}: event {event!r} names who may send it: app, participant")
    check_parts(
        turn=declaration.turn,
        greeting=declaration.greeting,
        idle=declaration.idle,
        voicemail=declaration.voicemail,
        memory=declaration.memory,
        bases=declaration.bases,
    )
