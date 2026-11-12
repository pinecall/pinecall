"""16-bit PCM and floats at a rate: samples written as PCM, and sounds laid on a recorded stereo file at their time."""

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np
from av.audio.stream import AudioStream

from runtime.kit.opus import drain_opus

# 16-bit samples: two bytes each, the width every plugin and every room takes.
SAMPLE_WIDTH = 2
LOUDEST = 32767
QUIETEST = -32768
# A sum of voices can pass full scale; it is clipped, not wrapped.
FULL_SCALE = 1.0
# Opus takes whole frames of 20 ms: 480 samples at 24 kHz, 960 at 48.
OPUS_FRAMES_A_SECOND = 50


@dataclass(frozen=True, slots=True)
class Sound:
    """One sound laid on the right: the sample it starts at, how many, and any stretch of it."""

    start: int
    length: int
    stretch: Callable[[int, int], np.ndarray]


def as_pcm(samples: np.ndarray) -> bytes:
    """Floats as 16-bit mono, clipped rather than wrapped."""
    return np.clip(np.rint(samples), QUIETEST, LOUDEST).astype(np.int16).tobytes()


# Blocking, for a thread: the file decoded a frame at a time, the sounds added on the right where
# each falls, encoded as it goes, put in its place. Nothing of the file's length is held at once.
def lay_sounds(audio: Path, sounds: Sequence[Sound], *, rate: int) -> None:
    """Add the sounds to the right channel of a stereo Ogg Opus file, each at its sample; the file is replaced whole."""
    part = audio.with_name(f"{audio.name}.part")
    encode(_mix(decode(audio, "stereo", rate=rate), sounds, rate), part, rate=rate)
    part.replace(audio)


def encode(stretches: Iterable[np.ndarray], out: Path, *, rate: int) -> None:
    """Write stretches of two channels of floats at `rate` as one stereo Ogg Opus."""
    frame = rate // OPUS_FRAMES_A_SECOND
    fifo = av.AudioFifo()
    with av.open(str(out), mode="w", format="ogg") as sink:
        stream: AudioStream = sink.add_stream("libopus", rate=rate)  # pyright: ignore[reportUnknownMemberType]
        stream.layout = "stereo"
        for stretch in stretches:
            piece = av.AudioFrame.from_ndarray(np.ascontiguousarray(stretch), format="fltp", layout="stereo")
            piece.sample_rate = rate
            piece.pts = None
            fifo.write(piece)
            drain_opus(fifo, stream, sink, frame=frame, final=False)
        drain_opus(fifo, stream, sink, frame=frame, final=True)
        for packet in stream.encode(None):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            sink.mux(packet)  # pyright: ignore[reportUnknownMemberType]


def decode(audio: Path, layout: str, *, rate: int) -> Iterator[np.ndarray]:
    """An audio file as stretches of floats at `rate`, one row a channel of the layout asked."""
    resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
    with av.open(str(audio)) as source:
        for frame in source.decode(audio=0):
            for piece in resampler.resample(frame):
                yield piece.to_ndarray()
        for piece in resampler.resample(None):
            yield piece.to_ndarray()


# A sound that outlasts the file is laid on silence past its end, a second at a time.
def _mix(stretches: Iterator[np.ndarray], sounds: Sequence[Sound], rate: int) -> Iterator[np.ndarray]:
    cursor = 0
    end = max((sound.start + sound.length for sound in sounds), default=0)
    for stretch in stretches:
        yield _lay(stretch, cursor, sounds)
        cursor += stretch.shape[1]
    while cursor < end:
        count = min(rate, end - cursor)
        yield _lay(np.zeros((2, count), dtype=np.float32), cursor, sounds)
        cursor += count


def _lay(stretch: np.ndarray, cursor: int, sounds: Sequence[Sound]) -> np.ndarray:
    until = cursor + stretch.shape[1]
    for sound in sounds:
        low, high = max(sound.start, cursor), min(sound.start + sound.length, until)
        if low < high:
            stretch[1, low - cursor : high - cursor] += sound.stretch(low - sound.start, high - low)
    np.clip(stretch, -FULL_SCALE, FULL_SCALE, out=stretch)
    return stretch
