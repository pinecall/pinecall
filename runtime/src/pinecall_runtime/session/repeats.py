"""What the agent said since the caller last spoke, sentence by sentence, so a tool's round never says one again."""

import re
from collections.abc import AsyncIterable, AsyncIterator

from livekit.agents import llm

type Piece = llm.ChatChunk | str

# A sentence ends at its stop and the space after it; a line with no stop is one sentence.
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _plain(text: str) -> str:
    return " ".join(text.lower().split())


def text_of(piece: Piece) -> str:
    """The words a piece of the model's answer carries; none for a tool call alone."""
    if isinstance(piece, str):
        return piece
    return (piece.delta.content or "") if piece.delta else ""


def _wordless(piece: Piece) -> Piece:
    if isinstance(piece, str) or piece.delta is None or not piece.delta.content:
        return piece
    return piece.model_copy(update={"delta": piece.delta.model_copy(update={"content": None})})


def _calls_a_tool(piece: Piece) -> bool:
    return not isinstance(piece, str) and piece.delta is not None and bool(piece.delta.tool_calls)


class SaidThisTurn:
    """The sentences the agent said since the caller last spoke: its own words and the tools' announcements."""

    def __init__(self) -> None:
        self.sentences: set[str] = set()

    def clear(self) -> None:
        """The caller spoke: a sentence may be said again."""
        self.sentences.clear()

    def say(self, text: str) -> None:
        """Keep every sentence of words the agent said."""
        self.sentences.update(plain for one in SENTENCE_END.split(text) if (plain := _plain(one)))

    def may_be_said_again(self, text: str) -> bool:
        """Whether these words could still grow into a sentence already said."""
        plain = _plain(text)
        return bool(plain) and any(one.startswith(plain) for one in self.sentences)

    def said(self, text: str) -> bool:
        """Whether these words are a sentence already said, whole."""
        return _plain(text) in self.sentences


# A model chaining tools in one answer writes its line again in each round ("Let me note that
# down." before one tool, then before the next): the words that open a round are held while they
# could still be a sentence said this turn, dropped once they are one, and let through as soon as
# they are not. A reply that says something new loses nothing but the time of its first words.
async def unrepeated(pieces: AsyncIterable[Piece], said: SaidThisTurn) -> AsyncIterator[Piece]:
    """The model's answer without a sentence the agent already said since the caller last spoke."""
    held: list[Piece] = []
    async for piece in pieces:
        if _calls_a_tool(piece) or not text_of(piece):
            # The round's words end here: said already, they go and the tool call stays.
            if said.said("".join(text_of(one) for one in [*held, piece])):
                held, piece = [], _wordless(piece)
            for one in held:
                yield one
            held = []
            yield piece
            continue
        held.append(piece)
        text = "".join(text_of(one) for one in held)
        if said.said(text):
            held = []
        elif not said.may_be_said_again(text):
            for one in held:
                yield one
            held = []
    if held and not said.said("".join(text_of(one) for one in held)):
        for one in held:
            yield one
