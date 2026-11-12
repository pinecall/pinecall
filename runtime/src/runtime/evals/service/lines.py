"""The line a simulated caller is on: written or spoken, decided once, and the same to whoever plays the call."""

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Protocol, Self

from runtime.evals.service.hearing import Said
from runtime.evals.service.turns import Landed, NextLine, speak_turns
from runtime.wire.metrics import ModelUsage


# How the caller's lines reach the agent is the one thing that varies between a written and a spoken
# test call. Until 2026-11 it was a `voice: bool` asked again at seven levels, and four functions that
# built the same call. A line is entered to open the call and left to close it, whatever happened on it.
class Line(Protocol):
    """A call as its simulated caller is on it: opened, a line said, the agent's answer waited for, hung up."""

    async def __aenter__(self) -> Self:
        """Open the call, and stand on it once the agent listens."""
        ...

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        """Leave the call, whatever happened on it."""
        ...

    async def say(self, text: str) -> ModelUsage | None:
        """Say one line to the agent; what saying it cost on this line (its voice, when spoken), or nothing."""
        ...

    async def wait_for_answer(self, lines: int, landed: Landed) -> bool:
        """Wait until the agent answered this many lines; False when the call ended or it never answered."""
        ...

    async def hang_up(self) -> None:
        """Hang up as a caller does, once the last line said was answered."""
        ...

    def list_said(self) -> Sequence[Said]:
        """What the caller really said and when, for the agent's hearing to be measured against; none when written."""
        ...


# What a line cost to say is told as it is said, so the caller's spending holds it before the next
# line is asked for: the line that crosses the ceiling is the last one said.
async def play(line: Line, turns: int, next_line: NextLine, count: Callable[[ModelUsage | None], None]) -> int:
    """Open the line, say each line as the agent answers the one before, and hang up; the lines said."""

    async def say(text: str) -> None:
        count(await line.say(text))

    async with line:
        said = await speak_turns(turns, next_line, say, line.wait_for_answer)
        await line.hang_up()
    return said
