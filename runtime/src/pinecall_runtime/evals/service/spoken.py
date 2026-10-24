"""A persona on a real line: the caller's leg in the room, its lines spoken, the noise on it."""

import asyncio
import random as randomness
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Never

import numpy as np
from livekit import rtc
from livekit.agents import tts
from livekit.agents.utils import http_context

from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.service import ambience as ambiences
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
# A television 15 dB under the caller was already transcribed as the caller.
UNDER_THE_CALLER_DB = 15.0
# Every line is resampled to this rate, so the caller's track opens before any audio exists.
SAMPLE_RATE = 48_000
CHANNELS = 1
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


class CallerLeg:
    """The caller's leg of a spoken call: its track in the room, its voice, the line's noise."""

    def __init__(self, spoken: SpokenLine, voice: tts.TTS[Never], logs: calls.Logs, interferer: bytes) -> None:
        """A leg with its track made and nothing said yet."""
        self.spoken = spoken
        self.voice = voice
        self.logs = logs
        self.interferer = interferer
        self.source = rtc.AudioSource(SAMPLE_RATE, CHANNELS)
        self.track = rtc.LocalAudioTrack.create_audio_track(judging.A_SIMULATED_CALLER, self.source)
        # When the caller began its last line, by the log's clock: its answer comes after it.
        self.said_at = logs.store.clock()
        # Set once the caller decided to talk over the answer: its next line is said with no pause.
        self.cutting_in = False

    # The line is spoken as the vendor sends it, never held until it is whole: a caller that
    # waited for its last word before its first was seconds late on every turn.
    async def say(self, line: str) -> None:
        """Speak one line into the room, after the caller's pause (none when cutting in), through the line's noise."""
        if not self.cutting_in:
            await asyncio.sleep(self.spoken.line.pause_s)
        self.cutting_in = False
        self.said_at = self.logs.store.clock()
        await self._speak(line)

    # A murmur rides the agent's answer: it moves no clock, so the answer is still waited for whole.
    async def murmur(self, word: str) -> None:
        """Say one listener's word into the room while the agent speaks, keeping the turn."""
        await self._speak(word)

    async def _speak(self, text: str) -> None:
        async with self.voice.synthesize(text) as stream:
            pieces = at_tempo(resampled(piece.frame async for piece in stream), self.spoken.line)
            async for frame in on_the_line(pieces, self.spoken.line, self.interferer):
                await self.source.capture_frame(rtc.AudioFrame(frame, SAMPLE_RATE, CHANNELS, len(frame) // 2))

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
    behavior: judging.CallerBehavior, interferer_db: float | None, packet_loss: float, ambience: str | None = None
) -> Line:
    """The line a caller acting so is on: the noise the request names, else the persona's own."""
    return Line(
        interferer_db=behavior.interferer_db if interferer_db is None else interferer_db,
        packet_loss=packet_loss or behavior.packet_loss,
        interrupts=behavior.interrupts,
        pause_s=behavior.pause_s,
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


# The interferer loops, so a short one covers a long line; `start` is the sample it goes on
# from, so a line mixed piece by piece hears one television, not one restarted at every piece.
def mix_interferer(caller: bytes, interferer: bytes, db_under: float = UNDER_THE_CALLER_DB, start: int = 0) -> bytes:
    """The interferer mixed under the caller's voice, `db_under` quieter."""
    if not interferer or not caller:
        return caller
    loudness = rms_of(interferer)
    gain = 0.0 if loudness == 0 else rms_of(caller) / loudness * 10 ** (-db_under / 20)
    voice = np.frombuffer(caller, dtype=np.int16).astype(np.int64)
    television = np.frombuffer(interferer, dtype=np.int16)
    noise = np.take(television, np.arange(start, start + voice.size), mode="wrap")
    mixed = voice + (noise * gain).astype(np.int64)
    return np.clip(mixed, QUIETEST, LOUDEST).astype(np.int16).tobytes()


def drop_packets(frames: Sequence[bytes], line: Line) -> list[bytes]:
    """The frames with the line's share of them lost."""
    if line.packet_loss <= 0:
        return list(frames)
    return [LOST * (len(frame) // 2) if line.dice.random() < line.packet_loss else frame for frame in frames]


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
# only the line's end is padded. The interferer's level follows each piece of the voice.
async def on_the_line(pieces: AsyncIterable[bytes], line: Line, interferer: bytes) -> AsyncIterator[bytes]:
    """The audio as the line carries it, in frames: the interferer under it, its packets lost."""
    size = (SAMPLE_RATE * FRAME_MS // 1000) * 2
    rest = b""
    heard = 0
    async for piece in pieces:
        carried = piece
        if line.interferer_db is not None:
            carried = mix_interferer(piece, interferer, line.interferer_db, start=heard)
        heard += len(carried) // 2
        whole = rest + carried
        cut = len(whole) - len(whole) % size
        for frame in drop_packets(frames_of(whole[:cut], SAMPLE_RATE), line):
            yield frame
        rest = whole[cut:]
    for frame in drop_packets(frames_of(rest, SAMPLE_RATE), line):
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
async def run_spoken(spoken: SpokenLine, voice: tts.TTS[Never], logs: calls.Logs, next_line: NextLine) -> int:
    """Join the room as the caller, say the lines as the agent answers, and hang up."""
    room = rtc.Room()
    async with http_context.open():
        interferer = b""
        if spoken.line.interferer_db is not None:
            chatter = b""
            if spoken.line.ambience in ambiences.VOICED:
                chatter = await synthesized(voice, A_TELEVISION)
            interferer = ambiences.sound_of(spoken.line.ambience, chatter)
        await room.connect(spoken.url, spoken.token)
        try:
            leg = CallerLeg(spoken, voice, logs, interferer)
            # Published before the agent arrives: audio pushed before a subscription is lost.
            await room.local_participant.publish_track(
                leg.track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            await _until_the_agent_is_here(room, spoken.call)
            said_count = await speak_turns(spoken.turns, next_line, leg.say, leg.line_answered)
            # Waited again, whole: hanging up at once would cut the agent's last answer.
            await answered(logs, spoken.call, said_count, since=leg.said_at)
            # Said before leaving, as a widget's hang-up is: the call ends caller_hung_up now, not drained
            # once the room is deleted, with the silence between the two billed.
            await room.local_participant.publish_data(b"{}", reliable=True, topic=session.HANGUP)
            return said_count
        finally:
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
