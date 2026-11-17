"""A link shaped as a bad network is: packets lost at random, held a delay and its jitter, a rate capped by a queue."""

import asyncio
import random as randomness
from collections.abc import Callable
from dataclasses import dataclass

# What waits behind a capped rate: a packet that would wait longer is dropped, as a router's queue
# drops its tail. 300 ms is what a consumer access router holds.
QUEUE_S = 0.3
BITS_A_BYTE = 8


@dataclass(frozen=True, slots=True)
class LinkShape:
    """How a link treats what crosses it: the share it loses, how long it holds each packet, how much it carries."""

    # The share of packets lost at random, 0 to 1.
    loss: float = 0.0
    # Milliseconds every packet is held, and how far each one's hold moves around it, either way.
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    # Kilobits a second the link carries; None carries anything.
    rate_kbps: float | None = None

    @property
    def is_clean(self) -> bool:
        """Whether the link changes nothing of what crosses it."""
        return self.loss <= 0 and self.delay_ms <= 0 and self.jitter_ms <= 0 and self.rate_kbps is None


@dataclass(slots=True)
class LinkCounts:
    """What a link did with its packets: those it carried, those it lost at random, those its queue dropped."""

    carried: int = 0
    lost: int = 0
    dropped: int = 0


# One direction of a path. A packet never overtakes the one before it: jitter on one path is a queue
# that grows and drains, and a packet that left later arrives later.
class Link:
    """One direction of a shaped link: each packet handed to it is delivered late, or never."""

    def __init__(self, shape: LinkShape, dice: randomness.Random | None = None) -> None:
        self.shape = shape
        self.dice = dice or randomness.Random()
        self.counts = LinkCounts()
        # When the capped rate has sent everything it was handed, and when the last packet is delivered.
        self._free_at = 0.0
        self._last_at = 0.0

    def carry(self, packet: bytes, deliver: Callable[[bytes], None]) -> None:
        """Take one packet: deliver it after the link's hold, or lose it."""
        hold = self.hold_of(len(packet), asyncio.get_running_loop().time())
        if hold is None:
            return
        if hold <= 0:
            deliver(packet)
        else:
            asyncio.get_running_loop().call_later(hold, deliver, packet)

    def hold_of(self, size: int, now: float) -> float | None:
        """How long a packet of this size handed over now is held, in seconds; None when the link loses it."""
        shape = self.shape
        if shape.loss > 0 and self.dice.random() < shape.loss:
            self.counts.lost += 1
            return None
        leaves = now
        if shape.rate_kbps is not None:
            waits = max(self._free_at - now, 0.0)
            if waits > QUEUE_S:
                self.counts.dropped += 1
                return None
            leaves = now + waits + size * BITS_A_BYTE / (shape.rate_kbps * 1000)
            self._free_at = leaves
        jitter = self.dice.uniform(-shape.jitter_ms, shape.jitter_ms) if shape.jitter_ms > 0 else 0.0
        arrives = max(leaves + max(shape.delay_ms + jitter, 0.0) / 1000, self._last_at)
        self._last_at = arrives
        self.counts.carried += 1
        return arrives - now
