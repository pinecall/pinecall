"""Audio encoded as Ogg Opus a frame at a time: what a fifo holds, in the whole frames Opus takes."""

from av.audio.fifo import AudioFifo
from av.audio.stream import AudioStream
from av.container import OutputContainer


# Opus takes whole frames only, of the size its encoder was opened for (20 ms: 960 samples at
# 48 kHz, 480 at 24): a tail shorter than one is dropped.
def drain_opus(fifo: AudioFifo, stream: AudioStream, sink: OutputContainer, *, frame: int, final: bool) -> None:
    """Encode what the fifo holds in whole frames; at the end, the tail that is one."""
    while fifo.samples >= frame or (final and fifo.samples > 0):
        read = fifo.read(min(frame, fifo.samples))
        if read is None or read.samples < frame:
            return
        for packet in stream.encode(read):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            sink.mux(packet)  # pyright: ignore[reportUnknownMemberType]
