"""The spoken line: the agent offered a room, the caller's leg put in it, its lines said out loud, the hang-up."""

import asyncio
import logging
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from types import TracebackType
from typing import Never, Self

from livekit import rtc
from livekit.agents import tts

from runtime.enums import Env
from runtime.evals.parts import Harness
from runtime.evals.service import ambience, turns
from runtime.evals.service.hearing import Said
from runtime.evals.service.leg import CallerLeg, Spoken, synthesize
from runtime.evals.service.slots import take_fleet_seat
from runtime.exceptions import ServiceUnavailable
from runtime.fleet import service as fleet
from runtime.kit.retry import until
from runtime.kit.time import epoch
from runtime.kit.turn import Relay
from runtime.live import service as live
from runtime.livekit import close_room
from runtime.providers import service as providers
from runtime.providers.stage import Running
from runtime.session import service as session
from runtime.wire.dispatch import Dispatch
from runtime.wire.metrics import ModelUsage, TTSModelUsage
from runtime.wire.room import A_SIMULATED_CALLER

logger = logging.getLogger(__name__)

# Longer than any run, so the caller's token never ends a call first.
A_CALL_MAY_LAST_S = 15 * 60.0
# The caller leaving ends the call as a hang-up, which the worker writes; the room is deleted after,
# whatever happened, so a worker that never noticed still ends its job and seals the log.
HANGS_UP_WITHIN_S = 10.0
# A cold worker has been measured at 15 s before it publishes its audio. Past the fleet's last offer and
# the overflow's joining: a caller that gave up before them heard nobody.
THE_AGENT_MAY_TAKE_S = fleet.AN_AGENT_JOINS_WITHIN_S
# A caller that took a seat waits for its agent as long as the fleet keeps its room: a job LiveKit gave
# to nobody is rung again by the sweep, to the same worker when it is the only one, and the callers
# still waiting let that room go first. Only the sweep rings a room again: on 2026-11-24 a caller that
# took a second seat itself rang a room whose call a worker had already opened, and the second job
# ended the first one's call in the middle.
THE_SEATED_MAY_WAIT_S = fleet.A_ROOM_IS_KEPT_S - 10.0
# What a café's tables say, read once in the caller's own voice and then eight of it at once: a murmur
# nobody follows. A television is a broadcast of its own (ambience.py).
A_TABLES_TALK = (
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
        # On a line with a network the hang-up is a packet like the rest, held or lost and sent again: the
        # caller stays on until the agent heard it. Leaving at once, as on a clean line, took the packet
        # with it, and the call ended ten seconds later by its room closing (2026-11-17).
        if not self._spoken.network.is_clean:
            await self._hear_the_end()

    def list_said(self) -> Sequence[Said]:
        """What the caller said and when, by the log's clock."""
        return () if self._leg is None else tuple(self._leg.spoke)

    @property
    def env(self) -> Env:
        """The env the call is placed in."""
        return self._dispatch.env or Env.sandbox

    async def _open(self) -> None:
        parts, call = self._parts, self._spoken.call
        seat = await self._take_a_seat()
        speech = await self._stack.enter_async_context(self._open_voice())
        interferer = await self._make_room_sound(speech)
        self._stack.push_async_callback(close_room, parts.servers[self.env], call)
        self._stack.push_async_exit(self._wait_for_the_end)
        await self._ring(seat)
        await self._join(call, self.env, speech, interferer)
        await self._wait_for_the_agent(THE_SEATED_MAY_WAIT_S if seat is not None else THE_AGENT_MAY_TAKE_S)

    def _open_voice(self) -> AbstractAsyncContextManager[tts.TTS[Never]]:
        return providers.voice_outside_a_call(self._voice)

    # A simulation waits for a seat and takes it before it opens anything: its voice, its room's sound
    # and its place in the room are held only once a worker is to answer, so a queue of callers holds
    # nothing open. A golden said out loud takes none: its room is offered as a caller's is, and a full
    # fleet answers it with the overflow's sentence. The seat is given back if the line breaks before
    # its room is rung, or the sweep would ring a room nobody is in.
    async def _take_a_seat(self) -> fleet.Seat | None:
        if not self._waits_for_slot:
            return None
        parts, call = self._parts, self._spoken.call
        async with parts.sessions.begin() as session_:
            the_fleet = await fleet.fleet_of_env(session_, self.env)
        seat = await take_fleet_seat(
            parts.sessions, parts.offering, parts.roster, parts.logs, self.env, the_fleet, call, self._dispatch
        )
        self._stack.push_async_callback(parts.offering.forget, call)
        return seat

    async def _ring(self, seat: fleet.Seat | None) -> None:
        parts, call = self._parts, self._spoken.call
        if seat is not None:
            await parts.offering.ring(seat, self._dispatch)
            return
        async with parts.sessions.begin() as session_:
            the_fleet = await fleet.fleet_of_env(session_, self.env)
        await parts.offering.offer(call, the_fleet, self._dispatch)

    # The caller's seat in a room of an env's LiveKit: its leg published and carrying from here on.
    async def _join(self, room: str, env: Env, speech: tts.TTS[Never], interferer: bytes) -> None:
        parts = self._parts
        visitor = live.Visitor(expires_at=epoch() + A_CALL_MAY_LAST_S, identity=A_SIMULATED_CALLER)
        token = live.sign_room_token(parts.signer, room, "talk", visitor)
        await self._room.connect(parts.settings.livekit_url_of(env), token, await self._cross_the_network())
        self._stack.push_async_callback(self._room.disconnect)
        leg = self._leg = CallerLeg(self._spoken, speech, parts.logs, parts.store, interferer)
        # Published before the agent arrives: audio pushed before a subscription is lost.
        await self._room.local_participant.publish_track(
            leg.track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        # The room behind the caller is heard from here: the agent greets a line that already has it.
        leg.open()
        self._stack.push_async_callback(leg.close)

    # A line with a network of its own sends every packet through a relay in this process, the one
    # ICE server the caller is given, and is told to use relays alone: what the line loses, how long
    # it holds a packet and how much it carries are then done to the call's real packets, each way,
    # before the SFU sees them. A clean line joins as it always did, with no relay to fail.
    async def _cross_the_network(self) -> rtc.RoomOptions:
        shape = self._spoken.network
        if shape.is_clean:
            return rtc.RoomOptions()
        relay = Relay(shape)
        await relay.open()
        self._stack.push_async_callback(self._close_relay, relay)
        server = rtc.IceServer(urls=[relay.url], username=relay.username, password=relay.password)
        only_relays = rtc.RtcConfiguration(
            ice_transport_type=rtc.IceTransportType.TRANSPORT_RELAY, ice_servers=[server]
        )
        return rtc.RoomOptions(rtc_config=only_relays)

    async def _close_relay(self, relay: Relay) -> None:
        await relay.close()
        up, down = relay.uplink.counts, relay.downlink.counts
        logger.info(
            "%s: the caller's network carried %d packets up and lost %d (%d to its queue), %d down and lost %d",
            self._spoken.call,
            up.carried,
            up.lost + up.dropped,
            up.dropped,
            down.carried,
            down.lost + down.dropped,
        )

    # Made in a thread: a café is eight voices resampled, and an office's hum is walked sample by sample.
    async def _make_room_sound(self, speech: tts.TTS[Never]) -> bytes:
        acts = self._spoken.acts
        if acts.interferer_db is None:
            return b""
        chatter = await synthesize(speech, A_TABLES_TALK) if acts.ambience in ambience.VOICED else b""
        return await asyncio.to_thread(ambience.sound_of, acts.ambience, chatter)

    # The agent joins before its session is built; its published audio means it listens.
    async def _wait_for_the_agent(self, within_s: float = THE_AGENT_MAY_TAKE_S) -> None:
        async def probe() -> bool | None:
            listens = any(
                publication.kind == rtc.TrackKind.KIND_AUDIO
                for participant in self._room.remote_participants.values()
                for publication in participant.track_publications.values()
            )
            return True if listens else None

        if await until(probe, every_s=turns.A_BEAT_S, within_s=within_s) is None:
            raise TimeoutError(f"no agent joined room {self._spoken.call} in {within_s:.0f}s: is the env's fleet up?")

    # Only a call that was hung up waits for its end: one that broke has its room deleted at once.
    async def _wait_for_the_end(
        self, _kind: type[BaseException] | None, error: BaseException | None, _trace: TracebackType | None
    ) -> None:
        if error is None:
            await self._hear_the_end()

    async def _hear_the_end(self) -> None:
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
            raise ServiceUnavailable("the simulated call could not be held: the caller's leg was never opened")
        return self._leg


def _refuse_a_line_that_broke(broke: BaseException) -> None:
    if isinstance(broke, TimeoutError | rtc.ConnectError):
        raise ServiceUnavailable(f"the simulated call could not be held: {broke}") from broke
