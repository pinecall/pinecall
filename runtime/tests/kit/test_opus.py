"""An upload read off its own bytes and kept as Ogg Opus: a script or a playlist is no audio."""

import io
import math
import struct
import wave

import pytest

from runtime.exceptions import ValidationError
from runtime.kit.opus import container_of, encode_upload


def a_wav(seconds: float, *, rate: int = 16_000) -> bytes:
    """A sine of that length, mono, as a person would upload it."""
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(
            b"".join(struct.pack("<h", int(8000 * math.sin(at / 10))) for at in range(int(rate * seconds)))
        )
    return out.getvalue()


def test_an_upload_comes_out_as_ogg_opus_at_the_rate_livekit_mixes() -> None:
    clip = encode_upload(a_wav(2.0), longest_s=60)
    assert clip.audio[:4] == b"OggS"
    assert clip.seconds == 2.0


def test_what_is_no_audio_is_refused_in_the_persons_words() -> None:
    with pytest.raises(ValidationError, match="no audio this box can read"):
        encode_upload(b"not a melody", longest_s=60)


# The container is named by the file's own bytes and FFmpeg is told it: nothing is probed, so a
# playlist or a concat script, which FFmpeg would otherwise follow, is no audio here.
def test_the_container_is_read_off_the_bytes_and_a_script_is_no_audio() -> None:
    assert container_of(a_wav(1.0)) == "wav"
    assert container_of(b"OggS" + bytes(40)) == "ogg"
    assert container_of(b"ID3" + bytes(40)) == "mp3"
    for frame in (b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3", b"\xff\xe2"):
        assert container_of(frame + bytes(40)) == "mp3"
    assert container_of(bytes(4) + b"ftypM4A " + bytes(32)) == "mov,mp4,m4a,3gp,3g2,mj2"
    playlist = b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:1,\nhttp://169.254.169.254/x\n"
    script = b"ffconcat version 1.0\nfile recordings/call_1/audio.ogg\n"
    for scripted in (playlist, script):
        assert container_of(scripted) is None
        with pytest.raises(ValidationError, match="no audio this box can read"):
            encode_upload(scripted, longest_s=60)
