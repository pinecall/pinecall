"""How a worker asks its gateway: what counts as away, the trace, the balancer's name, a refusal in one sentence."""

import secrets

import pytest
from opentelemetry import context as otel_context
from opentelemetry import trace

from runtime.actor import Scope
from runtime.enums import Env
from runtime.exceptions import UpstreamError
from runtime.jobs.service.client import (
    GatewayClient,
    affinity_headers,
    open_gateway,
    trace_headers,
    unavailable,
)
from runtime.wire.worker import HeartbeatRequest
from tests.conftest import Tenant, needs_the_services


def test_away_is_unreachable_or_a_5xx_and_a_4xx_is_an_answer() -> None:
    """Nobody answering or a 5xx is the gateway away, asked again; a 4xx is the gateway answering no."""
    assert unavailable("x").retryable
    assert unavailable("x", answered=503).retryable
    assert not unavailable("x", answered=404).retryable


def test_the_workers_trace_rides_its_requests_to_the_gateway() -> None:
    """The span a worker is in goes with each request as a traceparent; none, nothing."""
    assert trace_headers() == {}
    span = trace.NonRecordingSpan(
        trace.SpanContext(trace_id=0x1234, span_id=0x5678, is_remote=False, trace_flags=trace.TraceFlags(1))
    )
    token = otel_context.attach(trace.set_span_in_context(span))
    try:
        carried = trace_headers()
    finally:
        otel_context.detach(token)
    assert carried == {"traceparent": f"00-{0x1234:032x}-{0x5678:016x}-01"}


def test_a_calls_requests_name_the_call_for_the_balancer_and_the_others_do_not() -> None:
    """A call's requests carry its id, so the balancer sends them to the gateway that holds it."""
    assert affinity_headers("/v1/calls/CA_1/entries") == {"Pinecall-Call": "CA_1"}
    assert affinity_headers("/v1/calls/CA_1") == {"Pinecall-Call": "CA_1"}
    assert affinity_headers("/v1/calls") == {}
    assert affinity_headers("/v1/fleet/heartbeat") == {}


# Registered with LiveKit (`agent_name`) as a worker that reports in is: one that is not counts as
# heard with no seat, and every spoken simulation on this test gateway was refused as the fleet full
# for as long as it was heard (2026-10-24, three runs of four).
@needs_the_services
async def test_a_heartbeat_says_the_fleet_is_open(fleet: GatewayClient) -> None:
    """A worker of the sandbox fleet that reports in is neither cordoned nor full."""
    name = f"w-{secrets.token_hex(3)}"
    beat = HeartbeatRequest(
        fleet="pinecall-sandbox", worker=name, agent_name=name, active=0, max_jobs=4, load=0.1, draining=False
    )
    answered = await fleet.beat(beat)
    assert not answered.cordoned
    assert not answered.full


@needs_the_services
async def test_a_refusal_names_the_request_refused_and_its_status(fleet: GatewayClient, tenant: Tenant) -> None:
    """The gateway's 404 comes back as one sentence naming the request, with the status beside it."""
    with pytest.raises(UpstreamError, match="/v1/agents/nobody/config") as refused:
        await fleet.get_agent("nobody", Scope(tenant.org, Env.sandbox))
    assert refused.value.answered == 404


async def test_a_gateway_that_is_not_there_is_a_refusal_and_never_a_traceback() -> None:
    """Nobody answering at the address is a refusal with no status, never a crash."""
    client = open_gateway("http://127.0.0.1:9", "pc_test_x")
    with pytest.raises(UpstreamError) as refused:
        await client.beat(
            HeartbeatRequest(fleet="pinecall", worker="w1", active=0, max_jobs=4, load=0.0, draining=False)
        )
    assert refused.value.answered is None
    await client.aclose()
