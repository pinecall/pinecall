"""A visitor's room as their token asks for it: the fleet it reaches, and how long it outlives them."""

from runtime.fleet.service.dispatches import A_VISITOR_RETURNS_S, room_dispatch
from runtime.wire.dispatch import Dispatch


def test_a_visitors_room_reaches_the_envs_fleet_with_the_calls_dispatch() -> None:
    """One dispatch, to the fleet named, carrying whose call it is."""
    carried = Dispatch(agent="front", org="org_1")
    (reached,) = room_dispatch("pinecall-sandbox", carried).agents
    assert (reached.agent_name, reached.metadata) == ("pinecall-sandbox", carried.dump())


# Equal, LiveKit closed the room at the second the call's wait ended: the job ended as one whose
# room went away and the call was sealed `drained`, never as a caller who hung up (2026-11-11).
def test_a_visitors_room_outlives_the_wait_their_call_gives_them() -> None:
    """The call's own clock ends it, with its room still up; LiveKit's is the one behind it."""
    assert room_dispatch("pinecall-sandbox", Dispatch()).departure_timeout > A_VISITOR_RETURNS_S
