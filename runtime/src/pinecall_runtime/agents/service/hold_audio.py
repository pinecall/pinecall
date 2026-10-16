"""An uploaded hold melody converted once, here, so no worker decodes a tenant's file mid-call."""

import io
from dataclasses import dataclass

import av
from av.audio.stream import AudioStream
from av.container import InputContainer
from av.error import FFmpegError

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.opus import drain_opus

# livekit mixes at 48 kHz; mono like a phone leg; Opus for size, in whole frames only.
RATE = 48_000
OPUS_FRAME = 960
BIT_RATE = 64_000
# The melody loops, so a long file only costs storage, and a very short one stutters.
LONGEST_S = 300
SHORTEST_S = 1

NOT_AUDIO = "that file is no audio this box can read: send a wav, an mp3, an ogg or an m4a"
TOO_LONG = f"a hold melody loops, so {LONGEST_S // 60} minutes at most: this one runs longer"
TOO_SHORT = f"a hold melody of less than {SHORTEST_S} second would stutter as it loops"

# The containers a melody comes in, each by the bytes it starts with: FFmpeg is told which and
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


@dataclass(frozen=True, slots=True)
class Converted:
    """An upload as the worker plays it: Ogg Opus, 48 kHz mono, and how long it lasts."""

    audio: bytes
    seconds: float


def convert_upload(data: bytes) -> Converted:
    """Audio in a container this box names, as the melody the worker plays; refused in words."""
    container = container_of(data)
    if container is None:
        raise ValidationError(NOT_AUDIO)
    try:
        source = av.open(io.BytesIO(data), mode="r", format=container)
    except (FFmpegError, OSError, ValueError) as unreadable:
        raise ValidationError(NOT_AUDIO) from unreadable
    with source:
        if not source.streams.audio:
            raise ValidationError(NOT_AUDIO)
        try:
            audio, samples = _encoded(source)
        except (FFmpegError, OSError, ValueError) as unreadable:
            raise ValidationError(NOT_AUDIO) from unreadable
    seconds = samples / RATE
    if seconds < SHORTEST_S:
        raise ValidationError(TOO_SHORT)
    return Converted(audio=audio, seconds=round(seconds, 2))


def container_of(data: bytes) -> str | None:
    """The demuxer the file's first bytes name; None for a container this box does not read."""
    for offset, magic, named in CONTAINERS:
        if data[offset : offset + len(magic)] == magic:
            return named
    return None


def _encoded(source: InputContainer) -> tuple[bytes, int]:
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
                if samples > LONGEST_S * RATE:
                    raise ValidationError(TOO_LONG)
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
