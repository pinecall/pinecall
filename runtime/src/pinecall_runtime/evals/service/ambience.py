"""What plays behind the caller: a television, a café, an office, a street; the same every run."""

import numpy as np

# The room's rate, as spoken.py publishes it.
RATE = 48_000
# The sound loops under the caller, so a few seconds cover any line.
SECONDS = 8
# One phase: a persona rings from the same café every time, and a test hears what a call hears.
SEED = 7
# The hash white noise is drawn from, sample by sample: no generator, so the same on every machine.
HASH_FREQUENCY = 12.9898
HASH_SPREAD = 43758.5453
HASH_SECOND_FREQUENCY = 78.233
# Keeps the log of a uniform draw finite.
A_HAIR = 1e-12
# Far enough under full scale that mixing never clips it.
LEVEL = 6000.0
# The rows of a pink-noise generator: each held twice as long as the one before.
OCTAVES = 8
# One pole on pink noise: the hum of an office's air, nothing above a few hundred hertz.
HUM_POLE = 0.985
# A street's traffic swells and fades a few times a minute.
SWELLS_PER_S = 0.15
QUIETEST_SWELL = 0.35
# A café is chatter over pink noise, the chatter a little louder than the room.
CHATTER_OVER_ROOM = 1.4

AMBIENCES = ("television", "cafe", "office", "street")
# The ambiences that are a voice: they need the chatter synthesized before they are made.
VOICED = frozenset({"television", "cafe"})
NOT_AN_AMBIENCE = "{ambience} is no ambience: one of {allowed}"


def sound_of(ambience: str, chatter: bytes) -> bytes:
    """The ambience as 16-bit mono at the room's rate; `chatter` is a voice, for the voiced ones."""
    if ambience == "television":
        return chatter
    samples = RATE * SECONDS
    if ambience == "cafe":
        room = pink(samples, SEED)
        voice = np.frombuffer(chatter, dtype=np.int16).astype(np.float64)
        if voice.size:
            looped = np.take(voice, np.arange(samples), mode="wrap")
            room = room + leveled(looped) * CHATTER_OVER_ROOM
        return as_pcm(room)
    if ambience == "office":
        return as_pcm(hummed(pink(samples, SEED)))
    if ambience == "street":
        return as_pcm(swelled(brown(samples, SEED)))
    raise ValueError(NOT_AN_AMBIENCE.format(ambience=ambience, allowed=", ".join(AMBIENCES)))


# A hash of the sample's index, so the noise is a function and not a generator's state: the same
# on every machine, and a row drawn at another phase is another row.
def white(samples: int, phase: float) -> np.ndarray:
    """White noise, gaussian, one value a sample, the same for the same phase every run."""
    index = np.arange(samples, dtype=np.float64) + phase
    first = np.mod(np.sin(index * HASH_FREQUENCY) * HASH_SPREAD, 1.0)
    second = np.mod(np.sin(index * HASH_SECOND_FREQUENCY) * HASH_SPREAD, 1.0)
    return np.sqrt(-2.0 * np.log(first + A_HAIR)) * np.cos(2.0 * np.pi * second)


def pink(samples: int, phase: float) -> np.ndarray:
    """Pink noise: a sum of white rows, each held for twice as many samples as the last."""
    total = np.zeros(samples, dtype=np.float64)
    for octave in range(OCTAVES):
        hold = 2**octave
        rows = -(-samples // hold)
        total += np.repeat(white(rows, phase + octave * samples), hold)[:samples]
    return leveled(total)


def brown(samples: int, phase: float) -> np.ndarray:
    """Brown noise: white noise summed, its drift taken out, the rumble of traffic."""
    walked: np.ndarray = np.cumsum(white(samples, phase), dtype=np.float64)
    drift: np.ndarray = np.linspace(float(walked[0]), float(walked[-1]), samples, dtype=np.float64)
    settled: np.ndarray = walked - drift
    return leveled(settled)


def hummed(noise: np.ndarray) -> np.ndarray:
    """The noise with everything but its lowest notes smoothed away: a hum."""
    low = np.empty_like(noise)
    kept = 0.0
    for index, sample in enumerate(noise):
        kept = HUM_POLE * kept + (1.0 - HUM_POLE) * sample
        low[index] = kept
    return leveled(low)


def swelled(noise: np.ndarray) -> np.ndarray:
    """The noise rising and falling slowly: one car after another."""
    seconds = np.arange(noise.size) / RATE
    envelope = QUIETEST_SWELL + (1.0 - QUIETEST_SWELL) * (0.5 + 0.5 * np.sin(2.0 * np.pi * SWELLS_PER_S * seconds))
    return leveled(noise * envelope)


def leveled(samples: np.ndarray) -> np.ndarray:
    """The samples at the one level every ambience is made at."""
    loudness = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
    return samples if loudness == 0.0 else samples * (LEVEL / loudness)


def as_pcm(samples: np.ndarray) -> bytes:
    """Floats as 16-bit mono, clipped rather than wrapped."""
    return np.clip(np.rint(samples), -32768, 32767).astype(np.int16).tobytes()
