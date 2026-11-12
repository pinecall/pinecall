"""Who has a call's line: the agent, nobody while it is held, a person awaited, a supervisor, a person dialled in."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

from livekit.agents.utils import aio
from livekit.agents.voice import AgentSession

from runtime.exceptions import Conflict, ValidationError
from runtime.session.call import Call
from runtime.session.hold import HoldMusic
from runtime.wire import events as wire
from runtime.wire.commands import CallAttention
from runtime.wire.parts import Supervisor

# Why the agent is not the one speaking. With any of them it neither hears nor speaks; each
# transition adds or takes away its own and no other, so one never undoes what another holds: until
# 2026-11 these were five fields of three objects, and the app's `call.unhold` gave the agent its
# voice back under a supervisor who still had the line.
type Reason = Literal["hold", "attention", "supervisor", "bridge"]
# The reasons that are a person talking with the caller: no melody plays over them.
A_PERSON: frozenset[Reason] = frozenset({"supervisor", "bridge"})
WHY: dict[Reason, str] = {
    "hold": "the caller is on hold",
    "attention": "the caller waits for a person",
    "supervisor": "a supervisor has it",
    "bridge": "the person the caller was transferred to has it",
}
# The app's tool timeout must outlast the wait it asks for; the runtime does not extend it.
NOBODY_TOOK_IT = "nobody took the line within {wait_s:g}s"


class Line:
    """One call's line: who has it, the agent's ears and voice with it, the melody, and what the log says of it."""

    # The melody is the only thing here a call may lack: a written call, or an agent that plays none.
    def __init__(self, call: Call, live: AgentSession[Call], melody: HoldMusic | None = None) -> None:
        """A line the agent has."""
        self.call = call
        self.live = live
        self.melody = melody
        self.reasons: frozenset[Reason] = frozenset()
        self.taken_by: Supervisor | None = None
        self.awaiting: asyncio.Task[None] | None = None

    @property
    def agent_may_speak(self) -> bool:
        """Whether the line is the agent's: nobody holds it, awaits it or has taken it."""
        return not self.reasons

    def refuse_unless_the_agents(self, what: str) -> None:
        """Refuse words the app would have the agent say while the line is not its own."""
        if self.reasons:
            why = ", ".join(WHY[reason] for reason in sorted(self.reasons))
            raise Conflict(f"{what}: the agent does not have the line ({why}), so nothing it said would be heard")

    # ── its life ──

    async def open(self) -> None:
        """Publish the melody's track in the call's room."""
        if self.melody is not None:
            await self.melody.start()

    async def close(self) -> None:
        """Stop waiting for anybody, and stop the melody."""
        awaiting, self.awaiting = self.awaiting, None
        if awaiting is not None:
            await aio.cancel_and_wait(awaiting)
        if self.melody is not None:
            await self.melody.aclose()

    def floor(self, *, speaking: bool) -> None:
        """Whether the agent is speaking, as the session says: the melody waits for its quiet."""
        if self.melody is not None:
            self.melody.floor(speaking=speaking)

    def read_melody(self) -> tuple[Path | None, list[tuple[float, float]]]:
        """The melody's clip and when it sounded, by the clock, for the recording; nothing on a call with none."""
        return (None, []) if self.melody is None else (self.melody.clip, self.melody.sounded)

    # The wait for a tool or for the model's first word: the melody by its own count of reasons to
    # play, and no change of who has the line.
    @contextlib.asynccontextmanager
    async def waiting(self) -> AsyncGenerator[None]:
        """The melody, after its grace, for as long as the block waits."""
        if self.melody is not None:
            self.melody.begin()
        try:
            yield
        finally:
            if self.melody is not None:
                self.melody.end()

    # ── who has it ──

    async def hold(self) -> None:
        """The agent neither speaks nor hears, the melody plays, and the log says so."""
        await self._set(self._with("hold"))

    async def unhold(self) -> None:
        """The app's hold ends: the agent hears and speaks again, unless somebody else has the line."""
        await self._set(self._without("hold"))

    async def await_a_person(self, wanted: CallAttention) -> None:
        """Hold the caller for a supervisor, for as long as the app asked, once at a time."""
        if "attention" in self.reasons:
            raise ValidationError("the caller is already waiting for a person")
        requested = wire.AttentionRequested(reason=wanted.reason, wait_s=wanted.wait_s)
        asked = self.call.writing.write("attention.requested", requested)
        await self._set(self._with("attention"))
        self.awaiting = asyncio.create_task(self._nobody_came(wanted.wait_s))
        await asked

    # The person awaited came: the wait is answered, the melody stops, and the line is theirs.
    async def take(self, by: Supervisor) -> None:
        """A supervisor takes the line: the agent goes quiet until they release it."""
        if self.taken_by is not None:
            raise ValidationError(f"{self.taken_by.id} already holds the line; they release it, or nobody does")
        took = self.call.writing.write("supervisor.took_over", wire.SupervisorTookOver(by=by))
        if "attention" in self.reasons:
            self._stop_awaiting()
            self.call.writing.write("attention.answered", wire.AttentionAnswered(ok=True, by=by))
        self.taken_by = by
        await self._set(self._without("attention") | frozenset[Reason]({"supervisor"}))
        await took

    async def release(self, by: Supervisor) -> None:
        """The supervisor gives the line back; the agent has it again unless another reason holds it."""
        if self.taken_by is None:
            raise ValidationError("nobody holds the line, so there is nothing to give back")
        released = self.call.writing.write("supervisor.released", wire.SupervisorReleased(by=by))
        self.taken_by = None
        await self._set(self._without("supervisor"))
        await released

    # The person is in the room and the caller talks with them: the call ends when they leave.
    async def bridge(self) -> None:
        """The caller was transferred warm: the agent is quiet for the rest of the call."""
        await self._set(self._with("bridge"))

    # ── private ──

    async def _nobody_came(self, wait_s: float) -> None:
        await asyncio.sleep(wait_s)
        self.awaiting = None
        failed = NOBODY_TOOK_IT.format(wait_s=wait_s)
        answered = self.call.writing.write(
            "attention.answered", wire.AttentionAnswered(ok=False, by=None, error=failed)
        )
        await self._set(self._without("attention"))
        await answered

    def _with(self, reason: Reason) -> frozenset[Reason]:
        return self.reasons | frozenset[Reason]({reason})

    def _without(self, reason: Reason) -> frozenset[Reason]:
        return frozenset(each for each in self.reasons if each != reason)

    def _stop_awaiting(self) -> None:
        awaiting, self.awaiting = self.awaiting, None
        if awaiting is not None:
            awaiting.cancel()

    # The one place that touches the agent's audio, the melody and `call.line`, and only when the
    # answer changes: the line is held when there is a reason and none of them is a person.
    async def _set(self, reasons: frozenset[Reason]) -> None:
        before, self.reasons = self.reasons, reasons
        if reasons and not before:
            self._silence()
        if before and not reasons:
            self._hear_again()
        held, was = _is_held(reasons), _is_held(before)
        if held == was:
            return
        if self.melody is not None:
            if held:
                self.melody.begin()
            else:
                self.melody.end()
        await self.call.writing.write("call.line", wire.CallLine(held=held, muted=False))

    # interrupt() raises when nothing is playing or the session has stopped. Its future waits for the
    # speech to end: a hold asked from a tool of that speech would wait out livekit's five seconds
    # before the line was marked held (measured 2026-10-24), while the speech itself is cut as the
    # call returns. The audio goes off here, now.
    def _silence(self) -> None:
        with contextlib.suppress(RuntimeError):
            self.live.interrupt(force=True)
        self.live.output.set_audio_enabled(False)
        self.live.input.set_audio_enabled(False)

    # The ears first, then the voice, so the agent never speaks before it can hear.
    def _hear_again(self) -> None:
        self.live.input.set_audio_enabled(True)
        self.live.output.set_audio_enabled(True)


def _is_held(reasons: frozenset[Reason]) -> bool:
    return bool(reasons) and not reasons & A_PERSON
