"""A persona on a real line: the caller's leg in the room, its lines spoken, the noise on it."""

import asyncio
import math
import random as randomness
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Never

import numpy as np
from livekit import rtc
from livekit.agents import tts
from livekit.agents.utils import http_context

from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.service import ambience as ambiences
from pinecall_runtime.evals.service.hearing import Said
from pinecall_runtime.evals.service.tempo import Stretcher
from pinecall_runtime.evals.service.turns import A_BEAT_S, Landed, NextLine, answered, speak_turns, speaking
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.judging import service as judging
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session import service as session

# 10 ms of 16-bit mono per frame, the cadence livekit's examples publish at.
FRAME_MS = 10
# A sum past 16 bits is clipped, never wrapped: a wrap is a click the ears would hear.
LOUDEST = 32767
QUIETEST = -32768
# A lost packet is the silence a jitter buffer plays in its place.
LOST = b"\x00\x00"
# Every line is resampled to this rate, so the caller's track opens before any audio exists.
SAMPLE_RATE = 48_000
CHANNELS = 1
# What the caller's track carries while the caller says nothing.
SILENCE = LOST * (SAMPLE_RATE * FRAME_MS // 1000)
# How much of the line the room is given ahead of time: measured, a source paces what it is handed
# at the clock's rate once it holds this much, so the caller's word waits this long at most behind
# the room's noise. A second of it, the source's default, was a second of delay on every line.
AHEAD_MS = 100
# Where a vendor's voice sits, -20 dBFS: how loud a caller is taken to speak before its first word.
A_VOICE_RMS = 3277.0
# That guess weighs as half a second of speech, so a first syllable does not move the room's noise.
A_GUESS_WEIGHS_FRAMES = 50
# A frame under this is the gap between two words: it says nothing of how loud the caller speaks.
A_GAP_RMS = 100.0
# How far into the agent's answer a caller that interrupts starts talking, in seconds.
CUT_IN_AFTER_S = (0.8, 2.5)
# How far into the agent's answer a caller murmurs its "mm-hmm", in seconds: after a clause.
MURMUR_AFTER_S = (1.5, 3.5)
# A voice at this tempo is the vendor's own: nothing is stretched.
AS_READ = 1.0
# What a listener murmurs while the other speaks, without taking the turn, by language.
MURMURS: Mapping[str, tuple[str, ...]] = {
    "es": ("ajá", "mm", "sí, sí"),
    "en": ("mm-hmm", "uh-huh", "right"),
    "pt": ("uhum", "sim, sim"),
    "fr": ("hm hm", "oui"),
    "de": ("mhm", "ja"),
    "it": ("mh mh", "sì"),
}
# A cold worker has been measured at 15 s before it publishes its audio.
# Past the fleet's last offer and the overflow's joining: a caller that gave up before them heard nobody.
THE_AGENT_MAY_TAKE_S = fleet.AN_AGENT_JOINS_WITHIN_S
NOBODY_ANSWERED = "no agent joined room {call} in {seconds:.0f}s: is the env's fleet up?"
# The background voice a noisy line carries.
A_TELEVISION = (
    "A continuación, el resumen deportivo de la jornada. El equipo local venció por dos goles a "
    "uno en un partido disputado hasta el último minuto, y el entrenador destacó el esfuerzo de "
    "sus jugadores en la rueda de prensa posterior al encuentro."
)


@dataclass(frozen=True)
class Line:
    """What the line does to the caller's voice, and what the caller does on it."""

    # None: nothing is mixed in.
    interferer_db: float | None = None
    packet_loss: float = 0.0
    # The share of the agent's answers the caller talks over, and its silence before each line.
    interrupts: float = 0.0
    pause_s: float = 0.0
    # The share of the answers it murmurs into, how fast it speaks, and what plays behind it.
    backchannels: float = 0.0
    speed: float = AS_READ
    ambience: str = "television"
    # The caller's language, for the words it murmurs; None murmurs in English.
    language: str | None = None
    dice: randomness.Random = field(default_factory=randomness.Random, compare=False)


@dataclass(frozen=True, slots=True)
class SpokenLine:
    """A spoken call as the caller joins it: the room's address, its token, the call, its turns, its notice."""

    url: str
    token: str
    call: str
    turns: int
    line: Line
    # Whether the agent says the org's recording notice before its greeting.
    notice: bool = False


# The room behind a caller does not stop when the caller does: the track carries it from the moment
# the caller joins until it hangs up, under the agent's answers and through every silence, which is
# where a noisy line breaks an agent (a television taken for a caller cutting in, a turn that never
# ends). Until 2026-11-09 the noise was mixed into each spoken line alone, at a level that followed
# each piece of the voice, and between two lines the track was digital silence.
class CallerLeg:
    """The caller's leg of a spoken call: its track in the room, its voice, the line's noise."""

    def __init__(self, spoken: SpokenLine, voice: tts.TTS[Never], logs: calls.Logs, interferer: bytes) -> None:
        """A leg with its track made and nothing said yet."""
        self.spoken = spoken
        self.voice = voice
        self.logs = logs
        self.interferer = interferer
        # The interferer's own level, taken once: it is seconds long and asked for a hundred times a second.
        self.loudness = rms_of(interferer)
        self.level = SpokenLevel()
        self.source = rtc.AudioSource(SAMPLE_RATE, CHANNELS, queue_size_ms=AHEAD_MS)
        self.track = rtc.LocalAudioTrack.create_audio_track(judging.A_SIMULATED_CALLER, self.source)
        # The frames of the caller's voice not yet on the line, and whether there are none.
        self.waiting: deque[bytes] = deque()
        self.silent = asyncio.Event()
        # The samples the line has carried: where the interferer goes on from.
        self.carried = 0
        self.carrying: asyncio.Future[None] | None = None
        # What the caller said and when, by the log's clock: what the agent's hearing is measured against.
        self.spoke: list[Said] = []
        # When the caller began its last line, by the log's clock: its answer comes after it.
        self.said_at = logs.store.clock()
        # Set once the caller decided to talk over the answer: its next line is said with no pause.
        self.cutting_in = False

    # The line is spoken as the vendor sends it, never held until it is whole: a caller that
    # waited for its last word before its first was seconds late on every turn.
    async def say(self, line: str) -> None:
        """Speak one line into the room, after the caller's pause (none when cutting in), through the line's noise."""
        cut_in = self.cutting_in
        if not cut_in:
            await asyncio.sleep(self.spoken.line.pause_s)
        self.cutting_in = False
        self.said_at = self.logs.store.clock()
        await self._speak(line)
        self.spoke.append(Said("line", line, self.said_at, self.logs.store.clock(), cut_in=cut_in))

    # A murmur rides the agent's answer: it moves no clock, so the answer is still waited for whole.
    async def murmur(self, word: str) -> None:
        """Say one listener's word into the room while the agent speaks, keeping the turn."""
        began = self.logs.store.clock()
        await self._speak(word)
        self.spoke.append(Said("murmur", word, began, self.logs.store.clock()))

    def open(self) -> None:
        """Start carrying the line: from here the track is never without a frame."""
        self.carrying = asyncio.ensure_future(self._carry())
        # A line that broke leaves nobody waiting on it: the one speaking is woken and told.
        self.carrying.add_done_callback(lambda _: self.silent.set())

    async def close(self) -> None:
        """Stop carrying the line."""
        if self.carrying is not None:
            self.carrying.cancel()
            await asyncio.gather(self.carrying, return_exceptions=True)

    # The source paces the frames it is handed: this loop runs at the clock's rate, AHEAD_MS ahead.
    async def _carry(self) -> None:
        while True:
            frame = self.next_frame()
            await self.source.capture_frame(rtc.AudioFrame(frame, SAMPLE_RATE, CHANNELS, len(frame) // 2))

    # The interferer sits under how loud the caller speaks over the call, never under each piece of
    # its voice: a room does not get louder with the person in it.
    def next_frame(self) -> bytes:
        """The next 10 ms of the line: the caller's voice or its silence, the room behind it, or a lost packet."""
        line = self.spoken.line
        frame = SILENCE
        if self.waiting:
            frame = self.waiting.popleft()
            self.level.hear(frame)
        else:
            self.silent.set()
        if line.interferer_db is not None and self.loudness > 0:
            gain = self.level.rms / self.loudness * 10 ** (-line.interferer_db / 20)
            frame = behind(frame, self.interferer, self.carried, gain)
        self.carried += len(frame) // 2
        if line.packet_loss > 0 and line.dice.random() < line.packet_loss:
            return LOST * (len(frame) // 2)
        return frame

    # The voice is handed to the line as it arrives and the line says it at the clock's rate: a line
    # is said once the last of its frames has left.
    async def _speak(self, text: str) -> None:
        async with self.voice.synthesize(text) as stream:
            pieces = at_tempo(resampled(piece.frame async for piece in stream), self.spoken.line)
            async for frame in in_frames(pieces):
                self.silent.clear()
                self.waiting.append(frame)
        # A line that broke before the last frame was handed to it will never say it.
        self._still_carried()
        await self.silent.wait()
        self._still_carried()

    def _still_carried(self) -> None:
        if self.carrying is not None and self.carrying.done():
            self.carrying.result()

    # Cut in some way into the answer, as a person does: never at its first word. A caller that cuts in
    # asks for its line the moment the agent begins — what it talks over, it has not heard — and says
    # it with no pause, or the answer is over before it opens its mouth. A caller that murmurs waits for
    # the answer like any other, its "mm-hmm" said along the way.
    async def line_answered(self, lines: int, landed: Landed) -> bool:
        """Wait until the agent answered this many lines, or cut in once it started answering: True to speak."""
        line = self.spoken.line
        if lines and line.dice.random() < line.interrupts:
            await speaking(self.logs, self.spoken.call, since=self.said_at)
            landed()
            await asyncio.sleep(line.dice.uniform(*CUT_IN_AFTER_S))
            self.cutting_in = True
            return True
        if lines and line.dice.random() < line.backchannels:
            await speaking(self.logs, self.spoken.call, since=self.said_at)
            await asyncio.sleep(line.dice.uniform(*MURMUR_AFTER_S))
            await self.murmur(murmur_of(line))
        return await answered(
            self.logs, self.spoken.call, lines, since=self.said_at, landed=landed, notice=self.spoken.notice
        )


def murmur_of(line: Line) -> str:
    """One of the words a listener murmurs in the caller's language, by the line's dice."""
    words = MURMURS.get(providers.primary_language(line.language) or "en", MURMURS["en"])
    return line.dice.choice(words)


def line_of(
    behavior: judging.CallerBehavior,
    interferer_db: float | None,
    packet_loss: float,
    ambience: str | None = None,
    *,
    pause_s: float | None = None,
) -> Line:
    """The line a caller acting so is on: the noise and the pause the request names, else the persona's own."""
    return Line(
        interferer_db=behavior.interferer_db if interferer_db is None else interferer_db,
        packet_loss=packet_loss or behavior.packet_loss,
        interrupts=behavior.interrupts,
        pause_s=behavior.pause_s if pause_s is None else pause_s,
        backchannels=behavior.backchannels,
        speed=behavior.speed,
        ambience=behavior.ambience if ambience is None else ambience,
    )


def described(line: Line) -> str:
    """The line in the words a report prints."""
    if line.interferer_db is None and line.packet_loss <= 0:
        return "a clean line"
    noise = f"{line.ambience} {line.interferer_db or 0.0:.0f} dB under the caller"
    return noise if line.packet_loss <= 0 else f"{noise}, {line.packet_loss * 100:.0f}% packet loss"


# The vendor's audio is stretched as it arrives, the pitch kept, so a slow caller is slow and not
# low. At the vendor's own tempo nothing is touched.
async def at_tempo(pieces: AsyncIterable[bytes], line: Line) -> AsyncIterator[bytes]:
    """The audio at the line's tempo, piece by piece."""
    if line.speed == AS_READ:
        async for piece in pieces:
            yield piece
        return
    stretcher = Stretcher(line.speed, SAMPLE_RATE)
    async for piece in pieces:
        stretched = stretcher.push(piece)
        if stretched:
            yield stretched
    rest = stretcher.flush()
    if rest:
        yield rest


def frames_of(pcm: bytes, rate: int) -> list[bytes]:
    """The audio cut in 10 ms frames, the last padded with silence: a room refuses a short one."""
    size = (rate * FRAME_MS // 1000) * 2
    frames = [pcm[start : start + size] for start in range(0, len(pcm), size)]
    if frames and len(frames[-1]) < size:
        frames[-1] += LOST * ((size - len(frames[-1])) // 2)
    return frames


def rms_of(pcm: bytes) -> float:
    """The level of 16-bit audio."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    if not samples.size:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


# Averaged in power over the frames that carry speech, as an active speech level is: the gaps
# between words, and the silence between lines, do not make a caller quieter.
@dataclass(slots=True)
class SpokenLevel:
    """How loud the caller speaks: the level of its frames that carry speech, over the call so far."""

    power: float = A_VOICE_RMS * A_VOICE_RMS * A_GUESS_WEIGHS_FRAMES
    frames: int = A_GUESS_WEIGHS_FRAMES

    def hear(self, frame: bytes) -> None:
        """Count one frame of the caller's voice, when it is speech."""
        level = rms_of(frame)
        if level >= A_GAP_RMS:
            self.power += level * level
            self.frames += 1

    @property
    def rms(self) -> float:
        """The level, as the level of 16-bit audio."""
        return math.sqrt(self.power / self.frames)


# The interferer loops, so a few seconds of it last a call; `start` is the sample it goes on from,
# so the line hears one television from its first frame to its last.
def behind(frame: bytes, interferer: bytes, start: int, gain: float) -> bytes:
    """The frame with the interferer behind it, from sample `start` of it on, multiplied by `gain`."""
    voice = np.frombuffer(frame, dtype=np.int16).astype(np.int64)
    room = np.take(np.frombuffer(interferer, dtype=np.int16), np.arange(start, start + voice.size), mode="wrap")
    mixed = voice + (room * gain).astype(np.int64)
    return np.clip(mixed, QUIETEST, LOUDEST).astype(np.int16).tobytes()


# One resampler for the whole line: each piece leaves a few samples in it for the next.
async def resampled(frames: AsyncIterable[rtc.AudioFrame]) -> AsyncIterator[bytes]:
    """The audio at the room's rate, piece by piece, as it was when it already is."""
    resampler = None
    async for frame in frames:
        if frame.sample_rate == SAMPLE_RATE:
            yield bytes(frame.data)
            continue
        if resampler is None:
            resampler = rtc.AudioResampler(frame.sample_rate, SAMPLE_RATE, num_channels=CHANNELS)
        for piece in resampler.push(frame):
            yield bytes(piece.data)
    if resampler is not None:
        for piece in resampler.flush():
            yield bytes(piece.data)


# A piece ends where the vendor cut it, not on a frame: the rest waits for the next piece, and
# only the line's end is padded.
async def in_frames(pieces: AsyncIterable[bytes]) -> AsyncIterator[bytes]:
    """The audio in the room's frames, as the pieces arrive."""
    size = len(SILENCE)
    rest = b""
    async for piece in pieces:
        whole = rest + piece
        cut = len(whole) - len(whole) % size
        for frame in frames_of(whole[:cut], SAMPLE_RATE):
            yield frame
        rest = whole[cut:]
    for frame in frames_of(rest, SAMPLE_RATE):
        yield frame


# The operator's voices per language are the ones an agent speaks with when it names none; the
# caller takes the persona's own unless it is the agent's, else one the agent is not using, in its
# language, else in English, else the plugin's.
def pick_caller_voice(
    voices: Mapping[str, str], vendor: str, agents_voice: str | None, language: str | None, wanted: str | None = None
) -> str | None:
    """The voice the caller speaks with: the persona's when it has one, never the agent's."""
    own = f"{vendor}/{providers.primary_language(language) or 'en'}"
    ordered = [wanted, voices.get(own), voices.get(f"{vendor}/en")]
    ordered += [voice for key, voice in voices.items() if key.startswith(f"{vendor}/")]
    return next((voice for voice in ordered if voice and voice != agents_voice), None)


# Deleting the room is the endpoint's: it ends the agent's job, which seals the log.
async def run_spoken(
    spoken: SpokenLine, voice: tts.TTS[Never], logs: calls.Logs, next_line: NextLine, said: list[Said] | None = None
) -> int:
    """Join the room as the caller, say the lines as the agent answers, and hang up; what it said lands in `said`."""
    room = rtc.Room()
    async with http_context.open():
        interferer = b""
        if spoken.line.interferer_db is not None:
            chatter = b""
            if spoken.line.ambience in ambiences.VOICED:
                chatter = await synthesized(voice, A_TELEVISION)
            interferer = ambiences.sound_of(spoken.line.ambience, chatter)
        leg = CallerLeg(spoken, voice, logs, interferer)
        await room.connect(spoken.url, spoken.token)
        try:
            # Published before the agent arrives: audio pushed before a subscription is lost.
            await room.local_participant.publish_track(
                leg.track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            # The room behind the caller is heard from here: the agent greets a line that already has it.
            leg.open()
            await _until_the_agent_is_here(room, spoken.call)
            said_count = await speak_turns(spoken.turns, next_line, leg.say, leg.line_answered)
            # Waited again, whole: hanging up at once would cut the agent's last answer.
            await answered(logs, spoken.call, said_count, since=leg.said_at)
            # Said before leaving, as a widget's hang-up is: the call ends caller_hung_up now, not drained
            # once the room is deleted, with the silence between the two billed.
            await room.local_participant.publish_data(b"{}", reliable=True, topic=session.HANGUP)
            return said_count
        finally:
            await leg.close()
            if said is not None:
                said.extend(leg.spoke)
            await room.disconnect()


async def synthesized(voice: tts.TTS[Never], text: str) -> bytes:
    """A line spoken whole, at the room's rate."""
    async with voice.synthesize(text) as stream:
        pieces = resampled(piece.frame async for piece in stream)
        return b"".join([piece async for piece in pieces])


# The agent joins before its session is built; its published audio means it listens.
async def _until_the_agent_is_here(room: rtc.Room, call: str) -> None:
    def listening() -> bool:
        return any(
            publication.kind == rtc.TrackKind.KIND_AUDIO
            for participant in room.remote_participants.values()
            for publication in participant.track_publications.values()
        )

    for _ in range(int(THE_AGENT_MAY_TAKE_S / A_BEAT_S)):
        if listening():
            return
        await asyncio.sleep(A_BEAT_S)
    raise TimeoutError(NOBODY_ANSWERED.format(call=call, seconds=THE_AGENT_MAY_TAKE_S))
