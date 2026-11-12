"""Noise as a function of the sample's index: white, pink, brown, a hum, a swell; the same on every machine."""

import numpy as np

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
    return level(total)


def brown(samples: int, phase: float) -> np.ndarray:
    """Brown noise: white noise summed, its drift taken out, the rumble of traffic."""
    walk: np.ndarray = np.cumsum(white(samples, phase), dtype=np.float64)
    drift: np.ndarray = np.linspace(float(walk[0]), float(walk[-1]), samples, dtype=np.float64)
    steady: np.ndarray = walk - drift
    return level(steady)


def hum(noise: np.ndarray) -> np.ndarray:
    """The noise with everything but its lowest notes smoothed away: a hum."""
    low = np.empty_like(noise)
    last = 0.0
    for index, sample in enumerate(noise):
        last = HUM_POLE * last + (1.0 - HUM_POLE) * sample
        low[index] = last
    return level(low)


def swell(noise: np.ndarray, rate: int) -> np.ndarray:
    """The noise rising and falling slowly: one car after another."""
    seconds = np.arange(noise.size) / rate
    envelope = QUIETEST_SWELL + (1.0 - QUIETEST_SWELL) * (0.5 + 0.5 * np.sin(2.0 * np.pi * SWELLS_PER_S * seconds))
    return level(noise * envelope)


def level(samples: np.ndarray) -> np.ndarray:
    """The samples at the one level every noise is made at."""
    loudness = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
    return samples if loudness == 0.0 else samples * (LEVEL / loudness)
