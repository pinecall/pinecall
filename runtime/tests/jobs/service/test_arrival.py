"""The route a call takes: the agent the job names, else the number dialled, else the worker's default."""

import pytest

from runtime.calls.context import Route
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import NotFound
from runtime.jobs.service.arrival import resolve_route
from runtime.telephony.service.legs import Arrival
from runtime.wire.dispatch import Dispatch

NUMBER = "+15550100"
CALLER = "+15550199"
A_PHONE = Arrival(caller=CALLER, channel=Channel.phone, direction=Direction.inbound, number=NUMBER)
A_PAGE = Arrival(caller="room_1", channel=Channel.web, direction=Direction.inbound)
AT_THE_NUMBER = Route(org="org_a", agent="front", channel=Channel.phone, number=NUMBER)
IN_THE_SANDBOX = Route(org="org_a", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox)


def test_a_number_dialled_finds_the_route_that_answers_it() -> None:
    """The job names no agent: the number dialled decides."""
    assert resolve_route(Dispatch(), A_PHONE, [AT_THE_NUMBER], "fallback") == AT_THE_NUMBER


def test_a_number_nobody_answers_is_refused_rather_than_sent_to_the_default() -> None:
    """A number with no route is refused, never answered by the worker's default agent."""
    with pytest.raises(NotFound, match="nobody answers"):
        resolve_route(Dispatch(), A_PHONE, [], "fallback")


def test_with_no_agent_and_no_number_only_the_workers_default_is_left() -> None:
    """A page names no number: with no default agent the call has nowhere to go."""
    with pytest.raises(NotFound, match="no default agent"):
        resolve_route(Dispatch(), A_PAGE, [], None)


def test_the_dispatchs_agent_wins_over_the_number() -> None:
    """An agent the job names is the one that answers, on its own route."""
    other = Route(org="org_a", agent="sales", channel=Channel.phone, number="+15550111")
    assert resolve_route(Dispatch(agent="sales"), A_PHONE, [AT_THE_NUMBER, other], None) == other


def test_every_agent_answers_on_the_widget_without_a_stored_route() -> None:
    """The widget is every agent's door: no row is stored for it."""
    found = resolve_route(Dispatch(agent="front", org="org_a", env=Env.sandbox), A_PAGE, [], None)
    assert found == Route(org="org_a", agent="front", channel=Channel.web, env=Env.sandbox)


def test_an_agent_with_no_door_on_the_channel_names_where_it_looked() -> None:
    """Refused, the call says which org and env it looked in."""
    with pytest.raises(NotFound, match="org_a/production"):
        resolve_route(Dispatch(agent="sales"), A_PHONE, [AT_THE_NUMBER], None)


def test_a_ring_handed_to_the_sandbox_keeps_the_production_number_it_dialled() -> None:
    """A production ring handed to a developer's sandbox still names the number the caller dialled."""
    dispatch = Dispatch(agent="front", org="org_a", env=Env.sandbox, diverted_from=Env.production)
    assert resolve_route(dispatch, A_PHONE, [], None) == IN_THE_SANDBOX


def test_a_ring_handed_over_whose_leg_named_nobody_is_refused_rather_than_run_here() -> None:
    """A handed-over ring that lost its agent on the way is refused, never answered by the number."""
    with pytest.raises(NotFound, match="names no agent"):
        resolve_route(Dispatch(env=Env.sandbox, diverted_from=Env.production), A_PHONE, [AT_THE_NUMBER], None)
