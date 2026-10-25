"""PCM encoded as MP3: a file every browser plays, as long as the samples were."""

import io
import math
import struct

import av
from av.audio.stream import AudioStream

from pinecall_runtime.kit.mp3 import mp3_of

RATE = 24_000


def a_tone(seconds: float) -> bytes:
    """A 440 Hz tone as 16-bit mono samples."""
    count = round(RATE * seconds)
    return b"".join(struct.pack("<h", round(8000 * math.sin(2 * math.pi * 440 * at / RATE))) for at in range(count))


def test_two_seconds_of_samples_are_an_mp3_two_seconds_long_at_the_bit_rate_asked() -> None:
    mp3 = mp3_of(a_tone(2.0), rate=RATE, channels=1, bit_rate=48_000)

    with av.open(io.BytesIO(mp3), mode="r") as read:
        stream: AudioStream = read.streams.audio[0]
        samples = sum(frame.samples for frame in read.decode(audio=0))
        assert stream.codec_context.name.startswith("mp3")
        assert stream.rate == RATE
    assert abs(samples / RATE - 2.0) < 0.06
    assert 9_000 < len(mp3) < 16_000


def test_a_tail_shorter_than_one_frame_is_kept() -> None:
    mp3 = mp3_of(a_tone(0.01), rate=RATE, channels=1, bit_rate=48_000)

    with av.open(io.BytesIO(mp3), mode="r") as read:
        assert sum(frame.samples for frame in read.decode(audio=0)) > 0
