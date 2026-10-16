"""Tests for the caller's tempo: as long as the speed asks, the pitch kept, pieces as whole."""

import math
from array import array
from itertools import pairwise

from pinecall_runtime.evals.service.tempo import FRAME_S, RATE, Stretcher

# A tone of this period at the room's rate: 480 Hz, a voice's pitch.
PERIOD = 100

# A stretch lands within this of the length asked for: a frame either side.
WITHIN = 0.03

# The pitch comes back within this of itself.
PITCH_WITHIN = 0.05

# At the vendor's own tempo the length moves by the padding alone: under this many frames.
WITHIN_FRAMES = 2


def tone_of(samples: int, period: int = PERIOD) -> bytes:
    written = array("h")
    for index in range(samples):
        written.append(int(8000 * math.sin(2 * math.pi * index / period)))
    return written.tobytes()


def stretched(pcm: bytes, speed: float, piece: int | None = None) -> bytes:
    stretcher = Stretcher(speed, RATE)
    if piece is None:
        return stretcher.push(pcm) + stretcher.flush()
    out = b"".join(stretcher.push(pcm[at : at + piece]) for at in range(0, len(pcm), piece))
    return out + stretcher.flush()


def crossings_per_second(pcm: bytes) -> float:
    samples = array("h")
    samples.frombytes(pcm)
    crossed = sum(1 for a, b in pairwise(samples) if (a < 0) != (b < 0))
    return crossed / (len(samples) / RATE)


def test_twice_as_fast_is_half_as_long_and_half_as_fast_twice() -> None:
    second = tone_of(RATE)
    quick = len(stretched(second, 2.0)) / len(second)
    slow = len(stretched(second, 0.5)) / len(second)
    assert abs(quick - 0.5) < WITHIN
    assert abs(slow - 2.0) < WITHIN * 2


def test_the_pitch_is_the_tones_own_at_either_tempo() -> None:
    second = tone_of(RATE)
    pitch = crossings_per_second(second)
    for speed in (0.6, 1.5):
        assert abs(crossings_per_second(stretched(second, speed)) / pitch - 1.0) < PITCH_WITHIN


def test_the_vendors_own_tempo_keeps_the_length_but_for_the_padding() -> None:
    second = tone_of(RATE)
    moved = abs(len(stretched(second, 1.0)) - len(second)) // 2
    assert moved <= WITHIN_FRAMES * int(RATE * FRAME_S)


def test_a_line_in_pieces_comes_out_as_it_would_whole() -> None:
    second = tone_of(RATE)
    assert stretched(second, 1.3, piece=1_000) == stretched(second, 1.3)


def test_nothing_pushed_is_nothing_out() -> None:
    stretcher = Stretcher(1.5, RATE)
    assert stretcher.push(b"") == b""
    assert stretcher.flush() == b""
