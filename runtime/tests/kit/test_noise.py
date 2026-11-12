"""Noise made from a seed: a hum that keeps the low notes alone, a swell that keeps the level it was given."""

from array import array
from itertools import pairwise

import numpy as np

from runtime.kit.noise import hum, pink, swell

RATE = 48_000
SECONDS = 8
SEED = 7


def crossings_per_second(pcm: bytes) -> float:
    samples = array("h")
    samples.frombytes(pcm)
    crossed = sum(1 for a, b in pairwise(samples) if (a < 0) != (b < 0))
    return crossed / (len(samples) / RATE)


def pcm_of(samples: np.ndarray) -> bytes:
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


def test_an_office_hums_lower_than_the_room_it_came_from() -> None:
    room = pink(RATE, SEED)
    assert crossings_per_second(pcm_of(hum(room))) < crossings_per_second(pcm_of(room)) / 4


def test_a_swell_keeps_the_level_it_was_given() -> None:
    flat = pink(RATE * SECONDS, SEED)
    swelling = swell(flat, RATE)
    assert abs(np.sqrt(np.mean(swelling * swelling)) / np.sqrt(np.mean(flat * flat)) - 1.0) < 0.01
