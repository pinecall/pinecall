"""How a simulated spoken call was heard: the agent's log read against what its caller really said and when."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Literal

from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.schemas import Hearing
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.state import AgentTurn, UserTurn

# A turn's clock is the worker's and the caller's the gateway's, and a voice reaches the room a
# moment after it is handed to the line: two moments this close are the same moment.
A_MOMENT_S = 0.75
# A reply cut off counts as the room's doing only when the caller had been quiet this long.
QUIET_FOR_S = 1.0
# The share of a list a "slow" reply is slower than.
SLOW = 0.9


# What a simulation knows and no real call does: the words, and the moments they were on the line,
# by the log's own clock.
@dataclass(frozen=True, slots=True)
class Said:
    """One thing the caller said: a line of its own, or a murmur into the agent's answer."""

    kind: Literal["line", "murmur"]
    text: str
    began_at: float
    ended_at: float
    # The caller meant to talk over the agent with it.
    cut_in: bool = False


def words_of(text: str) -> list[str]:
    """The words of a sentence as two transcripts are compared: lower-case, no punctuation."""
    kept = "".join(sign.lower() if sign.isalnum() or sign.isspace() else " " for sign in text)
    return kept.split()


def distance(said: Sequence[str], heard: Sequence[str]) -> int:
    """The words to change, add or drop to turn what was heard into what was said."""
    before = list(range(len(heard) + 1))
    for row, word in enumerate(said, 1):
        now = [row]
        for column, other in enumerate(heard, 1):
            now.append(min(before[column] + 1, now[column - 1] + 1, before[column - 1] + (word != other)))
        before = now
    return before[-1]


# Over what the caller said, as a word error rate is: a room transcribed as the caller adds words
# nobody said, so the rate passes 1 on a line whose noise was heard as speech.
def error_rate(said: Sequence[str], heard: Sequence[str]) -> float | None:
    """The share of the caller's words the agent got wrong; None when the caller said nothing."""
    return None if not said else round(distance(said, heard) / len(said), 3)


def _overlaps(began: float, ended: float, said: Said) -> bool:
    return began <= said.ended_at + A_MOMENT_S and ended >= said.began_at - A_MOMENT_S


def _at(share: float, values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(share * len(ordered)) - 1))]


def measured(entries: Iterable[Entry], said: Sequence[Said]) -> Hearing:
    """The call's log against what its caller said: what the agent heard, missed, invented and talked over."""
    turns = calls.reduce(entries).turns
    replies = [turn for turn in turns if isinstance(turn, AgentTurn)]
    heard = [turn for turn in turns if isinstance(turn, UserTurn)]
    lines = [one for one in said if one.kind == "line"]

    # A reply cut off while nobody of the caller's was on the line was cut off by the room.
    cut_by_the_room = 0
    cut_by_a_murmur = 0
    for reply in replies:
        stopped = reply.metrics.stopped_speaking_at
        if not reply.interrupted or stopped is None:
            continue
        speaking = [one for one in said if _overlaps(stopped - QUIET_FOR_S, stopped, one)]
        if not speaking:
            cut_by_the_room += 1
        elif all(one.kind == "murmur" for one in speaking):
            cut_by_a_murmur += 1

    # A turn the agent heard while no line of the caller's was on the line is a turn nobody said.
    phantom = 0
    for turn in heard:
        began, ended = turn.metrics.started_speaking_at, turn.metrics.stopped_speaking_at
        if began is None or ended is None:
            continue
        if not any(_overlaps(began, ended, line) for line in lines):
            phantom += 1

    # Each line is answered by the first reply that starts after it ends and before the next line does.
    waits: list[float] = []
    unanswered = 0
    talked_over = 0
    starts = sorted(reply.metrics.started_speaking_at for reply in replies if reply.metrics.started_speaking_at)
    for at, line in enumerate(lines):
        until = lines[at + 1].began_at if at + 1 < len(lines) else float("inf")
        answer = next((start for start in starts if line.ended_at - A_MOMENT_S <= start < until), None)
        if answer is None:
            unanswered += 1
        else:
            waits.append(max(0.0, answer - line.ended_at))
        # A reply that began in the middle of a line the caller was not cutting in with spoke over it.
        if not line.cut_in and any(line.began_at + A_MOMENT_S < start < line.ended_at - A_MOMENT_S for start in starts):
            talked_over += 1

    spoken = [word for line in lines for word in words_of(line.text)]
    transcribed = [word for turn in heard for word in words_of(turn.text)]
    return Hearing(
        lines=len(lines),
        unanswered=unanswered,
        cut_by_the_room=cut_by_the_room,
        cut_by_a_murmur=cut_by_a_murmur,
        phantom_turns=phantom,
        talked_over=talked_over,
        reply_s=None if not waits else round(median(waits), 3),
        slow_reply_s=None if not waits else round(_at(SLOW, waits) or 0.0, 3),
        word_error_rate=error_rate(spoken, transcribed),
    )
