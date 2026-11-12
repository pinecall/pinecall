"""A call as a worker opens it at the gateway: what the jobs' tests open, write to and seal."""

from datetime import date

from runtime.calls.context import CallContext, Route, dump_context, new_call_id
from runtime.enums import Channel, Direction, Env
from runtime.jobs.service.arrival import TEST_VALUES_ON_THE_WIRE
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.client import GatewayClient
from runtime.wire.worker import OpenCallRequest
from tests.conftest import Tenant


def a_call(tenant: Tenant, agent: str) -> CallContext:
    """A sandbox call of the tenant's agent through the widget."""
    return CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller="web_1",
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 10, 16),
    )


def opening_of(tenant: Tenant, agent: str, **test_values: str) -> OpenCallRequest:
    """What a worker opens a new call of the tenant's agent with, on the test values given."""
    context = dump_context(a_call(tenant, agent))
    said = {"agent": agent, "context": context, TEST_VALUES_ON_THE_WIRE: test_values or None}
    return OpenCallRequest.model_validate(said)


async def opened(fleet: GatewayClient, tenant: Tenant, agent: str, **test_values: str) -> CallClient:
    """A call of the tenant's agent a worker opened at the gateway."""
    return await open_call(fleet, opening_of(tenant, agent, **test_values))
