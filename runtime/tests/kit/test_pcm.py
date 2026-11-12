"""16-bit audio in frames: cut whole, padded at the end alone, and one sound mixed under another."""

import math
from array import array
from collections.abc import AsyncIterator, Sequence

from runtime.kit.pcm import QUIET, frames_of, in_frames, mix_under, rms_of

RATE = 48_000
FRAME_MS = 10
A_FRAME = QUIET * (RATE * FRAME_MS // 1000)
A_SECOND_IN_FRAMES = 100


def tone_of(samples: int, amplitude: int, period: int = 100) -> bytes:
    written = array("h")
    for index in range(samples):
        written.append(int(amplitude * math.sin(2 * math.pi * index / period)))
    return written.tobytes()


async def pieces_of(*pcm: bytes) -> AsyncIterator[bytes]:
    for piece in pcm:
        yield piece


async def collected(frames: AsyncIterator[bytes]) -> Sequence[bytes]:
    return [frame async for frame in frames]


def difference(mix: bytes, caller: bytes) -> bytes:
    mixed, voice = array("h"), array("h")
    mixed.frombytes(mix)
    voice.frombytes(caller)
    return array("h", (a - b for a, b in zip(mixed, voice, strict=True))).tobytes()


def test_a_frame_is_ten_milliseconds_of_the_rate_it_was_cut_at() -> None:
    frames = frames_of(tone_of(RATE, 8000), RATE, FRAME_MS)
    assert len(frames) == A_SECOND_IN_FRAMES
    assert all(len(frame) == RATE // A_SECOND_IN_FRAMES * 2 for frame in frames)


def test_the_last_frame_is_padded_with_silence_rather_than_sent_short() -> None:
    frames = frames_of(tone_of(RATE // 100 + 10, 8000), RATE, FRAME_MS)
    assert len(frames) == 2
    assert len(frames[1]) == len(frames[0])
    assert frames[1].endswith(QUIET * 10)


async def test_the_pieces_go_out_in_whole_frames_and_only_the_lines_end_is_padded() -> None:
    first, second = tone_of(1_234, 8000), tone_of(777, 8000)
    frames = await collected(in_frames(pieces_of(first, second), RATE, FRAME_MS))
    assert {len(frame) for frame in frames} == {len(A_FRAME)}
    heard = b"".join(frames)
    assert heard[: len(first + second)] == first + second
    assert heard[len(first + second) :] == QUIET * ((len(heard) - len(first + second)) // 2)


def test_the_sound_goes_under_the_frame_at_the_gain_it_is_given() -> None:
    voice = tone_of(480, 8000, period=97)
    television = tone_of(RATE, 8000, period=31)
    added = difference(mix_under(voice, television, 0, 0.25), voice)
    assert abs(rms_of(added) / rms_of(television[: len(voice)]) - 0.25) < 0.01


def test_the_sound_under_loops_and_goes_on_from_the_sample_it_is_asked_from() -> None:
    television = tone_of(500, 2000, period=50)
    whole = mix_under(A_FRAME + A_FRAME, television, 0, 1.0)
    assert mix_under(A_FRAME, television, 480, 1.0) == whole[len(A_FRAME) :]
    assert rms_of(whole[-200:]) > 0


def test_a_sum_past_sixteen_bits_is_clipped_never_wrapped() -> None:
    loud = array("h", [32000] * 480).tobytes()
    assert set(array("h", mix_under(loud, loud, 0, 1.0))) == {32767}
