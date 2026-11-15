"""The nearest voice: the caller heard whole, the room far under them muted, a caller gone quiet learnt again."""

import numpy as np
from livekit import rtc

from runtime.session.nearest_voice import FORGOTTEN_AFTER_S, HELD_S, NearestVoice, levels_of

RATE = 24_000
# 50 ms, as the room's input hands the session its frames.
A_ROOM_FRAME = RATE // 20
# A caller at a voice's level, and a television across the room: 30 dB under them.
A_VOICE = 3000.0
A_TELEVISION = A_VOICE * 10 ** (-30 / 20)


def frame_of(samples: np.ndarray) -> rtc.AudioFrame:
    return rtc.AudioFrame(
        data=bytearray(samples.astype(np.int16).tobytes()),
        sample_rate=RATE,
        num_channels=1,
        samples_per_channel=len(samples),
    )


def speech_like(seed: int, seconds: float, level: float) -> np.ndarray:
    """Noise in syllables: bursts of 100 to 300 ms and short gaps, as a voice's energy comes and goes."""
    rng = np.random.default_rng(seed)
    voice = np.zeros(int(RATE * seconds))
    at = 0
    while at < len(voice):
        burst = int(RATE * rng.uniform(0.1, 0.3))
        voice[at : at + burst] = rng.standard_normal(min(burst, len(voice) - at)) * level
        at += burst + int(RATE * rng.uniform(0.03, 0.12))
    return voice


class Line:
    """A caller's line played through one gate at the room's pace."""

    def __init__(self) -> None:
        """A line on which the agent is not speaking."""
        self.agent_speaks = False
        self.gate = NearestVoice(caller_has_the_floor=lambda: not self.agent_speaks)

    def through(self, came: np.ndarray) -> np.ndarray:
        """What the session hears of it, frame by frame."""
        frames = [frame_of(came[at : at + A_ROOM_FRAME]) for at in range(0, len(came), A_ROOM_FRAME)]
        return np.concatenate([np.frombuffer(self.gate.hear(frame).data.tobytes(), dtype=np.int16) for frame in frames])


def a_call(seconds_of_voice: float, seconds_after: float) -> tuple[np.ndarray, int]:
    """A television the whole call and the caller speaking over it at first; where the caller stops."""
    stops = int(RATE * seconds_of_voice)
    came = speech_like(5, seconds_of_voice + seconds_after, A_TELEVISION)
    came[:stops] += speech_like(7, seconds_of_voice, A_VOICE)
    return came.astype(np.int16).astype(np.float64), stops


def test_a_line_nobody_spoke_on_passes_as_it_came() -> None:
    """Until a voice is known nothing is the room: a quiet caller's first words are heard."""
    came = speech_like(5, 4.0, A_TELEVISION)
    assert np.array_equal(Line().through(came), came.astype(np.int16))


def test_the_caller_is_heard_whole_over_a_television() -> None:
    """Every frame the caller speaks in passes untouched, gaps between words included."""
    came, stops = a_call(6.0, 0.0)
    heard = Line().through(came)
    assert np.array_equal(heard[:stops], came[:stops].astype(np.int16))


# 2026-11-14: the television was taken for the caller a quarter of a second after her turn closed.
def test_the_television_is_silent_once_the_caller_stops() -> None:
    """After the hold, what the line carries of the room is digital silence."""
    came, stops = a_call(6.0, 5.0)
    heard = Line().through(came)
    held = stops + int(RATE * (HELD_S + 0.35))
    assert not heard[held:].any()
    assert came[held:].any()


def test_a_voice_as_loud_as_the_callers_is_not_muted() -> None:
    """Six dB under the caller is somebody at the caller's side: it passes."""
    stops = int(RATE * 6.0)
    came = speech_like(5, 11.0, A_VOICE * 10 ** (-6 / 20))
    came[:stops] += speech_like(7, 6.0, A_VOICE)
    heard = Line().through(came)
    after = slice(stops + RATE, None)
    assert np.mean(heard[after] != 0) > 0.5


# 2026-11-15: at 20 dB a television 18 under the caller passed whole.
def test_a_television_eighteen_db_under_the_caller_is_silent_too() -> None:
    """What a caller would call "on, not loud" is under the bar once the caller is known."""
    stops = int(RATE * 6.0)
    came = speech_like(5, 11.0, A_VOICE * 10 ** (-18 / 20))
    came[:stops] += speech_like(7, 6.0, A_VOICE)
    heard = Line().through(came.astype(np.int16).astype(np.float64))
    assert not heard[stops + int(RATE * (HELD_S + 0.35)) :].any()


def test_the_room_is_heard_again_after_the_caller_was_quiet_for_long() -> None:
    """A caller far under the voice the call knew is learnt again, on the caller's own time alone."""
    came, stops = a_call(6.0, FORGOTTEN_AFTER_S + 6.0)
    line = Line()
    heard = line.through(came)
    assert heard[-RATE * 2 :].any()
    # While the agent speaks nobody expects the caller: the time is not counted, and the room stays muted.
    line = Line()
    line.through(came[:stops])
    line.agent_speaks = True
    assert not line.through(came[stops:])[-RATE * 2 :].any()


def test_digital_silence_has_no_level_and_a_short_frame_is_one_slice() -> None:
    """A line that carries nothing teaches nothing; a frame under 10 ms is weighed whole."""
    assert levels_of(frame_of(np.zeros(A_ROOM_FRAME))).size == 0
    assert levels_of(frame_of(np.full(100, 1000.0))).size == 1
    assert levels_of(frame_of(np.zeros(0))).size == 0
