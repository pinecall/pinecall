"""How a worker asks its gateway: the waits between tries, what counts as away, the trace, the balancer's name."""

import asyncio

import pytest
from opentelemetry import context as otel_context
from opentelemetry import trace

from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.jobs.service.stream import affine, again, away, traced, waits


def test_the_waits_double_to_the_cap() -> None:
    """Half a second, then double, never past five."""
    pauses = waits()
    assert [next(pauses) for _ in range(6)] == [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]


def test_away_is_unreachable_or_a_5xx_and_a_4xx_is_an_answer() -> None:
    """Nobody answering or a 5xx is the gateway away; a 4xx is the gateway answering no."""
    assert away(GatewayUnavailable("x"))
    assert away(GatewayUnavailable("x", answered=503))
    assert not away(GatewayUnavailable("x", answered=404))


async def test_an_attempt_is_asked_again_while_the_gateway_is_away() -> None:
    """A 502 is tried again until the gateway answers."""
    tries: list[int] = []

    async def attempt() -> str:
        tries.append(1)
        if len(tries) < 2:
            raise GatewayUnavailable("away", answered=502)
        return "done"

    assert await again(attempt, None, "x") == "done"
    assert len(tries) == 2


async def test_a_4xx_is_final_and_not_asked_again() -> None:
    """A refusal is the answer: asking again would get the same."""
    tries: list[int] = []

    async def attempt() -> str:
        tries.append(1)
        raise GatewayUnavailable("no", answered=409)

    with pytest.raises(GatewayUnavailable):
        await again(attempt, None, "x")
    assert len(tries) == 1


async def test_an_attempt_with_a_deadline_stops_asking_at_it() -> None:
    """A gateway away past the deadline ends the asking with the refusal."""

    async def attempt() -> str:
        raise GatewayUnavailable("away")

    with pytest.raises(GatewayUnavailable):
        await asyncio.wait_for(again(attempt, 0.1, "x"), 2)


def test_the_workers_trace_rides_its_requests_to_the_gateway() -> None:
    """The span a worker is in goes with each request as a traceparent; none, nothing."""
    assert traced() == {}
    span = trace.NonRecordingSpan(
        trace.SpanContext(trace_id=0x1234, span_id=0x5678, is_remote=False, trace_flags=trace.TraceFlags(1))
    )
    token = otel_context.attach(trace.set_span_in_context(span))
    try:
        carried = traced()
    finally:
        otel_context.detach(token)
    assert carried == {"traceparent": f"00-{0x1234:032x}-{0x5678:016x}-01"}


def test_a_calls_doors_name_the_call_for_the_balancer_and_the_others_do_not() -> None:
    """A call's requests carry its id, so the balancer sends them to the gateway that holds it."""
    assert affine("/v1/calls/CA_1/entries") == {"Pinecall-Call": "CA_1"}
    assert affine("/v1/calls/CA_1") == {"Pinecall-Call": "CA_1"}
    assert affine("/v1/calls") == {}
    assert affine("/v1/fleet/heartbeat") == {}
