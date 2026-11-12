"""Tests for what plays behind the caller: each ambience a sound, the same every run."""

import numpy as np
import pytest

from runtime.evals.service.ambience import RATE, SECONDS, SEED, babble, sound_of
from runtime.judging.service.specs import AMBIENCES
from runtime.kit.noise import pink

A_SECOND = RATE


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


# The fault: a café was one voice over a room, and an agent transcribed it as the caller.
def test_a_cafes_chatter_is_many_tables_at_once_and_never_the_one_voice_alone() -> None:
    seconds = np.arange(RATE * 2) / RATE
    # A voice that speaks half the time: a word, a gap, a word.
    voice = np.sin(2 * np.pi * 220 * seconds) * (np.sin(2 * np.pi * 2 * seconds) > 0) * 8000
    alone = np.take(voice, np.arange(RATE * SECONDS), mode="wrap")
    tables = babble(voice, RATE * SECONDS)
    hundredths = RATE // 100

    def silent_share(samples: np.ndarray) -> float:
        windows = samples[: samples.size // hundredths * hundredths].reshape(-1, hundredths)
        levels = np.sqrt(np.mean(windows * windows, axis=1))
        return int(np.count_nonzero(levels < float(levels.max()) / 20)) / levels.size

    # One voice leaves its gaps silent; a room of tables fills them.
    assert silent_share(alone) > 0.4
    assert silent_share(tables) < 0.05
    both = np.corrcoef(alone, tables)[0, 1]
    assert abs(both) < 0.5


def test_a_street_swells_and_fades() -> None:
    levels = rms_by_second(sound_of("street", b""))
    assert max(levels) / min(levels) > 1.5


def test_an_ambience_nobody_made_is_refused_naming_them_all() -> None:
    with pytest.raises(ValueError, match="television, cafe, office, street"):
        sound_of("beach", b"")
