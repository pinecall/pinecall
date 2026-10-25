"""The caller's audio cleared of the agent's own voice: WebRTC's echo canceller, what the agent plays its reference."""

import time
from collections import deque
from collections.abc import Callable
from typing import override

import numpy as np
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

# AEC3 learns the echo path from the echo itself. A caller whose audio carries none (headphones, a
# browser that cancelled it whole, the simulated caller) never teaches it one, and its suppressor
# then takes the caller's voice for echo whenever the agent speaks: a "Bye." said over the agent kept
# 1 % of its energy, a sentence 75 % (measured on AEC3 here, 2026-10-25; with an echo as faint as
# -40 dB it kept 93 %). So the cleared audio is handed on only while the caller's audio is heard to
# carry the agent's voice, and the canceller learns all along either way.
# Heard by GCC-PHAT: the caller's waveform against the agent's, lag by lag up to a second. An echo is
# a delayed copy and peaks far above the rest; a voice talking over the agent never does. Over 120
# simulated calls with the caller talking over the agent at random, no echo peaked at 17 times its
# floor at most, a speaker's echo at 30 at least, at the right lag.
# A delay is found at 8 kHz as well as at the room's rate, for a sixth of the cost.
METER_RATE = 8000
# How far back the caller's audio is searched for the agent's voice: the room's queue, the network
# both ways and the browser's playout.
LONGEST_ECHO_S = 1.0
# How much of the recent past is compared, how often, and how much of it the agent must have spoken.
COMPARED_OVER_S = 4.0
JUDGED_EVERY_S = 0.5
SPOKE_FOR = 0.25
# The correlation's peak over its median: an echo is found above the first, and taken for gone only
# once that many judgements in a row, the agent speaking, fall below the second. An echo path rarely
# changes in a call; a caller talking over the agent, or a faint echo under the room's noise, dips
# the peak for a moment and must not let the echo through.
ECHO_FOUND_AT = 25.0
ECHO_GONE_UNDER = 10.0
GONE_AFTER = 4


class EchoMeter:
    """Whether the caller's audio carries the agent's voice: their waveforms compared, lag by lag."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """No echo until one is heard."""
        self.clock = clock
        self.echo = False
        self.missed = 0
        self.played: deque[tuple[float, np.ndarray]] = deque()
        self.heard: deque[tuple[float, np.ndarray]] = deque()
        self.judged_at = 0.0

    def agent(self, frame: rtc.AudioFrame) -> None:
        """The agent's audio as it leaves, ending now."""
        self._kept(self.played, frame)

    def caller(self, frame: rtc.AudioFrame) -> None:
        """The caller's audio as it arrives, ending now; judged again every half second."""
        self._kept(self.heard, frame)
        now = self.clock()
        if now - self.judged_at >= JUDGED_EVERY_S:
            self.judged_at = now
            self._judge(now)

    def _kept(self, kept: deque[tuple[float, np.ndarray]], frame: rtc.AudioFrame) -> None:
        now = self.clock()
        samples = np.frombuffer(frame.data.tobytes(), dtype=np.int16).astype(np.float64)
        samples = samples[:: frame.num_channels][:: max(1, frame.sample_rate // METER_RATE)]
        kept.append((now - len(samples) / METER_RATE, samples))
        while kept and kept[0][0] < now - COMPARED_OVER_S - LONGEST_ECHO_S - 1:
            kept.popleft()

    def _judge(self, now: float) -> None:
        start = now - COMPARED_OVER_S - LONGEST_ECHO_S
        agent, caller = _laid_out(self.played, start, now), _laid_out(self.heard, start, now)
        if np.count_nonzero(agent) < SPOKE_FOR * len(agent) or not caller.any():
            return
        size = 1 << (2 * len(caller) - 1).bit_length()
        crossed = np.fft.rfft(caller, size) * np.conj(np.fft.rfft(agent, size))
        lagged = np.fft.irfft(crossed / (np.abs(crossed) + 1e-9), size)[: round(LONGEST_ECHO_S * METER_RATE)]
        peak = float(lagged.max() / (np.median(np.abs(lagged)) + 1e-12))
        if peak >= ECHO_FOUND_AT:
            self.echo, self.missed = True, 0
        elif peak < ECHO_GONE_UNDER:
            self.missed += 1
            self.echo = self.echo and self.missed < GONE_AFTER
        else:
            self.missed = 0


class Canceller:
    """One call's echo canceller: the agent's audio in as the reference, the caller's out cleared."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """A canceller that has heard nothing yet."""
        self.apm = rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True)
        self.meter = EchoMeter(clock)

    def played(self, frame: rtc.AudioFrame) -> None:
        """The agent's audio as it leaves for the room, given to the canceller as the far end."""
        for piece, _ in _slices(frame):
            self.apm.process_reverse_stream(piece)
        self.meter.agent(frame)

    def heard(self, frame: rtc.AudioFrame) -> rtc.AudioFrame:
        """The caller's frame with the agent's voice taken out while it carries it, else as it came."""
        cleared = bytearray(frame.data.tobytes())
        for piece, at in _slices(frame):
            self.apm.set_stream_delay_ms(STREAM_DELAY_MS)
            self.apm.process_stream(piece)
            cleared[at : at + len(piece.data.tobytes())] = piece.data.tobytes()
        self.meter.caller(frame)
        if not self.meter.echo:
            return frame
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


# What arrived in the window as one stretch at the meter's rate, by when each piece arrived; silence
# where nothing did (the agent sends nothing while it is quiet).
def _laid_out(kept: deque[tuple[float, np.ndarray]], start: float, end: float) -> np.ndarray:
    laid = np.zeros(round((end - start) * METER_RATE))
    for at, samples in kept:
        first = round((at - start) * METER_RATE)
        if first + len(samples) <= 0 or first >= len(laid):
            continue
        cut = max(0, -first)
        piece = samples[cut : cut + len(laid) - max(first, 0)]
        laid[max(first, 0) : max(first, 0) + len(piece)] = piece
    return laid
