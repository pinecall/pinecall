"""The caller's leg of a spoken call: its track in the room, its voice, the noise of the line it is on."""

import asyncio
import math
import random as randomness
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Never

from livekit import rtc
from livekit.agents import tts

from runtime.calls.log import Logs, Store
from runtime.evals.service import turns
from runtime.evals.service.hearing import Said
from runtime.judging import service as judging
from runtime.kit.link import LinkShape
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
# A caller slower than read says its words a third of the way slower and leaves the rest of its
# slowness as silence where the voice already breaks: this long at half speed, a little more or less
# each time, wherever the voice was quiet for as long as a gap between two phrases is.
A_THIRD = 3
A_PAUSE_AT_HALF_SPEED_S = 0.9
A_PAUSE_VARIES = (0.6, 1.4)
A_BREAK_FRAMES = 9
# A room heard behind some of the caller's lines alone comes up and goes down over this many frames.
A_ROOM_FADES_FRAMES = 25
# What a listener murmurs while the other speaks, without taking the turn, by language.
MURMURS: Mapping[str, tuple[str, ...]] = {
    "es": ("ajá", "mm", "sí, sí"),
    "en": ("mm-hmm", "uh-huh", "right"),
    "pt": ("uhum", "sim, sim"),
    "fr": ("hm hm", "oui"),
    "de": ("mhm", "ja"),
    "it": ("mh mh", "sì"),
    "ar": ("آه", "تمام", "أيوه"),
    "hi": ("हाँ", "जी", "अच्छा"),
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
    # The network between the caller and the room: what it loses, how long it holds, how much it carries.
    network: LinkShape = field(default_factory=LinkShape)


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
        # Whether the room is heard now, and how much of it: all of it for a room that never stops.
        self.heard = spoken.acts.ambience_turns >= 1.0
        self.room = 1.0 if self.heard else 0.0
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
            # The caller hears the answer's end the network's delay late, and its own voice then
            # crosses the same network back: the first half is waited here, the second is the link's.
            await asyncio.sleep(self.spoken.acts.pause_s + self.spoken.network.delay_ms / 1000)
        self.cutting_in = False
        self.said_at = self.store.clock()
        # A room heard behind some lines alone is thrown for at each one, and is gone with its last word.
        whole = self.spoken.acts.ambience_turns >= 1.0
        self.heard = whole or self.dice.random() < self.spoken.acts.ambience_turns
        await self._speak(line)
        self.heard = whole
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
        """The next 10 ms of the line: the caller's voice or its silence, and the room behind it."""
        acts = self.spoken.acts
        frame = SILENCE
        if self.waiting:
            frame = self.waiting.popleft()
            self.level.hear(frame)
        else:
            self.silent.set()
        if acts.interferer_db is not None and self.loudness > 0:
            step = 1.0 / A_ROOM_FADES_FRAMES
            self.room = min(1.0, self.room + step) if self.heard else max(0.0, self.room - step)
            if self.room > 0:
                gain = self.level.rms / self.loudness * 10 ** (-acts.interferer_db / 20) * self.room
                frame = mix_under(frame, self.interferer, self.carried, gain)
        self.carried += len(frame) // 2
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
            speed = self.spoken.acts.speed
            pieces = at_tempo(resample(piece.frame async for piece in stream), tempo_of(speed))
            async for frame in with_pauses(in_frames(pieces, SAMPLE_RATE, FRAME_MS), speed, self.dice):
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


# Until 2026-11-17 a lost packet was ten milliseconds of the caller's track silenced before it was
# encoded: the room never missed a packet, and nothing of what a network does to a call beside losing
# it (a delay, its jitter, a rate too low) could be said. The line's network is a link the caller's
# packets really cross now (`spoken.py`), and this is how a report words it.
def describe(acts: judging.Behavior, network: LinkShape, *, by_phone: bool = False) -> str:
    """The line a caller acting so is on, in the words a report prints."""
    said = ["a phone line"] if by_phone else []
    if acts.interferer_db is not None:
        some = "" if acts.ambience_turns >= 1.0 else f" in {acts.ambience_turns * 100:.0f}% of its lines"
        said.append(f"{acts.ambience} {acts.interferer_db:.0f} dB under the caller{some}")
    if network.loss > 0:
        said.append(f"{network.loss * 100:.0f}% packet loss")
    if network.delay_ms > 0 or network.jitter_ms > 0:
        jitter = f" ± {network.jitter_ms:.0f} ms" if network.jitter_ms > 0 else ""
        said.append(f"{network.delay_ms:.0f} ms delay{jitter}")
    if network.rate_kbps is not None:
        said.append(f"{network.rate_kbps:.0f} kbps")
    return ", ".join(said) or "a clean line"


async def synthesize(voice: tts.TTS[Never], text: str) -> bytes:
    """A line spoken whole, at the room's rate."""
    async with voice.synthesize(text) as stream:
        pieces = resample(piece.frame async for piece in stream)
        return b"".join([piece async for piece in pieces])


# A person who talks slowly is not a recording played slowly: the words come almost as anybody says
# them, and the time goes into the silences between them. Until 2026-11-25 a caller at `speed` 0.8 was
# its whole line stretched to five quarters, every syllable drawn out and not one pause: slow, and
# like nobody.
def tempo_of(speed: float) -> float:
    """How fast a caller at this speed says its words: as asked when faster, a third of the way when slower."""
    return speed if speed >= AS_READ else AS_READ - (AS_READ - speed) / A_THIRD


async def with_pauses(frames: AsyncIterable[bytes], speed: float, dice: randomness.Random) -> AsyncIterator[bytes]:
    """The line's frames, each break the voice made held longer for a caller slower than read."""
    if speed >= AS_READ:
        async for frame in frames:
            yield frame
        return
    held_s = A_PAUSE_AT_HALF_SPEED_S * (AS_READ / speed - AS_READ)
    spoke, quiet = False, 0
    async for frame in frames:
        yield frame
        if rms_of(frame) >= A_GAP_RMS:
            spoke, quiet = True, 0
            continue
        quiet += 1
        # Once a break: the silence the voice left goes on after the pause, and before the line's first
        # word there is nothing to hold.
        if spoke and quiet == A_BREAK_FRAMES:
            for _ in range(round(held_s * dice.uniform(*A_PAUSE_VARIES) * 1000 / FRAME_MS)):
                yield SILENCE


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
