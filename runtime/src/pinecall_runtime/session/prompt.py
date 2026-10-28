"""A call's prompt: its blocks, the request each turn sends, its greeting, its knowledge entry."""

import json
from collections.abc import Sequence
from typing import cast, override

from livekit.agents import llm

from pinecall_runtime.agents.declaration import (
    DEFAULT_LAYOUT,
    KNOWLEDGE_BLOCK,
    Greeting,
    PromptBlock,
    block_hash,
)
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.events import PromptChanged
from pinecall_runtime.wire.parts import PromptRegion

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
    # caches up to its last block among them) gets one per static block instead.
    @override
    def to_provider_format(  # type: ignore[override]  # pyright: ignore[reportIncompatibleMethodOverride]
        self, format: str, **kwargs: object
    ) -> tuple[list[dict[str, object]], object]:
        """The request as the provider's formatter builds it, the static blocks kept apart."""
        formatted = super().to_provider_format(format, **kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if self.static and hasattr(formatted[1], "system_messages"):
            formatted[1].system_messages = list(self.static)
        return formatted  # pyright: ignore[reportUnknownVariableType]


# Always a new context: livekit reuses its own across a turn's tool steps, so additions would
# pile up. The order is the one prompt-injection.md states: static blocks, history, the view after
# the caller's words.
def request(
    history: llm.ChatContext, blocks: Blocks, lookups: Sequence[llm.ChatItem] = (), saying: Sequence[str] = ()
) -> Request:
    """One request: the history with the lookups spliced in, the dynamic blocks after the caller, what is said last."""
    items = _ahead_of_the_caller(history.items, lookups)
    dynamic = [llm.ChatMessage(role="system", content=[text]) for text in blocks.of("dynamic")]
    # A line the agent is still saying (a tool's announcement, playing while the tool ran) reaches the history only
    # once it has played; the reply is asked for before that. Sent as said, the model goes on from it instead of
    # saying it again.
    said = [llm.ChatMessage(role="assistant", content=[line]) for line in saying]
    return Request([*_after_the_caller(items, dynamic), *said], blocks.of("static"))


# The log keeps the prompt's hashes alone; a run keeps what was sent, to reproduce a failure.
def as_asked(sent: Request, tools: Sequence[llm.Tool]) -> JsonObject:
    """One request as a failing golden reproduces it: the static blocks, the tools, the items."""
    schemas = llm.ToolContext(list(tools)).parse_function_tools("openai")
    items: object = sent.to_dict().get("items", [])
    asked = {"system": list(sent.static), "tools": schemas, "messages": items}
    return cast(JsonObject, json.loads(json.dumps(asked)))


# An eval run starts in the middle of a conversation, so it never greets.
def greeting_for(greeting: Greeting | None, run: str | None) -> Greeting | None:
    """The declared greeting, or none when an eval run opened the call."""
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
    return PromptChanged(name=KNOWLEDGE_BLOCK, hash=block_hash(text), chars=len(text)) if text else None


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
