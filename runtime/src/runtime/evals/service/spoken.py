"""The spoken line: the agent offered a room, the caller's leg put in it, its lines said out loud, the hang-up."""

import asyncio
import logging
from collections.abc import Sequence
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Never, Self

from livekit import rtc
from livekit.agents import tts

from runtime.enums import Env
from runtime.evals.parts import Harness
from runtime.evals.service import ambience, turns
from runtime.evals.service.hearing import Said
from runtime.evals.service.leg import CallerLeg, Spoken, synthesize
from runtime.evals.service.slots import wait_for_fleet_slot
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.kit.retry import until
from runtime.kit.time import epoch
from runtime.live import service as live
from runtime.livekit import close_room
from runtime.providers import service as providers
from runtime.providers.stage import Running
from runtime.session import service as session
from runtime.wire.dispatch import Dispatch
from runtime.wire.metrics import ModelUsage, TTSModelUsage
from runtime.wire.room import A_SIMULATED_CALLER

logger = logging.getLogger(__name__)

NO_LINE = "the simulated call could not be held: {broke}"
# Longer than any run, so the caller's token never ends a call first.
A_CALL_MAY_LAST_S = 15 * 60.0
# The caller leaving ends the call as a hang-up, which the worker writes; the room is deleted after,
# whatever happened, so a worker that never noticed still ends its job and seals the log.
HANGS_UP_WITHIN_S = 10.0
# A cold worker has been measured at 15 s before it publishes its audio. Past the fleet's last offer and
# the overflow's joining: a caller that gave up before them heard nobody.
THE_AGENT_MAY_TAKE_S = fleet.AN_AGENT_JOINS_WITHIN_S
NOBODY_ANSWERED = "no agent joined room {call} in {seconds:.0f}s: is the env's fleet up?"
# The background voice a noisy line carries.
A_TELEVISION = (
    "A continuación, el resumen deportivo de la jornada. El equipo local venció por dos goles a "
    "uno en un partido disputado hasta el último minuto, y el entrenador destacó el esfuerzo de "
    "sus jugadores en la rueda de prensa posterior al encuentro."
)


# The agent is dispatched into a room whoever holds it (a process deployed or a developer's) and the
# caller speaks there in a voice of its own; the room going ends the job, which seals the call. The
# call lasts minutes and holds no connection. Everything opened on the way in is on one stack, closed
# in the reverse order whatever happens: until 2026-11 the voice was opened two transactions before
# the `try` that closed it, and a database error between them left its client open.
class SpokenLine:
    """A spoken call as its simulated caller is on it: a seat in the agent's room, a voice, the line's noise."""

    def __init__(
        self, parts: Harness, dispatch: Dispatch, voice: Running, spoken: Spoken, *, waits_for_slot: bool
    ) -> None:
        self._parts = parts
        self._dispatch = dispatch
        self._voice = voice
        self._spoken = spoken
        self._waits_for_slot = waits_for_slot
        self._stack = AsyncExitStack()
        self._room = rtc.Room()
        self._leg: CallerLeg | None = None
        self._lines = 0

    async def __aenter__(self) -> Self:
        """Offer the agent the room, join it as the caller, and stand on the line once the agent listens."""
        try:
            await self._open()
        except BaseException as broke:
            await self._stack.__aexit__(type(broke), broke, broke.__traceback__)
            _refuse_a_line_that_broke(broke)
            raise
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        """Leave the room, wait a moment for the worker to write the end, and delete the room."""
        await self._stack.__aexit__(kind, error, trace)
        if error is not None:
            _refuse_a_line_that_broke(error)

    async def say(self, text: str) -> ModelUsage | None:
        """Speak one line into the room; its voice's characters, as the box prices them."""
        await self._on_the_line().say(text)
        self._lines += 1
        return TTSModelUsage(provider=self._voice.vendor, model=self._voice.model or "", characters_count=len(text))

    async def wait_for_answer(self, lines: int, landed: turns.Landed) -> bool:
        """Wait until the agent answered this many lines, the caller murmuring or cutting in as it acts."""
        return await self._on_the_line().wait_for_answer(lines, landed)

    # Waited again, whole: hanging up at once would cut the agent's last answer. Said before leaving, as
    # a widget's hang-up is: the call ends caller_hung_up now, not drained once the room is deleted,
    # with the silence between the two billed.
    async def hang_up(self) -> None:
        """Hear the last answer out, then say the hang-up in the room."""
        parts, leg = self._parts, self._on_the_line()
        await turns.wait_for_answer(parts.logs, parts.store, self._spoken.call, self._lines, since=leg.said_at)
        await self._room.local_participant.publish_data(b"{}", reliable=True, topic=session.HANGUP)

    def list_said(self) -> Sequence[Said]:
        """What the caller said and when, by the log's clock."""
        return () if self._leg is None else tuple(self._leg.spoke)

    async def _open(self) -> None:
        parts, call = self._parts, self._spoken.call
        env = self._dispatch.env or Env.sandbox
        async with parts.sessions.begin() as session_:
            the_fleet = await fleet.fleet_of_env(session_, env)
        if self._waits_for_slot:
            await wait_for_fleet_slot(
                parts.sessions, parts.offering, parts.roster, parts.logs, env, self._dispatch.agent or "", the_fleet
            )
        speech = await self._stack.enter_async_context(providers.voice_outside_a_call(self._voice))
        interferer = await self._make_room_sound(speech)
        visitor = live.Visitor(expires_at=epoch() + A_CALL_MAY_LAST_S, identity=A_SIMULATED_CALLER)
        token = live.sign_room_token(parts.signer, call, "talk", visitor)
        self._stack.push_async_callback(close_room, parts.servers[env], call)
        self._stack.push_async_exit(self._wait_for_the_end)
        await parts.offering.offer(call, the_fleet, self._dispatch)
        await self._room.connect(parts.settings.livekit_url_of(env), token)
        self._stack.push_async_callback(self._room.disconnect)
        leg = self._leg = CallerLeg(self._spoken, speech, parts.logs, parts.store, interferer)
        # Published before the agent arrives: audio pushed before a subscription is lost.
        await self._room.local_participant.publish_track(
            leg.track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        # The room behind the caller is heard from here: the agent greets a line that already has it.
        leg.open()
        self._stack.push_async_callback(leg.close)
        await self._wait_for_the_agent()

    # Made in a thread: a café is eight voices resampled, and an office's hum is walked sample by sample.
    async def _make_room_sound(self, speech: tts.TTS[Never]) -> bytes:
        acts = self._spoken.acts
        if acts.interferer_db is None:
            return b""
        chatter = await synthesize(speech, A_TELEVISION) if acts.ambience in ambience.VOICED else b""
        return await asyncio.to_thread(ambience.sound_of, acts.ambience, chatter)

    # The agent joins before its session is built; its published audio means it listens.
    async def _wait_for_the_agent(self) -> None:
        async def probe() -> bool | None:
            listens = any(
                publication.kind == rtc.TrackKind.KIND_AUDIO
                for participant in self._room.remote_participants.values()
                for publication in participant.track_publications.values()
            )
            return True if listens else None

        if await until(probe, every_s=turns.A_BEAT_S, within_s=THE_AGENT_MAY_TAKE_S) is None:
            raise TimeoutError(NOBODY_ANSWERED.format(call=self._spoken.call, seconds=THE_AGENT_MAY_TAKE_S))

    # Only a call that was hung up waits for its end: one that broke has its room deleted at once.
    async def _wait_for_the_end(
        self, _kind: type[BaseException] | None, error: BaseException | None, _trace: TracebackType | None
    ) -> None:
        if error is not None:
            return
        call = self._spoken.call
        log = self._parts.logs.reading(call)
        subscription = await log.follow()
        try:
            async with asyncio.timeout(HANGS_UP_WITHIN_S):
                while (await log.snapshot()).status != "ended":
                    await turns.wait_for_entry_or_beat(subscription)
        except TimeoutError:
            logger.info("%s: the worker wrote no call.ended within %.0f s; its room is closed", call, HANGS_UP_WITHIN_S)
        finally:
            subscription.close()

    def _on_the_line(self) -> CallerLeg:
        if self._leg is None:
            raise ServiceUnavailable(NO_LINE.format(broke="the caller's leg was never opened"))
        return self._leg


def _refuse_a_line_that_broke(broke: BaseException) -> None:
    if isinstance(broke, TimeoutError | rtc.ConnectError):
        raise ServiceUnavailable(NO_LINE.format(broke=broke)) from broke
