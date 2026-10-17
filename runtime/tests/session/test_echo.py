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


def test_the_agents_voice_heard_back_is_mostly_taken_out() -> None:
    """A broadband reference, as speech is, and its late, softer copy as the caller's audio: the copy is gone."""
    voice = (np.random.default_rng(7).standard_normal(RATE * SECONDS) * 4000).astype(np.int16)
    heard_back = np.concatenate([np.zeros(ECHO_LATE, np.int16), (voice[:-ECHO_LATE] * ECHO_LEVEL).astype(np.int16)])
    canceller = echo.Canceller()
    before: list[rtc.AudioFrame] = []
    after: list[rtc.AudioFrame] = []
    for at in range(0, len(voice), A_ROOM_FRAME):
        canceller.played(frame_of(voice[at : at + A_ROOM_FRAME]))
        came = frame_of(heard_back[at : at + A_ROOM_FRAME])
        cleared = canceller.heard(came)
        assert cleared.samples_per_channel == came.samples_per_channel
        if at >= RATE * (SECONDS - 2):
            before.append(came)
            after.append(cleared)
    # The last two seconds, once it has found the delay: 20 dB down or more (AEC3 measured ~48 dB here).
    assert energy(after) < energy(before) * 0.01


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


def test_a_web_call_gets_the_canceller_and_a_phone_call_does_not() -> None:
    """The visitor's browser hands the agent's voice back; a handset cancels its own."""
    web = a_session()
    assert echo.cancel(web, Channel.web) is not None
    assert isinstance(web.input.audio, echo.ClearedInput) and isinstance(web.output.audio, echo.ReferenceOutput)
    phone = a_session()
    assert echo.cancel(phone, Channel.phone) is None
    assert not isinstance(phone.input.audio, echo.ClearedInput)
