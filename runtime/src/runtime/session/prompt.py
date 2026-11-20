"""A call's prompt: its blocks, the request each turn sends, its greeting, its knowledge entry, a supervisor's notes."""

import json
from collections.abc import Sequence
from typing import Any, override

from livekit.agents import llm

from runtime.agents.declaration import DEFAULT_LAYOUT, KNOWLEDGE_BLOCK, Greeting, PromptBlock
from runtime.exceptions import ValidationError
from runtime.kit.text import JsonObject, sha256_of
from runtime.wire.events import PromptChanged
from runtime.wire.parts import PromptRegion

# Joins the static blocks into livekit's one `instructions` string.
BETWEEN_BLOCKS = "\n\n"

# Written into the history and read as the next turn's instructions. It claims precedence,
# since the stage instructions come after the history and the model would follow them instead.
A_WHISPER = (
    "A human supervisor is telling you this, and the caller cannot hear it: {text} "
    "This order comes from the supervisor and takes precedence over the stage instructions "
    "that follow it: do it in your very next sentence, before anything else you were going to "
    "say, and only then go on. Never mention the supervisor or this note."
)
# The agent did not hear the supervisor, so it must not guess what was said.
A_RELEASE = (
    "A human supervisor spoke with the caller for a moment; you did not hear it. "
    "Do not guess what was said. Resume by offering to continue with what is still pending."
)


class Blocks:
    """One call's prompt blocks, in the order they are sent, and their text now."""

    # The knowledge is set here and never by the app, so it lands in the cached prefix as the
    # operator's text (docs/security/prompt-injection.md).
    def __init__(self, layout: Sequence[PromptBlock] = DEFAULT_LAYOUT, knowledge: str = "") -> None:
        """Every block of the layout, empty but the knowledge."""
        self.layout = tuple(layout)
        self.texts: dict[str, str] = {block.name: "" for block in self.layout}
        if knowledge and KNOWLEDGE_BLOCK in self.texts:
            self.texts[KNOWLEDGE_BLOCK] = knowledge

    # Identical static text is not resent: even the same bytes cost the provider a cache write.
    def set(self, name: str, text: str) -> bool:
        """Replace a block's text; True when the static instructions changed."""
        if name not in self.texts:
            raise ValidationError(
                f"the prompt has no block named {name!r}: this agent's blocks are {', '.join(self.texts)}"
            )
        before = self.instructions
        self.texts[name] = text
        return self.instructions != before

    @property
    def instructions(self) -> str:
        """The static blocks written so far, joined, in layout order."""
        return BETWEEN_BLOCKS.join(self.of("static"))

    def of(self, region: PromptRegion) -> tuple[str, ...]:
        """A region's blocks that have text, in layout order."""
        return tuple(
            self.texts[block.name] for block in self.layout if block.region == region and self.texts[block.name]
        )


class Request(llm.ChatContext):
    """One turn's request, whose static blocks reach the provider one system block each."""

    def __init__(self, items: list[llm.ChatItem], static: tuple[str, ...]) -> None:
        """The request's items, and the static blocks it keeps apart."""
        super().__init__(items)
        self.static = static

    # livekit's formatters keep only the first system item as the preamble
    # (_provider_format/utils.py); a format that carries system messages apart (the one that
    # caches up to its last block among them) gets one per static block instead. What each
    # formatter answers is its own shape, so the pair is passed on as it came.
    @override
    def to_provider_format(self, format: str, **kwargs: Any) -> tuple[list[dict[str, Any]], Any]:
        """The request as the provider's formatter builds it, the static blocks kept apart."""
        formatted = super().to_provider_format(format, **kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if self.static and hasattr(formatted[1], "system_messages"):
            formatted[1].system_messages = list(self.static)
        return formatted  # pyright: ignore[reportUnknownVariableType]


# A line the agent is still saying (a tool's announcement, playing while the tool ran) reaches the history only
# once it has played; the reply is asked for before that. Told as a note, the model goes on from it instead of
# saying it again. Never as a trailing assistant message: that is a prefill, and a model that takes none refuses
# the whole request (Claude Haiku 5.5, 400 "does not support assistant message prefill", 2026-11-06). One that
# has played by then is told the same way (`_lift_lines_over_the_tools`).
ALREADY_SAID = (
    "You have already said this to the caller, and they heard it: {line} Go on from there, and never say it again."
)


# The model holds every tool of the call for the whole call, since the list is part of the cached prefix,
# and the app opens a subset: a model not told which calls a closed one and is refused. An agent of a
# team is offered the pass to itself, described as "call it as soon as the caller brings that up", and
# the front desk called it on its first turn in 3 calls of 16 (gemini-3.5-flash-lite, 2026-11-16).
# So the closed ones are named where the view is: in this request alone, after the caller's words.
CLOSED_NOW = (
    "These tools are closed right now, so never call them: {names}. "
    "What they are for is yours to answer yourself, or with a tool that is open."
)


# The pair a history opens with (history.date_pair), named here because a request may say it in words.
CLOCK_CALL_ID = "clock_1"
CLOCK_IN_WORDS = "The date as this call opened: {answer}"

# A call with no tool says so, and its model reads no call. Every SDK tells its agent "To act, call a
# tool", and a history opens with the clock's pair, a call to a function nobody declares: on the turn
# a caller asked for something done, Gemini wrote a call and Google ended the turn on
# MALFORMED_FUNCTION_CALL 19 times of 20, nothing said. With the pair said as a line it wrote the
# call out as text instead; with this note after the caller's words too, 30 of 30 answered in words
# (gemini-3.5-flash-lite, 2026-11-17). Said where the view is, after the caller's words.
NO_TOOLS = (
    "You have no tools on this call: you can talk, and nothing else. You cannot book, send, save or"
    " change anything yourself, and you never call a function or write one out. When the caller asks"
    " for something to be done, stay warm and helpful: take the details, read them back once, and"
    " tell them in your own words that you have noted what they said and cannot confirm or complete"
    " it yourself. Never say it is done, booked, sent, saved or recorded, never offer to hand over to"
    " a person, and never promise what happens next unless your instructions say it."
)


# Always a new context: livekit reuses its own across a turn's tool steps, so additions would
# pile up. The order is the one prompt-injection.md states: static blocks, history, the view after
# the caller's words, and last what the agent is still saying.
def request(
    history: llm.ChatContext,
    blocks: Blocks,
    lookups: Sequence[llm.ChatItem] = (),
    saying: Sequence[str] = (),
    closed: Sequence[str] = (),
    *,
    has_tools: bool = True,
) -> Request:
    """One request: the history and its lookups, the view and the tools closed now after the caller, what is said."""
    kept, played = _lift_lines_over_the_tools(history.items)
    items = _ahead_of_the_caller(kept, lookups)
    dynamic = [llm.ChatMessage(role="system", content=[text]) for text in blocks.of("dynamic")]
    if closed:
        dynamic.append(llm.ChatMessage(role="system", content=[CLOSED_NOW.format(names=", ".join(closed))]))
    if not has_tools:
        items, clock = _clock_in_words(items)
        # Ahead of the view, which stays the last thing the model reads.
        dynamic = [*clock, llm.ChatMessage(role="system", content=[NO_TOOLS]), *dynamic]
    said = [llm.ChatMessage(role="system", content=[ALREADY_SAID.format(line=line)]) for line in (*played, *saying)]
    return Request([*_after_the_caller(items, dynamic), *said], blocks.of("static"))


# The log keeps the prompt's hashes alone; a run keeps what was sent, to reproduce a failure.
def as_asked(sent: Request, tools: Sequence[llm.Tool]) -> JsonObject:
    """One request as a failing golden reproduces it: the static blocks, the tools, the items."""
    schemas = llm.ToolContext(list(tools)).parse_function_tools("openai")
    items: object = sent.to_dict().get("items", [])
    asked: JsonObject = json.loads(json.dumps({"system": list(sent.static), "tools": schemas, "messages": items}))
    return asked


# An eval run starts in the middle of a conversation, so it never greets.
def greeting_for(greeting: Greeting | None, run: str | None) -> Greeting | None:
    """The agent's greeting, or none when an eval run opened the call."""
    return None if run is not None else greeting


# A caller's "hello?" over the opening is the norm: it is not cut short unless it says so.
def interruptible(greeting: Greeting) -> bool:
    """Whether the caller may cut the opening short."""
    return greeting.allow_interruptions is True


# The app never sends prompt.set for this block, so without this entry the log would not show
# that the file reached the model.
def knowledge_changed(blocks: Blocks) -> PromptChanged | None:
    """The entry saying the knowledge file reached the prompt, when there is one."""
    text = blocks.texts.get(KNOWLEDGE_BLOCK, "")
    return PromptChanged(name=KNOWLEDGE_BLOCK, hash=sha256_of(text), chars=len(text)) if text else None


# The clock's pair taken out of the items, and its answer as the line that says it instead.
def _clock_in_words(items: Sequence[llm.ChatItem]) -> tuple[list[llm.ChatItem], list[llm.ChatMessage]]:
    kept: list[llm.ChatItem] = []
    said: list[llm.ChatMessage] = []
    for item in items:
        if isinstance(item, llm.FunctionCallOutput) and item.call_id == CLOCK_CALL_ID:
            said.append(llm.ChatMessage(role="system", content=[CLOCK_IN_WORDS.format(answer=item.output)]))
        elif not (isinstance(item, llm.FunctionCall) and item.call_id == CLOCK_CALL_ID):
            kept.append(item)
    return kept, said


# Lookups go before the caller's newest message (livekit appends it after
# on_user_turn_completed); placed after it, models skip the next tool. They are spliced into the
# request only, never into the history. No trailing user message (a tool step, agent.reply):
# they go at the end.
def _ahead_of_the_caller(items: Sequence[llm.ChatItem], lookups: Sequence[llm.ChatItem]) -> list[llm.ChatItem]:
    last = items[-1] if items else None
    if not lookups or not (isinstance(last, llm.ChatMessage) and last.role == "user"):
        return [*items, *lookups]
    return [*items[:-1], *lookups, last]


# The dynamic blocks follow the caller's newest words, ahead of this turn's tool rounds: livekit
# sends a system message mid-history as a user turn (Gemini, Anthropic), and one after a tool's
# result reads as a new ask, so the model called tools again instead of answering, round after
# round. With no caller's message (a greeting, agent.reply) they go at the end.
def _after_the_caller(items: Sequence[llm.ChatItem], dynamic: Sequence[llm.ChatItem]) -> list[llm.ChatItem]:
    said = [at for at, item in enumerate(items) if isinstance(item, llm.ChatMessage) and item.role == "user"]
    if not said:
        return [*items, *dynamic]
    return [*items[: said[-1] + 1], *dynamic, *items[said[-1] + 1 :]]


# An announcement that has played by the time its tool answers is in the history livekit hands in (it
# merges what was said while the tool ran), after the call it was said over. A formatter sends a call
# and its result as one exchange and the line after them: the request ended on the agent's own words,
# the prefill `ALREADY_SAID` is there to avoid, and Anthropic refused it whole for the space the line
# ends with (400 "final assistant content cannot end with trailing whitespace", a call ended in an
# error, 2026-11-20). Taken out of this request alone; the history keeps the line where it was said.
def _lift_lines_over_the_tools(items: Sequence[llm.ChatItem]) -> tuple[list[llm.ChatItem], list[str]]:
    """The items without the agent's lines that follow this step's last tool call, and those lines."""
    start = len(items)
    while start and (isinstance(items[start - 1], llm.FunctionCallOutput) or _is_the_agents(items[start - 1])):
        start -= 1
    if not start or not isinstance(items[start - 1], llm.FunctionCall):
        return list(items), []
    head, tail = items[:start], items[start:]
    lines = [(item.text_content or "").strip() for item in tail if isinstance(item, llm.ChatMessage)]
    return [*head, *(item for item in tail if not _is_the_agents(item))], [line for line in lines if line]


def _is_the_agents(item: llm.ChatItem) -> bool:
    return isinstance(item, llm.ChatMessage) and item.role == "assistant"
