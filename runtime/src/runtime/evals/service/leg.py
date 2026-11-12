"""The caller's leg of a spoken call: its track in the room, its voice, the noise of the line it is on."""

import asyncio
import math
import random as randomness
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Never

from livekit import rtc
from livekit.agents import tts

from runtime.calls.log import Logs, Store
from runtime.evals.service import turns
from runtime.evals.service.hearing import Said
from runtime.judging import service as judging
from runtime.kit.pcm import QUIET, in_frames, mix_under, rms_of
from runtime.kit.tempo import Stretcher
from runtime.providers.stage import primary_language
from runtime.wire.room import A_SIMULATED_CALLER

# 10 ms of 16-bit mono per frame, the cadence livekit's examples publish at.
FRAME_MS = 10
# Every line is resampled to this rate, so the caller's track opens before any audio exists.
SAMPLE_RATE = 48_000
CHANNELS = 1
# What the caller's track carries while the caller says nothing.
SILENCE = QUIET * (SAMPLE_RATE * FRAME_MS // 1000)
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


@dataclass(frozen=True, slots=True)
class Spoken:
    """A spoken call as its caller acts on it: the call, how the caller behaves, in what language, behind a notice."""

    call: str
    acts: judging.Behavior
    # The caller's language, for the words it murmurs; None murmurs in English.
    language: str | None = None
    # Whether the agent says the org's recording notice before its greeting.
    notice: bool = False


# The room behind a caller does not stop when the caller does: the track carries it from the moment
# the caller joins until it hangs up, under the agent's answers and through every silence, which is
# where a noisy line breaks an agent (a television taken for a caller cutting in, a turn that never
# ends). Until 2026-11-09 the noise was mixed into each spoken line alone, at a level that followed
# each piece of the voice, and between two lines the track was digital silence.
class CallerLeg:
    """The caller's leg of a spoken call: its track in the room, its voice, the line's noise."""

    def __init__(
        self,
        spoken: Spoken,
        voice: tts.TTS[Never],
        logs: Logs,
        store: Store,
        interferer: bytes,
        dice: randomness.Random | None = None,
    ) -> None:
        self.spoken = spoken
        self.voice = voice
        self.logs = logs
        self.store = store
        self.interferer = interferer
        self.dice = dice or randomness.Random()
        # The interferer's own level, taken once: it is seconds long and asked for a hundred times a second.
        self.loudness = rms_of(interferer)
        self.level = SpokenLevel()
        self.source = rtc.AudioSource(SAMPLE_RATE, CHANNELS, queue_size_ms=AHEAD_MS)
        self.track = rtc.LocalAudioTrack.create_audio_track(A_SIMULATED_CALLER, self.source)
        # The frames of the caller's voice not yet on the line, and whether there are none.
        self.waiting: deque[bytes] = deque()
        self.silent = asyncio.Event()
        # The samples the line has carried: where the interferer goes on from.
        self.carried = 0
        self.carrying: asyncio.Future[None] | None = None
        # What the caller said and when, by the log's clock: what the agent's hearing is measured against.
        self.spoke: list[Said] = []
        # When the caller began its last line, by the log's clock: its answer comes after it.
        self.said_at = store.clock()
        # Set once the caller decided to talk over the answer: its next line is said with no pause.
        self.cutting_in = False
        # Set when the caller leaves: the line is carried until then.
        self.closed = False

    # The line is spoken as the vendor sends it, never held until it is whole: a caller that
    # waited for its last word before its first was seconds late on every turn.
    async def say(self, line: str) -> None:
        """Speak one line into the room, after the caller's pause (none when cutting in), through the line's noise."""
        cut_in = self.cutting_in
        if not cut_in:
            await asyncio.sleep(self.spoken.acts.pause_s)
        self.cutting_in = False
        self.said_at = self.store.clock()
        await self._speak(line)
        self.spoke.append(Said("line", line, self.said_at, self.store.clock(), cut_in=cut_in))

    # A murmur rides the agent's answer: it moves no clock, so the answer is still waited for whole.
    async def murmur(self, word: str) -> None:
        """Say one listener's word into the room while the agent speaks, keeping the turn."""
        began = self.store.clock()
        await self._speak(word)
        self.spoke.append(Said("murmur", word, began, self.store.clock()))

    def open(self) -> None:
        """Start carrying the line: from here the track is never without a frame."""
        self.carrying = asyncio.ensure_future(self._carry())
        # A line that broke leaves nobody waiting on it: the one speaking is woken and told.
        self.carrying.add_done_callback(lambda _: self.silent.set())

    async def close(self) -> None:
        """Stop carrying the line."""
        self.closed = True
        if self.carrying is not None:
            self.carrying.cancel()
            await asyncio.gather(self.carrying, return_exceptions=True)

    # The interferer sits under how loud the caller speaks over the call, never under each piece of
    # its voice: a room does not get louder with the person in it.
    def next_frame(self) -> bytes:
        """The next 10 ms of the line: the caller's voice or its silence, the room behind it, or a lost packet."""
        acts = self.spoken.acts
        frame = SILENCE
        if self.waiting:
            frame = self.waiting.popleft()
            self.level.hear(frame)
        else:
            self.silent.set()
        if acts.interferer_db is not None and self.loudness > 0:
            gain = self.level.rms / self.loudness * 10 ** (-acts.interferer_db / 20)
            frame = mix_under(frame, self.interferer, self.carried, gain)
        self.carried += len(frame) // 2
        if acts.packet_loss > 0 and self.dice.random() < acts.packet_loss:
            return QUIET * (len(frame) // 2)
        return frame

    # Cut in some way into the answer, as a person does: never at its first word. A caller that cuts in
    # asks for its line the moment the agent begins (what it talks over, it has not heard) and says
    # it with no pause, or the answer is over before it opens its mouth. A caller that murmurs waits for
    # the answer like any other, its "mm-hmm" said along the way.
    async def wait_for_answer(self, lines: int, landed: turns.Landed) -> bool:
        """Wait until the agent answered this many lines, or cut in once it started answering: True to speak."""
        acts, call = self.spoken.acts, self.spoken.call
        if lines and self.dice.random() < acts.interrupts:
            await turns.wait_until_speaking(self.logs, self.store, call, since=self.said_at)
            landed()
            await asyncio.sleep(self.dice.uniform(*CUT_IN_AFTER_S))
            self.cutting_in = True
            return True
        if lines and self.dice.random() < acts.backchannels:
            await turns.wait_until_speaking(self.logs, self.store, call, since=self.said_at)
            await asyncio.sleep(self.dice.uniform(*MURMUR_AFTER_S))
            await self.murmur(pick_murmur(self.spoken.language, self.dice))
        return await turns.wait_for_answer(
            self.logs, self.store, call, lines, since=self.said_at, landed=landed, notice=self.spoken.notice
        )

    # The source paces the frames it is handed: this loop runs at the clock's rate, AHEAD_MS ahead.
    async def _carry(self) -> None:
        while not self.closed:
            frame = self.next_frame()
            await self.source.capture_frame(rtc.AudioFrame(frame, SAMPLE_RATE, CHANNELS, len(frame) // 2))

    # The voice is handed to the line as it arrives and the line says it at the clock's rate: a line
    # is said once the last of its frames has left.
    async def _speak(self, text: str) -> None:
        async with self.voice.synthesize(text) as stream:
            pieces = at_tempo(resample(piece.frame async for piece in stream), self.spoken.acts.speed)
            async for frame in in_frames(pieces, SAMPLE_RATE, FRAME_MS):
                self.silent.clear()
                self.waiting.append(frame)
        # A line that broke before the last frame was handed to it will never say it.
        self._check_carrying()
        await self.silent.wait()
        self._check_carrying()

    def _check_carrying(self) -> None:
        if self.carrying is not None and self.carrying.done():
            self.carrying.result()


def pick_murmur(language: str | None, dice: randomness.Random) -> str:
    """One of the words a listener murmurs in the caller's language, by the dice."""
    words = MURMURS.get(primary_language(language) or "en", MURMURS["en"])
    return dice.choice(words)


def describe(acts: judging.Behavior) -> str:
    """The line a caller acting so is on, in the words a report prints."""
    if acts.interferer_db is None and acts.packet_loss <= 0:
        return "a clean line"
    noise = f"{acts.ambience} {acts.interferer_db or 0.0:.0f} dB under the caller"
    return noise if acts.packet_loss <= 0 else f"{noise}, {acts.packet_loss * 100:.0f}% packet loss"


async def synthesize(voice: tts.TTS[Never], text: str) -> bytes:
    """A line spoken whole, at the room's rate."""
    async with voice.synthesize(text) as stream:
        pieces = resample(piece.frame async for piece in stream)
        return b"".join([piece async for piece in pieces])


# The vendor's audio is stretched as it arrives, the pitch kept, so a slow caller is slow and not
# low. At the vendor's own tempo nothing is touched.
async def at_tempo(pieces: AsyncIterable[bytes], speed: float) -> AsyncIterator[bytes]:
    """The audio at the tempo given, piece by piece."""
    if speed == AS_READ:
        async for piece in pieces:
            yield piece
        return
    stretcher = Stretcher(speed, SAMPLE_RATE)
    async for piece in pieces:
        stretched = stretcher.push(piece)
        if stretched:
            yield stretched
    rest = stretcher.flush()
    if rest:
        yield rest


# One resampler for the whole line: each piece leaves a few samples in it for the next.
async def resample(frames: AsyncIterable[rtc.AudioFrame]) -> AsyncIterator[bytes]:
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
