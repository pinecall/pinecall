"""The voices far from the caller's microphone taken down by a model: loaded once a process, a stream a call."""

import ctypes
import logging
from pathlib import Path

import numpy as np
from livekit import rtc

logger = logging.getLogger(__name__)

# A level alone tells a room from a caller only when the room is faint (nearest_voice.py): a
# television a caller would call "on, not loud", 18 dB under them, passed it whole (2026-11-15).
# What tells the two apart at that level is the room itself: a voice from across it arrives with
# its reflections on it, the caller's does not. A speech-enhancement model trained on that takes
# the far voice down before the level is read. The one the box runs is a DeepFilterNet3 fine-tuned
# on speakers 12 to 24 dB under the one near the microphone, 2.3 M parameters, causal, on a CPU.
# Measured on the test box through its own library, a call's frames at 24 kHz: a newscast across a
# living room 24 dB under the caller came out 21 dB lower and one 18 or 12 under 7 lower, the
# caller's own words transcribed the same; 0.7 ms of one core for each 10 ms of a line that carries
# a room, 0.2 for a clean one; the audio leaves 10 ms late. What it does not do: a clean voice with
# no room on it, however faint, is a second caller to it (1 dB), as it is to anything that listens.
# The box may have none (a laptop, a server set up without it): the call is then told apart by
# level alone, as it was.

# The library's own word for "take down whatever is far, as far as it goes", in dB.
NO_CEILING_DB = 100.0
# 16-bit audio as the floats the library takes, -1 to 1.
FULL_SCALE = 32768.0

_A_FLOAT = ctypes.POINTER(ctypes.c_float)


class FarVoicesModel:
    """The model as a process holds it: its library and its weights, loaded once, shared by every stream."""

    def __init__(self, library: ctypes.CDLL, weights: int) -> None:
        """A library whose functions are declared, and the weights it loaded."""
        self.library = library
        self.weights = weights

    def open_stream(self) -> "FarVoices":
        """A stream of its own for one call: nothing of another call's audio is in it."""
        return FarVoices(self)


class FarVoices:
    """One call's audio through the model: each frame in, the same length out, the far voices taken down."""

    def __init__(self, model: FarVoicesModel) -> None:
        """A stream not yet opened: it opens at the rate of the first frame it is handed."""
        self.model = model
        self.stream: int | None = None
        self.rate = 0
        # The samples the model takes at a time, at that rate.
        self.size = 0
        # What came and is not yet a whole piece for the model, and what it gave back and is not yet handed on.
        self.waiting = np.zeros(0, dtype=np.float32)
        self.cleared = np.zeros(0, dtype=np.float32)
        self.broken = False

    # A frame is rarely anything but a whole number of the model's pieces (50 ms of 10): then what
    # comes back is what went in, 10 ms late inside the model. One that is not is held until the
    # next completes it, and silence stands in at the stream's start for what is still inside.
    def clear(self, frame: rtc.AudioFrame) -> rtc.AudioFrame:
        """The frame with the far voices taken down; as it came when it is not mono or the model will not open."""
        if self.broken or frame.num_channels != 1 or not self._open_at(frame.sample_rate):
            return frame
        came = np.frombuffer(frame.data.tobytes(), dtype=np.int16).astype(np.float32) / FULL_SCALE
        self.waiting = np.concatenate([self.waiting, came])
        pieces = [self.cleared]
        whole = len(self.waiting) // self.size
        for at in range(whole):
            pieces.append(self._through(self.waiting[at * self.size : (at + 1) * self.size]))
        self.waiting = self.waiting[whole * self.size :]
        ready = np.concatenate(pieces)
        if len(ready) < len(came):
            ready = np.concatenate([np.zeros(len(came) - len(ready), dtype=np.float32), ready])
        handed, self.cleared = ready[: len(came)], ready[len(came) :]
        return rtc.AudioFrame(
            data=np.clip(np.rint(handed * FULL_SCALE), -FULL_SCALE, FULL_SCALE - 1).astype(np.int16).tobytes(),
            sample_rate=frame.sample_rate,
            num_channels=1,
            samples_per_channel=len(came),
        )

    def close(self) -> None:
        """Give the stream back to the library."""
        if self.stream is not None:
            self.model.library.weya_nc_session_free(self.stream)
            self.stream = None

    # The library resamples to the model's own rate itself: the stream is opened at the call's.
    def _open_at(self, rate: int) -> bool:
        if self.stream is not None and rate == self.rate:
            return True
        self.close()
        library = self.model.library
        stream: int | None = library.weya_nc_session_create(self.model.weights, rate, NO_CEILING_DB)
        if not stream:
            logger.warning("the far-voices model opened no stream at %d Hz: the call goes on without it", rate)
            self.broken = True
            return False
        self.stream, self.rate = stream, rate
        self.size = int(library.weya_nc_get_frame_length(stream))
        self.waiting = np.zeros(0, dtype=np.float32)
        self.cleared = np.zeros(0, dtype=np.float32)
        return True

    def _through(self, piece: np.ndarray) -> np.ndarray:
        given = np.ascontiguousarray(piece, dtype=np.float32)
        back = np.zeros(self.size, dtype=np.float32)
        process = self.model.library.weya_nc_process_frame
        process(self.stream, given.ctypes.data_as(_A_FLOAT), back.ctypes.data_as(_A_FLOAT))
        return back


# The functions are declared once: undeclared, ctypes hands a pointer over as a C int and cuts it.
def declare(library: ctypes.CDLL) -> None:
    """Say what each function of the library takes and gives."""
    library.weya_nc_model_load_from_path.argtypes = [ctypes.c_char_p]
    library.weya_nc_model_load_from_path.restype = ctypes.c_void_p
    library.weya_nc_session_create.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_float]
    library.weya_nc_session_create.restype = ctypes.c_void_p
    library.weya_nc_session_free.argtypes = [ctypes.c_void_p]
    library.weya_nc_session_free.restype = None
    library.weya_nc_get_frame_length.argtypes = [ctypes.c_void_p]
    library.weya_nc_get_frame_length.restype = ctypes.c_size_t
    library.weya_nc_process_frame.argtypes = [ctypes.c_void_p, _A_FLOAT, _A_FLOAT]
    library.weya_nc_process_frame.restype = ctypes.c_float


# A process that cannot load it says so once and takes its calls without it: a call is never lost
# to a model that only makes it better.
def load_far_voices(library: Path | None, weights: Path | None) -> FarVoicesModel | None:
    """The model the settings name, loaded; None when they name none, or when it does not load."""
    if library is None or weights is None:
        return None
    try:
        loaded = ctypes.CDLL(str(library))
        declare(loaded)
        held: int | None = loaded.weya_nc_model_load_from_path(str(weights).encode())
    except (OSError, AttributeError):
        logger.warning("the far-voices model at %s did not load: calls go on without it", library, exc_info=True)
        return None
    if not held:
        logger.warning("the far-voices model read no weights at %s: calls go on without it", weights)
        return None
    return FarVoicesModel(loaded, held)
