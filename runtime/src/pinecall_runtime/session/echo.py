"""The caller's audio cleared of the agent's own voice: WebRTC's echo canceller, what the agent plays its reference."""

from typing import override

from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.voice import io

from pinecall_runtime.enums import Channel

# A visitor on a laptop's speakers sends the agent's voice back into the room: the browser's own
# canceller leaves a residue, Whisper writes it as words ("Thank you.") and they took the floor
# (gpu.pinecall.io, 2026-10-17). livekit cancels echo in its clients and, for an agent, only with
# its cloud's models; its SDK carries WebRTC's canceller (AEC3) all the same, which its own console
# mode feeds with what it plays. Here both ends of the loop are this process: what the agent sends
# to the room is the far end, and the caller's audio is cleared before the VAD and the ears hear it.
# A phone is not: the handset and the network cancel their own echo, and a second canceller on a
# line with none only bends the caller's voice when both talk at once.
CANCELS_ECHO = frozenset({Channel.web})
# The canceller works on 10 ms at a time, at any rate the frames carry.
SLICES_PER_SECOND = 100
# The agent's audio leaves ahead of its echo: the room's queue (200 ms), the network both ways, the
# browser's playout. AEC3 finds the delay itself; this is where it starts looking. WebRTC forgets it
# after every near-end frame, so it is said again before each one, as livekit's console does.
STREAM_DELAY_MS = 300
BYTES_PER_SAMPLE = 2


class Canceller:
    """One call's echo canceller: the agent's audio in as the reference, the caller's out cleared."""

    def __init__(self) -> None:
        """A canceller that has heard nothing yet."""
        self.apm = rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True)

    def played(self, frame: rtc.AudioFrame) -> None:
        """The agent's audio as it leaves for the room, given to the canceller as the far end."""
        for piece, _ in _slices(frame):
            self.apm.process_reverse_stream(piece)

    def heard(self, frame: rtc.AudioFrame) -> rtc.AudioFrame:
        """The caller's frame with the agent's voice taken out; a tail short of 10 ms passes as it came."""
        cleared = bytearray(frame.data.tobytes())
        for piece, at in _slices(frame):
            self.apm.set_stream_delay_ms(STREAM_DELAY_MS)
            self.apm.process_stream(piece)
            cleared[at : at + len(piece.data.tobytes())] = piece.data.tobytes()
        return rtc.AudioFrame(
            data=cleared,
            sample_rate=frame.sample_rate,
            num_channels=frame.num_channels,
            samples_per_channel=frame.samples_per_channel,
        )


class ClearedInput(io.AudioInput):
    """The caller's audio, each frame through the canceller before the session hears it."""

    def __init__(self, canceller: Canceller, source: io.AudioInput) -> None:
        """Read from the source, clear, hand on."""
        super().__init__(label="EchoCanceller", source=source)
        self.canceller = canceller

    @override
    async def __anext__(self) -> rtc.AudioFrame:
        """The next frame of the caller's, cleared."""
        return self.canceller.heard(await super().__anext__())


class ReferenceOutput(io.AudioOutput):
    """The agent's audio on its way to the room, each frame given to the canceller as it goes."""

    def __init__(self, canceller: Canceller, next_in_chain: io.AudioOutput) -> None:
        """Pass everything on, and keep the canceller told."""
        super().__init__(
            label="EchoCanceller", next_in_chain=next_in_chain, capabilities=io.AudioOutputCapabilities(pause=True)
        )
        self.canceller = canceller

    @property
    @override
    def sample_rate(self) -> int | None:
        """The rate the room's output asks for."""
        return self.next_in_chain.sample_rate if self.next_in_chain else None

    @override
    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        """The frame to the room, and to the canceller."""
        if self.next_in_chain:
            await self.next_in_chain.capture_frame(frame)
        await super().capture_frame(frame)
        self.canceller.played(frame)

    @override
    def flush(self) -> None:
        """The segment is complete."""
        super().flush()
        if self.next_in_chain:
            self.next_in_chain.flush()

    @override
    def clear_buffer(self) -> None:
        """Stop playing at once."""
        if self.next_in_chain:
            self.next_in_chain.clear_buffer()


def cancel(live: AgentSession[None], channel: Channel) -> Canceller | None:
    """Put the canceller between the room and the session, where the channel needs one; None where not."""
    caller, agent = live.input.audio, live.output.audio
    if channel not in CANCELS_ECHO or caller is None or agent is None:
        return None
    canceller = Canceller()
    live.input.audio = ClearedInput(canceller, caller)
    live.output.audio = ReferenceOutput(canceller, agent)
    return canceller


# Each slice a frame of its own, over a copy: the canceller writes into what it is handed.
def _slices(frame: rtc.AudioFrame) -> list[tuple[rtc.AudioFrame, int]]:
    samples = frame.sample_rate // SLICES_PER_SECOND
    step = samples * frame.num_channels * BYTES_PER_SAMPLE
    data = frame.data.tobytes()
    return [
        (
            rtc.AudioFrame(
                data=bytearray(data[at : at + step]),
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
                samples_per_channel=samples,
            ),
            at,
        )
        for at in range(0, len(data) - step + 1, step)
    ]
