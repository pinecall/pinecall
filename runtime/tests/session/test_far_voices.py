"""The far-voices model's stream: every frame through the library in its own pieces, the same length out, or none."""

import ctypes
from pathlib import Path
from typing import cast

import numpy as np
from livekit import rtc

from runtime.session.far_voices import FarVoices, FarVoicesModel, load_far_voices
from runtime.session.nearest_voice import NearestVoice

RATE = 24_000
# 10 ms: what the library takes at a time at the call's rate.
A_PIECE = RATE // 100
# 50 ms, as the room's input hands the session its frames.
A_ROOM_FRAME = RATE // 20


class Halving:
    """A library that hands back each piece at half its level, and counts the pieces and the streams it was asked."""

    def __init__(self, *, opens: bool = True) -> None:
        """One that opens a stream unless told it must not."""
        self.opens = opens
        self.pieces = 0
        self.streams: list[tuple[int, float]] = []
        self.freed: list[int] = []

    def weya_nc_session_create(self, _weights: int, rate: int, ceiling: float) -> int | None:
        self.streams.append((rate, ceiling))
        return len(self.streams) if self.opens else None

    def weya_nc_get_frame_length(self, _stream: int) -> int:
        return self.streams[-1][0] // 100

    def weya_nc_process_frame(
        self, _stream: int, given: "ctypes._Pointer[ctypes.c_float]", back: "ctypes._Pointer[ctypes.c_float]"
    ) -> float:
        size = self.streams[-1][0] // 100
        np.ctypeslib.as_array(back, shape=(size,))[:] = np.ctypeslib.as_array(given, shape=(size,)) * 0.5
        self.pieces += 1
        return 0.0

    def weya_nc_session_free(self, stream: int) -> None:
        self.freed.append(stream)


def a_stream(library: Halving) -> FarVoices:
    return FarVoicesModel(cast(ctypes.CDLL, library), weights=1).open_stream()


def frame_of(samples: np.ndarray, rate: int = RATE) -> rtc.AudioFrame:
    return rtc.AudioFrame(
        data=bytearray(samples.astype(np.int16).tobytes()),
        sample_rate=rate,
        num_channels=1,
        samples_per_channel=len(samples),
    )


def samples_of(frame: rtc.AudioFrame) -> np.ndarray:
    return np.frombuffer(frame.data.tobytes(), dtype=np.int16)


def test_a_room_frame_goes_through_in_the_models_pieces_and_comes_back_whole() -> None:
    """50 ms is five pieces of 10: each is handed over once, and the frame comes back as long as it went."""
    library = Halving()
    stream = a_stream(library)
    came = np.arange(A_ROOM_FRAME) * 10
    cleared = stream.clear(frame_of(came))
    assert library.pieces == 5
    assert library.streams == [(RATE, 100.0)]
    assert np.array_equal(samples_of(cleared), came // 2)


def test_a_frame_that_is_no_whole_number_of_pieces_keeps_its_length_and_the_streams_order() -> None:
    """What is left over waits for the next frame; silence stands in at the start, and nothing is lost or swapped."""
    library = Halving()
    stream = a_stream(library)
    came = (np.arange(A_PIECE * 6) + 1) * 4
    first, second = came[: A_PIECE + 100], came[A_PIECE + 100 :]
    back = np.concatenate([samples_of(stream.clear(frame_of(first))), samples_of(stream.clear(frame_of(second)))])
    assert len(back) == len(came)
    # 100 samples of silence, then the stream at half its level, as far as its whole pieces go.
    assert not back[:100].any()
    assert np.array_equal(back[100:], (came // 2)[: len(came) - 100])


def test_a_library_that_opens_no_stream_leaves_the_call_as_it_came() -> None:
    """The call is not lost to the model: its frames pass untouched, and it is asked once."""
    library = Halving(opens=False)
    stream = a_stream(library)
    came = frame_of(np.full(A_ROOM_FRAME, 1000))
    assert stream.clear(came) is came
    assert stream.clear(came) is came
    assert len(library.streams) == 1 and library.pieces == 0


def test_a_stream_is_opened_again_at_another_rate_and_given_back_when_closed() -> None:
    """A phone's frames after a browser's are another stream, and the first is freed."""
    library = Halving()
    stream = a_stream(library)
    stream.clear(frame_of(np.zeros(A_ROOM_FRAME)))
    stream.clear(frame_of(np.zeros(800), rate=16_000))
    assert [rate for rate, _ in library.streams] == [RATE, 16_000]
    stream.close()
    assert library.freed == [1, 2]


def test_the_caller_is_heard_through_the_model_before_the_level_is_read() -> None:
    """The gate reads what the model gave back, and closes the model's stream with its own."""
    library = Halving()
    gate = NearestVoice(caller_has_the_floor=lambda: True, far_voices=a_stream(library))
    heard = gate.hear(frame_of(np.full(A_ROOM_FRAME, 2000)))
    assert np.array_equal(samples_of(heard), np.full(A_ROOM_FRAME, 1000))
    gate._close()
    assert library.freed == [1]


def test_a_box_with_no_model_or_one_that_does_not_load_has_none(tmp_path: Path) -> None:
    """Nothing named is nothing loaded, and a file that is no library is said and left."""
    assert load_far_voices(None, None) is None
    assert load_far_voices(tmp_path / "library.so", None) is None
    no_library = tmp_path / "library.so"
    no_library.write_bytes(b"not a library")
    assert load_far_voices(no_library, tmp_path / "weights.tar.gz") is None
