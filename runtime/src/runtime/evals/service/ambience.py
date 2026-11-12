"""What plays behind the caller: a television, a café, an office, a street; the same every run."""

from collections.abc import Callable, Mapping
from functools import lru_cache

import numpy as np

from runtime.kit import noise
from runtime.kit.pcm import as_pcm

# The room's rate, as the caller's leg publishes it.
RATE = 48_000
# The sound loops under the caller, so a few seconds cover any line.
SECONDS = 8
SAMPLES = RATE * SECONDS
# One phase: a persona rings from the same café every time, and a test hears what a call hears.
SEED = 7
# A café is chatter over pink noise, the chatter a little louder than the room.
CHATTER_OVER_ROOM = 1.4
# The tables of a café: this many people talking at once, so that none of them can be followed.
TABLES = 8
# Each table speaks at a pace and pitch of its own, from this much of the voice's to that much.
SLOWEST_TABLE = 0.8
FASTEST_TABLE = 1.3
# Each table starts this much of the chatter after the one before: never two saying the same word.
A_TABLE_STARTS_AFTER = 0.618
# A table further away is this much quieter, three distances in all.
DISTANCES = 3
FURTHER_BY = 0.5


def _television(chatter: bytes) -> bytes:
    return chatter


def _cafe(chatter: bytes) -> bytes:
    room = noise.pink(SAMPLES, SEED)
    voice = np.frombuffer(chatter, dtype=np.int16).astype(np.float64)
    if voice.size:
        room = room + babble(voice, SAMPLES) * CHATTER_OVER_ROOM
    return as_pcm(room)


def _office(_chatter: bytes) -> bytes:
    return _hum_of_an_office()


def _street(_chatter: bytes) -> bytes:
    return _rumble_of_a_street()


# An office's hum is a filter walked sample by sample, 384,000 of them, and it is the same every
# time: made once a process. Until 2026-11 it was made again for every call, on the gateway's event
# loop, and while it ran no other simulated caller's track was fed a frame and no request was answered.
@lru_cache(maxsize=1)
def _hum_of_an_office() -> bytes:
    return as_pcm(noise.hum(noise.pink(SAMPLES, SEED)))


@lru_cache(maxsize=1)
def _rumble_of_a_street() -> bytes:
    return as_pcm(noise.swell(noise.brown(SAMPLES, SEED), RATE))


# Until 2026-11 a chain of `if` beside two hand-kept lists of the names.
SOUNDS: Mapping[str, Callable[[bytes], bytes]] = {
    "television": _television,
    "cafe": _cafe,
    "office": _office,
    "street": _street,
}
# The ambiences that are a voice: they need the chatter synthesized before they are made.
VOICED = frozenset({"television", "cafe"})


# Blocking, for a thread (`asyncio.to_thread`): a café is eight voices resampled, an office a hum.
def sound_of(ambience: str, chatter: bytes) -> bytes:
    """The ambience as 16-bit mono at the room's rate; `chatter` is a voice, for the voiced ones."""
    made = SOUNDS.get(ambience)
    if made is None:
        raise ValueError(f"{ambience} is no ambience: one of {', '.join(SOUNDS)}")
    return made(chatter)


# One voice read at one table is a second caller, not a café: on 2026-11-09 the first call placed
# with the room heard the whole call had its agent transcribe the café's one voice, word for word,
# as the caller, and answer twice in three minutes. The same voice at eight paces and pitches, each
# from another place in what it reads, is the murmur of a room.
def babble(voice: np.ndarray, samples: int) -> np.ndarray:
    """The voice as a café's tables: several of it at once, each at its own pace, start and distance."""
    read = np.arange(voice.size, dtype=np.float64)
    at = np.arange(samples, dtype=np.float64)
    total = np.zeros(samples, dtype=np.float64)
    for table in range(TABLES):
        pace = SLOWEST_TABLE + (FASTEST_TABLE - SLOWEST_TABLE) * table / (TABLES - 1)
        starts = table * A_TABLE_STARTS_AFTER * voice.size
        heard = np.interp(at * pace + starts, read, voice, period=voice.size)
        total += heard / (1.0 + FURTHER_BY * (table % DISTANCES))
    return noise.level(total)
