"""The caller's voice at another tempo: its audio stretched frame by frame, the pitch kept."""

import numpy as np

# The room's rate, as spoken.py publishes it; this module knows no room.
RATE = 48_000
# One frame of voice, long enough to hold a pitch period and short enough to follow the words.
FRAME_S = 0.024
# How far either side of its natural place a frame may be taken from, to join the one before.
TOLERANCE_S = 0.008
LOUDEST = 32767
QUIETEST = -32768


# Overlap-add with each frame taken where it joins the output best (WSOLA): the voice gets
# shorter or longer, its pitch stays. Deterministic: the same audio in pieces or whole comes out
# the same, so a line spoken as the vendor sends it sounds as it would spoken whole.
class Stretcher:
    """Audio pushed in at one tempo and read out at another, a piece at a time."""

    def __init__(self, speed: float, rate: int = RATE) -> None:
        """A stretcher for a voice `speed` times as fast: 2 is twice as fast, 0.5 half."""
        self.frame = int(rate * FRAME_S)
        self.hop = self.frame // 2
        self.step = self.hop * speed
        self.tolerance = int(rate * TOLERANCE_S)
        self.window = np.hanning(self.frame)
        # Audio pushed and not yet used whole, as floats; the next frame's natural place in it.
        self.pending = np.zeros(0, dtype=np.float64)
        self.place = 0.0
        # Where the frame before was taken from, so the next is sought where it joins that one.
        self.taken: int | None = None
        # The output being overlap-added, and how much of it was read out already.
        self.output = np.zeros(self.frame, dtype=np.float64)
        self.written = 0
        self.read = 0

    def push(self, pcm: bytes) -> bytes:
        """Take 16-bit mono audio in; give back what is stretched and complete so far."""
        if pcm:
            arrived = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
            self.pending = np.concatenate([self.pending, arrived])
        while int(self.place) + self.tolerance + self.frame <= self.pending.size:
            self._add_a_frame()
        self._forget_the_used()
        return self._completed()

    def flush(self) -> bytes:
        """The rest, once no more audio is coming: the last frames padded with silence."""
        if self.pending.size == 0 and self.written == 0:
            return b""
        padding = np.zeros(self.frame + self.tolerance, dtype=np.float64)
        self.pending = np.concatenate([self.pending, padding])
        while int(self.place) + self.frame <= self.pending.size:
            self._add_a_frame()
        rest = self.output[self.read : self.written + self.hop]
        self.read = self.written + self.hop
        return _as_pcm(rest)

    def _add_a_frame(self) -> None:
        start = self._best_start()
        frame = self.pending[start : start + self.frame] * self.window
        if self.written + self.frame > self.output.size:
            grown = np.zeros(self.output.size * 2 + self.frame, dtype=np.float64)
            grown[: self.output.size] = self.output
            self.output = grown
        self.output[self.written : self.written + self.frame] += frame
        self.written += self.hop
        self.taken = start
        self.place += self.step

    # The frame is taken where it best continues the one before: among the places within the
    # tolerance of its natural one, the one most like what would have followed the last frame.
    def _best_start(self) -> int:
        nominal = int(self.place)
        if self.taken is None:
            return nominal
        natural = self.pending[self.taken + self.hop : self.taken + self.hop + self.hop]
        lowest = max(0, nominal - self.tolerance)
        highest = min(nominal + self.tolerance, self.pending.size - self.frame)
        if highest <= lowest or natural.size < self.hop:
            return max(lowest, min(nominal, highest))
        candidates = np.lib.stride_tricks.sliding_window_view(self.pending[lowest : highest + self.hop], self.hop)
        return lowest + int(np.argmax(candidates @ natural))

    def _forget_the_used(self) -> None:
        keep_from = int(self.place) - self.tolerance
        if self.taken is not None:
            keep_from = min(keep_from, self.taken)
        if keep_from > 0:
            self.pending = self.pending[keep_from:]
            self.place -= keep_from
            if self.taken is not None:
                self.taken -= keep_from

    def _completed(self) -> bytes:
        done = self.output[self.read : self.written]
        self.read = self.written
        return _as_pcm(done)


def _as_pcm(samples: np.ndarray) -> bytes:
    return np.clip(np.rint(samples), QUIETEST, LOUDEST).astype(np.int16).tobytes()
