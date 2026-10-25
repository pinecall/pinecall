"""The echo canceller: the agent's voice out of the caller's audio, the frames passed on whole, where it applies."""

from typing import override

import numpy as np
from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.voice import io

from pinecall_runtime.enums import Channel
from pinecall_runtime.session import echo

RATE = 24_000
SLICE = RATE // 100
# 50 ms, as the room's input hands the session its frames.
A_ROOM_FRAME = SLICE * 5
SECONDS = 6
# The agent's voice comes back 120 ms late and at half its level, as a laptop's speakers return it.
ECHO_LATE = SLICE * 12
ECHO_LEVEL = 0.5


def frame_of(samples: np.ndarray) -> rtc.AudioFrame:
    return rtc.AudioFrame(
        data=bytearray(samples.tobytes()), sample_rate=RATE, num_channels=1, samples_per_channel=len(samples)
    )


def energy(frames: list[rtc.AudioFrame]) -> float:
    joined = np.concatenate([np.frombuffer(frame.data.tobytes(), dtype=np.int16) for frame in frames]).astype(
        np.float64
    )
    return float(np.mean(joined**2))


class Played:
    """A call played through one canceller at the room's pace: the agent's audio out, the caller's in."""

    def __init__(self) -> None:
        """A canceller whose clock moves one room frame at a time."""
        self.now = 0.0
        self.canceller = echo.Canceller(clock=lambda: self.now)

    def through(self, agent: np.ndarray, caller: np.ndarray) -> np.ndarray:
        """Each 50 ms the agent sent (nothing while it is silent) and the caller's, cleared or not."""
        out = np.zeros_like(caller)
        for at in range(0, len(caller), A_ROOM_FRAME):
            self.now += A_ROOM_FRAME / RATE
            sent = agent[at : at + A_ROOM_FRAME]
            if sent.any():
                self.canceller.played(frame_of(sent))
            cleared = self.canceller.heard(frame_of(caller[at : at + A_ROOM_FRAME]))
            out[at : at + len(sent)] = np.frombuffer(cleared.data.tobytes(), dtype=np.int16)
        return out


def speech_like(seed: int, seconds: float) -> np.ndarray:
    """Noise in syllables: bursts of 100 to 300 ms and short gaps, as a voice's energy comes and goes."""
    rng = np.random.default_rng(seed)
    voice = np.zeros(int(RATE * seconds))
    at = 0
    while at < len(voice):
        burst = int(RATE * rng.uniform(0.1, 0.3))
        voice[at : at + burst] = rng.standard_normal(min(burst, len(voice) - at)) * rng.uniform(1500, 4000)
        at += burst + int(RATE * rng.uniform(0.03, 0.12))
    return voice


def heard_back(voice: np.ndarray, level: float) -> np.ndarray:
    """The agent's voice as a laptop's speakers return it: 120 ms late and softer."""
    return np.concatenate([np.zeros(ECHO_LATE), voice[:-ECHO_LATE] * level])


def as_pcm(samples: np.ndarray) -> np.ndarray:
    return np.clip(samples, -32768, 32767).astype(np.int16)


def test_the_agents_voice_heard_back_is_mostly_taken_out() -> None:
    """Its late, softer copy as the caller's audio is heard as an echo, and taken out."""
    voice = speech_like(7, SECONDS)
    played = Played()
    came = as_pcm(heard_back(voice, ECHO_LEVEL))
    cleared = played.through(as_pcm(voice), came)
    assert played.canceller.meter.echo
    # The last two seconds, once it has found the delay: 20 dB down or more.
    tail = slice(RATE * (SECONDS - 2), None)
    assert np.mean(cleared[tail].astype(np.float64) ** 2) < np.mean(came[tail].astype(np.float64) ** 2) * 0.01


# 2026-10-25: with no echo to learn, AEC3 took a "Bye." said over the agent for its echo and kept 1 % of it.
def test_a_caller_whose_audio_carries_no_echo_is_heard_whole_while_the_agent_speaks() -> None:
    """Headphones, or a browser that cancelled the echo: what the caller says over the agent passes untouched."""
    voice = speech_like(7, SECONDS)
    caller = np.zeros(len(voice))
    bye = speech_like(11, 0.4)
    caller[RATE * 4 : RATE * 4 + len(bye)] = bye
    came = as_pcm(caller + np.random.default_rng(3).standard_normal(len(voice)) * 20)
    played = Played()
    cleared = played.through(as_pcm(voice), came)
    assert not played.canceller.meter.echo
    assert np.array_equal(cleared, came)


def test_a_caller_talking_over_the_agent_does_not_let_a_found_echo_through() -> None:
    """Once heard, the echo stays cancelled while the caller talks over the agent for a while."""
    voice = speech_like(7, SECONDS * 2)
    caller = heard_back(voice, ECHO_LEVEL)
    talking = speech_like(13, 3.0)
    caller[RATE * 8 : RATE * 8 + len(talking)] += talking
    played = Played()
    cancelling: list[bool] = []
    for second in range(0, SECONDS * 2):
        span = slice(RATE * second, RATE * (second + 1))
        played.through(as_pcm(voice[span]), as_pcm(caller[span]))
        cancelling.append(played.canceller.meter.echo)
    assert all(cancelling[3:])


def test_a_frame_short_of_a_slice_passes_as_it_came() -> None:
    """The canceller takes 10 ms at a time; a tail shorter than that is not touched, and the length holds."""
    canceller = echo.Canceller()
    odd = frame_of(np.full(SLICE * 2 + 7, 1000, dtype=np.int16))
    cleared = canceller.heard(odd)
    assert cleared.samples_per_channel == SLICE * 2 + 7
    assert cleared.data.tobytes()[-14:] == odd.data.tobytes()[-14:]


class Sink(io.AudioOutput):
    """The room's output, faked: what it was handed."""

    def __init__(self) -> None:
        super().__init__(label="sink", capabilities=io.AudioOutputCapabilities(pause=True), sample_rate=RATE)
        self.frames: list[rtc.AudioFrame] = []
        self.flushed = 0

    @override
    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        await super().capture_frame(frame)
        self.frames.append(frame)

    @override
    def flush(self) -> None:
        super().flush()
        self.flushed += 1

    @override
    def clear_buffer(self) -> None:
        self.frames.clear()


async def test_the_agents_audio_reaches_the_room_untouched_and_the_canceller_too() -> None:
    """The reference output hands every frame on as it came, and its flushes and clears."""
    sink = Sink()
    output = echo.ReferenceOutput(echo.Canceller(), sink)
    sent = frame_of(np.full(A_ROOM_FRAME, 2000, dtype=np.int16))
    await output.capture_frame(sent)
    output.flush()
    assert [frame.data.tobytes() for frame in sink.frames] == [sent.data.tobytes()]
    assert sink.flushed == 1 and output.sample_rate == RATE
    output.clear_buffer()
    assert sink.frames == []


def a_session() -> AgentSession[None]:
    """A session whose audio in and out are set, as livekit leaves them after start."""
    live: AgentSession[None] = AgentSession()
    live.input.audio = io.AudioInput(label="room")
    live.output.audio = Sink()
    return live


# Async: livekit's AgentSession takes the running loop; alone, the file had none to give it.
async def test_a_web_call_gets_the_canceller_and_a_phone_call_does_not() -> None:
    """The visitor's browser hands the agent's voice back; a handset cancels its own."""
    web = a_session()
    assert echo.cancel(web, Channel.web) is not None
    assert isinstance(web.input.audio, echo.ClearedInput) and isinstance(web.output.audio, echo.ReferenceOutput)
    phone = a_session()
    assert echo.cancel(phone, Channel.phone) is None
    assert not isinstance(phone.input.audio, echo.ClearedInput)
