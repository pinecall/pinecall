"""The session's use cases, and its pieces a host builds a call on: opened, heard, re-staged, commanded, ended."""

from collections.abc import Mapping, Sequence

from livekit.agents.voice.run_result import RunResult

from runtime.enums import Stage
from runtime.providers.stage import Pipeline, Running
from runtime.session import commands, text, voice
from runtime.session.call import Call, CallContext, Platform, ToolUse
from runtime.session.clock import end_when_quiet, keep_time, watch_the_quiet
from runtime.session.commands import Restage
from runtime.session.history import CLOCK_TOOL, Resumption, history_of
from runtime.session.hold import HoldMusic, runtime_melody
from runtime.session.room import CallRoom
from runtime.session.session import Heard, OnEnded, Place, Session
from runtime.session.tools import END_CALL, result_text
from runtime.session.widget import HANGUP, Reading, Widget
from runtime.session.writing import WRITTEN_WITHIN_S, Writing
from runtime.wire.base import Command, Entry
from runtime.wire.events import ErrorEvent
from runtime.wire.parts import EndedBy, EndReason

# What a host builds a call on and reads of it, named once: a higher domain reaches this module and
# no other of the session's.
__all__ = [
    "CLOCK_TOOL",
    "END_CALL",
    "HANGUP",
    "WRITTEN_WITHIN_S",
    "Call",
    "CallContext",
    "CallRoom",
    "Heard",
    "HoldMusic",
    "OnEnded",
    "Place",
    "Platform",
    "Reading",
    "Restage",
    "Resumption",
    "Session",
    "ToolUse",
    "Widget",
    "Writing",
    "end",
    "end_when_quiet",
    "hear",
    "history_of",
    "keep_time",
    "open_spoken",
    "open_written",
    "result_text",
    "resume",
    "run",
    "runtime_melody",
    "take",
    "take_stages",
    "watch_the_quiet",
]


# A stage its vendor refuses raises here, before anything of the call is written: the host says it
# on the call's log and lets the call go.
def open_spoken(
    call: Call,
    stages: Pipeline,
    place: Place,
    *,
    lookup_budget_ms: int | None = None,
    tool_steps: int | None = None,
    on_ended: OnEnded | None = None,
) -> Session:
    """The session of a spoken call in its room, built and not yet started."""
    return voice.voice_session(
        call, stages, place, lookup_budget_ms=lookup_budget_ms, tool_steps=tool_steps, on_ended=on_ended
    )


def open_written(
    call: Call,
    thinking: Running,
    place: Place | None = None,
    *,
    lookup_budget_ms: int | None = None,
    tool_steps: int | None = None,
    on_ended: OnEnded | None = None,
) -> Session:
    """The session of a written call, in a room or (the gateway's own) in none, built and not yet started."""
    return text.text_session(
        call, thinking, place or Place(), lookup_budget_ms=lookup_budget_ms, tool_steps=tool_steps, on_ended=on_ended
    )


# A gateway that restarted forgot the call, not the caller: no call.started, no second greeting. The
# call itself goes on from what the log took of it (`Call(written=…)`).
async def resume(session: Session, entries: Sequence[Entry]) -> None:
    """Open the session on a call taken up again, with the history its log holds."""
    await session.resume(history_of(entries))


async def hear(session: Session, message: str) -> Heard:
    """The contact's written message into the call: the agent's reply, and why the call ended if it did."""
    return await session.hear(message)


async def run(session: Session, line: str) -> RunResult[None]:
    """A golden's line into the call as livekit's test run: every event the turn produced."""
    return await session.run(line)


async def end(session: Session, reason: EndReason, by: EndedBy) -> None:
    """End a call for this reason and close it: call.ended, then the seal."""
    await session.end(reason, by)


async def take(session: Session, command: Command, *, restage: Restage | None = None) -> ErrorEvent | None:
    """Take one command off the call's stream; the `error` entry of one it refused, for the host to write."""
    return await commands.take(session, command, restage=restage)


async def take_stages(session: Session, wanted: Mapping[Stage, Running], *, alone: bool) -> list[Stage]:
    """The live call on the model and the voice its agent's settings name now; the stages rebuilt."""
    return await session.take_stages(wanted, alone=alone)
