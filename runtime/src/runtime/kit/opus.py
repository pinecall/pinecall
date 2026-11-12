"""Audio as Ogg Opus: an upload read by the container its first bytes name, and encoded a whole frame at a time."""

import io
from dataclasses import dataclass

import av
from av.audio.fifo import AudioFifo
from av.audio.stream import AudioStream
from av.container import InputContainer, OutputContainer
from av.error import FFmpegError

from runtime.exceptions import ValidationError

# livekit mixes at 48 kHz; mono like a phone leg; Opus for size, in whole frames only.
RATE = 48_000
OPUS_FRAME = 960
BIT_RATE = 64_000


# The containers an upload comes in, each by the bytes it starts with: FFmpeg is told which and
# probes nothing, so no playlist, script or path a file could carry is followed (an `m3u8` fetches
# URLs, an `ffconcat` opens files). The pair is (offset, magic) → the demuxer's name.
CONTAINERS: tuple[tuple[int, bytes, str], ...] = (
    (0, b"RIFF", "wav"),
    (0, b"OggS", "ogg"),
    (0, b"fLaC", "flac"),
    (4, b"ftyp", "mov,mp4,m4a,3gp,3g2,mj2"),
    (0, b"ID3", "mp3"),
    # An MPEG audio frame's sync with layer III: MPEG-1, MPEG-2 and MPEG-2.5, with and without CRC.
    (0, b"\xff\xfb", "mp3"),
    (0, b"\xff\xfa", "mp3"),
    (0, b"\xff\xf3", "mp3"),
    (0, b"\xff\xf2", "mp3"),
    (0, b"\xff\xe3", "mp3"),
    (0, b"\xff\xe2", "mp3"),
)


class RunsLonger(ValidationError):
    """The audio runs past the ceiling its reader gave; the reader says so in its own sentence."""

    def __init__(self, longest_s: int) -> None:
        super().__init__(f"the audio runs longer than {longest_s} seconds")
        self.longest_s = longest_s


@dataclass(frozen=True, slots=True)
class Encoded:
    """An upload as Ogg Opus, 48 kHz mono, and how long it lasts."""

    audio: bytes
    seconds: float


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


def container_of(data: bytes) -> str | None:
    """The demuxer the file's first bytes name; None for a container this box does not read."""
    for offset, magic, named in CONTAINERS:
        if data[offset : offset + len(magic)] == magic:
            return named
    return None


# Decoded here, once, so nothing downstream decodes a tenant's upload: what is kept is ours.
def encode_upload(data: bytes, *, longest_s: int) -> Encoded:
    """Audio in a container this box names, as Ogg Opus; refused in words, RunsLonger past the ceiling."""
    container = container_of(data)
    if container is None:
        raise ValidationError("that file is no audio this box can read: send a wav, an mp3, an ogg, a flac or an m4a")
    try:
        source = av.open(io.BytesIO(data), mode="r", format=container)
    except (FFmpegError, OSError, ValueError) as unreadable:
        raise ValidationError(
            "that file is no audio this box can read: send a wav, an mp3, an ogg, a flac or an m4a"
        ) from unreadable
    with source:
        if not source.streams.audio:
            raise ValidationError(
                "that file is no audio this box can read: send a wav, an mp3, an ogg, a flac or an m4a"
            )
        try:
            audio, samples = _encode(source, longest_s=longest_s)
        except (FFmpegError, OSError, ValueError) as unreadable:
            raise ValidationError(
                "that file is no audio this box can read: send a wav, an mp3, an ogg, a flac or an m4a"
            ) from unreadable
    return Encoded(audio=audio, seconds=samples / RATE)


# Refused at the first frame past the ceiling: a file of hours is never encoded whole to be turned down.
def _encode(source: InputContainer, *, longest_s: int) -> tuple[bytes, int]:
    out = io.BytesIO()
    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    fifo = av.AudioFifo()
    samples = 0
    with av.open(out, mode="w", format="ogg") as sink:
        stream: AudioStream = sink.add_stream("libopus", rate=RATE)  # pyright: ignore[reportUnknownMemberType]
        stream.layout = "mono"
        stream.bit_rate = BIT_RATE
        for decoded in source.decode(audio=0):
            for frame in resampler.resample(decoded):
                samples += frame.samples
                if samples > longest_s * RATE:
                    raise RunsLonger(longest_s)
                frame.pts = None
                fifo.write(frame)
            drain_opus(fifo, stream, sink, frame=OPUS_FRAME, final=False)
        for frame in resampler.resample(None):
            samples += frame.samples
            frame.pts = None
            fifo.write(frame)
        drain_opus(fifo, stream, sink, frame=OPUS_FRAME, final=True)
        for packet in stream.encode(None):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            sink.mux(packet)  # pyright: ignore[reportUnknownMemberType]
    return out.getvalue(), samples
