"""A shaped link: what it loses, how long it holds a packet, what its queue drops, the order it keeps."""

import asyncio
import random

from runtime.kit.link import QUEUE_S, Link, LinkShape

A_PACKET = b"\x00" * 400


def test_a_clean_link_holds_nothing_and_says_it_is_clean() -> None:
    link = Link(LinkShape())
    assert LinkShape().is_clean
    assert link.hold_of(len(A_PACKET), now=10.0) == 0.0
    assert (link.counts.carried, link.counts.lost, link.counts.dropped) == (1, 0, 0)


def test_any_one_number_makes_a_link_a_shaped_one() -> None:
    shaped = (LinkShape(loss=0.1), LinkShape(delay_ms=1), LinkShape(jitter_ms=1), LinkShape(rate_kbps=64))
    assert not any(shape.is_clean for shape in shaped)


def test_the_share_lost_is_lost_at_random_and_counted() -> None:
    link = Link(LinkShape(loss=0.3), random.Random(7))
    held = [link.hold_of(len(A_PACKET), now=0.0) for _ in range(1000)]
    lost = len([hold for hold in held if hold is None])
    # Three hundred of a thousand, by a seeded dice: well inside these.
    assert 250 < lost < 350
    assert (link.counts.lost, link.counts.carried) == (lost, 1000 - lost)


def test_every_packet_is_held_the_delay_and_its_jitter_moves_each_within_its_bounds() -> None:
    link = Link(LinkShape(delay_ms=150, jitter_ms=40), random.Random(7))
    held = [link.hold_of(len(A_PACKET), now=float(second)) for second in range(200)]
    assert all(hold is not None and 0.110 <= hold <= 0.190 for hold in held)
    assert len({round(hold or 0.0, 3) for hold in held}) > 20, "the jitter moves the hold from packet to packet"


# Jitter on one path is a queue that grows and drains: a packet that left later arrives later.
def test_a_packet_never_overtakes_the_one_before_it() -> None:
    link = Link(LinkShape(delay_ms=100, jitter_ms=100), random.Random(7))
    arrivals = [now + (link.hold_of(len(A_PACKET), now) or 0.0) for now in (index * 0.02 for index in range(500))]
    assert arrivals == sorted(arrivals)


# 400 bytes at 80 kbps is 40 ms on the wire: handed together, the ninth would wait 320 ms.
def test_a_capped_rate_sends_one_packet_after_another_and_drops_what_would_wait_past_its_queue() -> None:
    link = Link(LinkShape(rate_kbps=80))
    held = [link.hold_of(len(A_PACKET), now=5.0) for _ in range(12)]
    sent = [hold for hold in held if hold is not None]
    assert len(sent) == 8
    assert all(abs(hold - 0.04 * (index + 1)) < 1e-9 for index, hold in enumerate(sent))
    assert link.counts.dropped == 4
    assert max(sent) <= QUEUE_S + 0.04


def test_a_queue_that_drained_carries_again() -> None:
    link = Link(LinkShape(rate_kbps=80))
    for _ in range(12):
        link.hold_of(len(A_PACKET), now=5.0)
    assert link.hold_of(len(A_PACKET), now=6.0) is not None
    assert link.counts.carried == 9


async def test_a_clean_link_delivers_at_once_and_a_slow_one_after_its_hold() -> None:
    at_once: list[bytes] = []
    Link(LinkShape()).carry(A_PACKET, at_once.append)
    assert at_once == [A_PACKET]
    late: list[bytes] = []
    Link(LinkShape(delay_ms=30)).carry(A_PACKET, late.append)
    assert late == []
    await asyncio.sleep(0.1)
    assert late == [A_PACKET]


async def test_a_lost_packet_is_never_delivered() -> None:
    delivered: list[bytes] = []
    Link(LinkShape(loss=1.0)).carry(A_PACKET, delivered.append)
    await asyncio.sleep(0.01)
    assert delivered == []
