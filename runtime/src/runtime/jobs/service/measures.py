"""A worker's last minute: what its calls' job processes tell it, and what its heartbeat carries."""

import asyncio
import math
import socket
import tempfile
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

from runtime.exceptions import ValidationError
from runtime.kit.text import a_mapping
from runtime.wire.base import BatchedEntry
from runtime.wire.worker import JobReport

# What the heartbeat carries is the last minute's, as the roster judges it.
WINDOW_S = 60.0

# A busy minute is thousands of turns: past this many, the oldest are forgotten early.
MOST_KEPT = 10_000

# A p95 is read off this many turns at least; fewer, and the heartbeat carries none.
TURNS_FOR_A_P95 = 5
P95 = 0.95

# How a call that failed ended; one datagram per thing told, and a datagram lost is uncounted.
AN_ERROR = "error"


@dataclass(frozen=True, slots=True)
class Minute:
    """A worker's calls over the last minute: ended, failed, error entries, and first audio."""

    ended: int
    # Of the calls that ended, those that ended in an error.
    failed: int
    errors: int
    turns: int
    first_audio_p95_s: float | None


class LastMinute:
    """What the worker's job processes told it, kept for a minute, in the worker's main process."""

    def __init__(self) -> None:
        """Nothing heard yet."""
        self.first_audio: deque[tuple[float, float]] = deque(maxlen=MOST_KEPT)
        self.errors: deque[float] = deque(maxlen=MOST_KEPT)
        self.ended: deque[tuple[float, bool]] = deque(maxlen=MOST_KEPT)

    def hear(self, message: bytes, now: float) -> None:
        """One datagram from a job; one that does not read is dropped."""
        try:
            report = JobReport.parse_json(message, "a job's report")
        except ValidationError:
            return
        if report.first_audio_s is not None:
            self.first_audio.append((now, report.first_audio_s))
        if report.error:
            self.errors.append(now)
        if report.ended is not None:
            self.ended.append((now, report.ended == AN_ERROR))

    def read_minute(self, now: float) -> Minute:
        """The minute up to now."""
        since = now - WINDOW_S
        while self.first_audio and self.first_audio[0][0] < since:
            self.first_audio.popleft()
        while self.errors and self.errors[0] < since:
            self.errors.popleft()
        while self.ended and self.ended[0][0] < since:
            self.ended.popleft()
        waits = sorted(value for _, value in self.first_audio)
        return Minute(
            ended=len(self.ended),
            failed=sum(1 for _, failed in self.ended if failed),
            errors=len(self.errors),
            turns=len(waits),
            first_audio_p95_s=nearest_rank(waits, P95) if len(waits) >= TURNS_FOR_A_P95 else None,
        )


class _Hearing(asyncio.DatagramProtocol):
    def __init__(self, minute: LastMinute) -> None:
        self.minute = minute

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        del addr
        self.minute.hear(data, asyncio.get_running_loop().time())


# Private to the unit on the box (PrivateTmp=yes); the health port tells two workers of a machine
# apart, as it must already, since each binds its own.
def measures_path(fleet: str, port: int) -> Path:
    """Where a worker hears its jobs: a datagram socket its main process binds."""
    return Path(tempfile.gettempdir()) / f"pinecall-{fleet}-{port}.measures"


# Bound before livekit starts its processes; a leftover of a worker that died is taken over.
async def listen_for_jobs(path: Path, minute: LastMinute) -> asyncio.DatagramTransport:
    """Bind the socket the worker's jobs tell it through."""
    await asyncio.to_thread(path.unlink, missing_ok=True)
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: _Hearing(minute), local_addr=str(path), family=socket.AF_UNIX
    )
    return transport


# Called on every batch a job sends: most carry none of the three, and send nothing.
def report_batch(path: Path, entries: Sequence[BatchedEntry]) -> None:
    """Tell the worker what a batch of its call's entries says: first audio, errors, an end."""
    messages = [message for entry in entries if (message := _message_of(entry)) is not None]
    if not messages:
        return
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
        sender.settimeout(0)
        for message in messages:
            try:
                sender.sendto(message, str(path))
            except OSError:
                # A worker not listening (a test, or its main process gone) loses the measure only.
                return


# The one percentile of the worker's side: the heartbeat's p95 and the load lab's report read it here.
def nearest_rank(values: Sequence[float], share: float) -> float:
    """The value at this share of values already sorted, by nearest rank."""
    return values[max(math.ceil(share * len(values)) - 1, 0)]


def _message_of(entry: BatchedEntry) -> bytes | None:
    if entry.type == "turn.agent":
        measured = entry.data.get("metrics")
        waited = measured.get("e2e_latency") if a_mapping(measured) else None
        if isinstance(waited, int | float):
            return JobReport(first_audio_s=waited).dump_json().encode()
    if entry.type == AN_ERROR:
        return JobReport(error=True).dump_json().encode()
    if entry.type == "call.ended":
        reason = entry.data.get("reason")
        return JobReport(ended=reason if isinstance(reason, str) else "").dump_json().encode()
    return None
