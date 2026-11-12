"""The agent's words as they play: the entry each piece is written as, and the lexicon's spoken forms read back."""

from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence

from livekit.agents import utils
from livekit.agents.types import NOT_GIVEN, TimedString
from livekit.agents.voice import AgentSession

from runtime.kit.words import Unsaying
from runtime.session.call import Call
from runtime.wire import events as wire


def transcript_of(live: AgentSession[Call], delta: str | TimedString) -> wire.AgentTranscript:
    """What the agent said, as the wire's transcript entry, with the word timings livekit gave."""
    speech = live.current_speech.id if live.current_speech else ""
    timed: dict[str, float] = {}
    if isinstance(delta, TimedString):
        if utils.is_given(delta.start_time):
            timed["start"] = delta.start_time
        if utils.is_given(delta.end_time):
            timed["end"] = delta.end_time
    return wire.AgentTranscript(speech_id=speech, text=str(delta), final=False, **timed)


# Pieces are held while they could still be the start of a spoken form, so a form split across
# two pieces is read back whole; a timed piece keeps the times of the first and the last.
async def unsay(pieces: AsyncIterable[str | TimedString], says: Mapping[str, str]) -> AsyncIterator[str | TimedString]:
    """The transcript pieces with the lexicon's spoken forms read back as the words written."""
    if not says:
        async for piece in pieces:
            yield piece
        return
    unsaying = Unsaying(says)
    pending: list[str | TimedString] = []
    async for piece in pieces:
        pending.append(piece)
        text = "".join(pending)
        if unsaying.found(text) and not unsaying.may_go_on(text):
            yield _join(pending, unsaying.back(text))
            pending = []
        elif not unsaying.may_go_on(text):
            for held in pending:
                yield held
            pending = []
    if pending:
        text = "".join(pending)
        yield _join(pending, unsaying.back(text) if unsaying.found(text) else text)


def _join(pending: Sequence[str | TimedString], text: str) -> str | TimedString:
    first, last = pending[0], pending[-1]
    if not isinstance(first, TimedString) or not isinstance(last, TimedString):
        return text
    end = last.end_time if last.end_time is not NOT_GIVEN else first.end_time
    return TimedString(text, start_time=first.start_time, end_time=end)
