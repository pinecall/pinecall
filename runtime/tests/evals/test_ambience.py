"""Tests for what plays behind the caller: each ambience a sound, the same every run."""

from array import array
from itertools import pairwise

import numpy as np
import pytest

from pinecall_runtime.evals.service.ambience import AMBIENCES, RATE, SECONDS, SEED, hummed, pink, sound_of, swelled

A_SECOND = RATE


def crossings_per_second(pcm: bytes) -> float:
    samples = array("h")
    samples.frombytes(pcm)
    crossed = sum(1 for a, b in pairwise(samples) if (a < 0) != (b < 0))
    return crossed / (len(samples) / RATE)


def rms_by_second(pcm: bytes) -> list[float]:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    return [
        float(np.sqrt(np.mean(window * window)))
        for window in np.split(samples[: (samples.size // A_SECOND) * A_SECOND], samples.size // A_SECOND)
    ]


def test_every_ambience_but_the_television_is_a_few_seconds_that_loop() -> None:
    for ambience in AMBIENCES:
        if ambience == "television":
            continue
        assert len(sound_of(ambience, b"")) == RATE * SECONDS * 2


def test_the_television_is_the_chatter_as_read() -> None:
    chatter = bytes(range(0, 200, 2))
    assert sound_of("television", chatter) == chatter


def test_the_same_cafe_is_heard_every_run() -> None:
    assert sound_of("cafe", b"") == sound_of("cafe", b"")
    assert sound_of("street", b"") == sound_of("street", b"")


def test_a_cafe_carries_the_chatter_over_its_room() -> None:
    room = sound_of("cafe", b"")
    chatter = np.clip(pink(RATE, SEED) * 2, -32768, 32767).astype(np.int16).tobytes()
    assert sound_of("cafe", chatter) != room


def pcm_of(samples: np.ndarray) -> bytes:
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


def test_an_office_hums_lower_than_the_room_it_came_from() -> None:
    room = pink(RATE, SEED)
    assert crossings_per_second(pcm_of(hummed(room))) < crossings_per_second(pcm_of(room)) / 4


def test_a_street_swells_and_fades() -> None:
    levels = rms_by_second(sound_of("street", b""))
    assert max(levels) / min(levels) > 1.5


def test_a_swell_keeps_the_level_it_was_given() -> None:
    flat = pink(RATE * SECONDS, SEED)
    swelling = swelled(flat)
    assert abs(np.sqrt(np.mean(swelling * swelling)) / np.sqrt(np.mean(flat * flat)) - 1.0) < 0.01


def test_an_ambience_nobody_made_is_refused_naming_them_all() -> None:
    with pytest.raises(ValueError, match="television, cafe, office, street"):
        sound_of("beach", b"")
