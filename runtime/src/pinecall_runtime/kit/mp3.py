"""PCM encoded as one MP3 file: what every browser plays, Safari's too, at a bit rate small enough to fetch at once."""

import io

import av
import numpy as np
from av.audio.frame import AudioFrame
from av.audio.stream import AudioStream

# LAME takes planar samples in frames of 1152; the last one may be shorter.
FRAME = 1152


def mp3_of(pcm: bytes, *, rate: int, channels: int, bit_rate: int) -> bytes:
    """16-bit interleaved samples as an MP3 file at `bit_rate` bits a second."""
    layout = "mono" if channels == 1 else "stereo"
    samples = np.frombuffer(pcm, dtype=np.int16).reshape(1, -1)
    whole = AudioFrame.from_ndarray(samples, format="s16", layout=layout)
    whole.sample_rate = rate
    planar = av.AudioResampler(format="s16p", layout=layout, rate=rate)
    fifo = av.AudioFifo()
    for frame in [*planar.resample(whole), *planar.resample(None)]:
        frame.pts = None
        fifo.write(frame)
    out = io.BytesIO()
    with av.open(out, mode="w", format="mp3") as sink:
        stream: AudioStream = sink.add_stream("libmp3lame", rate=rate)  # pyright: ignore[reportUnknownMemberType]
        stream.layout = layout
        stream.bit_rate = bit_rate
        while fifo.samples > 0:
            read = fifo.read(min(FRAME, fifo.samples))
            if read is None:
                break
            for packet in stream.encode(read):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                sink.mux(packet)  # pyright: ignore[reportUnknownMemberType]
        for packet in stream.encode(None):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            sink.mux(packet)  # pyright: ignore[reportUnknownMemberType]
    return out.getvalue()
