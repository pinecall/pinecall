"""The caller's audio with what sits far under their own voice muted: the nearest voice is the caller's."""

from collections import deque
from collections.abc import Callable
from typing import override

import numpy as np
from livekit import rtc

from runtime.session.far_voices import FarVoices

# One microphone cannot tell two voices apart without a model; it can tell which one is near. The
# caller speaks into the microphone and a television, a colleague or a waiting room is across the
# room, so the room's voices arrive well under the caller's own. On 2026-11-14 a simulated caller
# with a television 30 dB under her was heard right, and then the agent never answered: the
# television was taken for her speaking again a quarter of a second after her turn closed, the
# reply it stopped was never said, and thirty seconds of news became her next turn. livekit levels
# the caller's audio (its automatic gain) and, with the caller quiet, levelled the television up to
# a voice's loudness in twelve seconds; so the room is muted here, before that gain hears it.
# Muted, never turned down: what is turned down the gain turns up again. Where the box has the model
# that takes far voices down (far_voices.py) the frame goes through it first, so a room that is not
# faint falls under the bar too.
# What it cannot do: a voice as loud as the caller's at the microphone is a second caller to it,
# and a person the caller hands the phone to from across the room is heard only once the caller has
# been quiet for a while (FORGOTTEN_AFTER_S).

# A level is taken every 10 ms: shorter than any syllable, as long as the canceller's own slice.
SLICES_PER_SECOND = 100
# How far under the caller's loud level a sound is the room's. At 20 a television 30 dB under the
# caller was silent and one 18 under passed whole (2026-11-15, a simulated call nobody answered). At
# 12, on a real newscast across a real living room: one 24 under was silent with no model before it,
# and with the model one 18 under was too, but for the words it said before the caller's first; one
# 12 under still passed in part. What the bar costs the caller was measured on three minutes of
# people speaking on air, in English and Spanish: no word lost at 20, 15 or 12, with 0 to 9 % of the
# audio muted, all of it between words. A broadcast is levelled as a phone's own microphone is, and
# a caller who trails off is where a lower bar would show first.
UNDER_THE_VOICE_DB = 12.0
# The caller's loud level is this percentile of the levels that carried their voice: above the
# consonants, under a cough.
LOUD = 85
# Over this much of their own speech, so a laugh or a raised voice is gone from it three seconds of
# talking later; time in which nothing passed is not counted, or the room would become the voice.
VOICE_OVER_S = 3.0
# Nothing is muted until this much sound was heard: one syllable says nothing of how loud a caller is.
HEARD_FOR_S = 0.3
# The line stays open this long after the voice's last loud slice: the gap between two words, a
# syllable's tail, a breath in the middle of a sentence.
HELD_S = 0.25
# A caller who moves away from the microphone, or hands the phone over, is now far under what the
# call took for their voice. After this long of the caller's own time (the agent not speaking) with
# nothing passing, the voice is learnt again from whatever the line carries: about when an agent's
# idle line asks whether they are there, so whoever answers it is heard.
FORGOTTEN_AFTER_S = 8.0


class NearestVoice(rtc.FrameProcessor[rtc.AudioFrame]):
    """One call's line, each frame as it came or silent: silent when nothing in it is near the caller's own level."""

    def __init__(self, caller_has_the_floor: Callable[[], bool], far_voices: FarVoices | None = None) -> None:
        """A line nobody was heard on yet: everything passes until a voice is known."""
        self.caller_has_the_floor = caller_has_the_floor
        # The model's stream for this call, where the box has the model: heard through before the level is read.
        self.far_voices = far_voices
        self.muting = True
        # The levels, in dB, of the slices that carried the voice, over VOICE_OVER_S of them.
        self.voiced: deque[float] = deque(maxlen=round(VOICE_OVER_S * SLICES_PER_SECOND))
        # Since the last frame that carried the voice, and since then on the caller's own time.
        self.quiet_s = 0.0
        self.unheard_s = 0.0

    @property
    @override
    def enabled(self) -> bool:
        """Whether the room is muted; livekit hands every frame over only while it is."""
        return self.muting

    @enabled.setter
    @override
    def enabled(self, value: bool) -> None:
        self.muting = value

    @property
    def bar(self) -> float:
        """The level, in dB, under which a sound is the room's; nothing is, until a voice was heard."""
        if len(self.voiced) < HEARD_FOR_S * SLICES_PER_SECOND:
            return -np.inf
        return float(np.percentile(np.fromiter(self.voiced, dtype=np.float64), LOUD)) - UNDER_THE_VOICE_DB

    # A frame carries the voice when any slice of it does, and then passes whole: the soft start of
    # a word is in the frame its vowel is in more often than not, and costs no delay to keep.
    def hear(self, frame: rtc.AudioFrame) -> rtc.AudioFrame:
        """The frame as it came while it carries the caller's voice or follows it closely, else silence as long."""
        if self.far_voices is not None:
            frame = self.far_voices.clear(frame)
        levels = levels_of(frame)
        near = levels[levels >= self.bar]
        if near.size:
            self.voiced.extend(near.tolist())
            self.quiet_s = self.unheard_s = 0.0
            return frame
        self.quiet_s += frame.duration
        if self.quiet_s <= HELD_S:
            return frame
        if self.caller_has_the_floor():
            self.unheard_s += frame.duration
        if self.unheard_s >= FORGOTTEN_AFTER_S:
            self.voiced.clear()
            self.unheard_s = 0.0
        return rtc.AudioFrame(
            data=bytes(len(frame.data.tobytes())),
            sample_rate=frame.sample_rate,
            num_channels=frame.num_channels,
            samples_per_channel=frame.samples_per_channel,
        )

    @override
    def _process(self, frame: rtc.AudioFrame) -> rtc.AudioFrame:
        return self.hear(frame)

    @override
    def _close(self) -> None:
        self.voiced.clear()
        if self.far_voices is not None:
            self.far_voices.close()


# Digital silence has no level: it is left out, so a line that carries nothing teaches nothing.
def levels_of(frame: rtc.AudioFrame) -> np.ndarray:
    """The level, in dB, of each 10 ms of the frame that carries any sound at all."""
    samples = np.frombuffer(frame.data.tobytes(), dtype=np.int16).astype(np.float64)
    if not samples.size:
        return samples
    size = max(1, frame.sample_rate // SLICES_PER_SECOND) * frame.num_channels
    count = samples.size // size
    # A frame shorter than a slice is one slice; what is left over after the last whole one is not weighed.
    slices = samples[: count * size].reshape(count, size) if count else samples.reshape(1, -1)
    power = np.mean(np.square(slices), axis=1)
    return 10.0 * np.log10(power[power > 0])
