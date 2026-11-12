"""A dispatch: the name a worker is reached by, the one a visitor's token carries, and one put on a room."""

from collections.abc import Mapping

from google.protobuf.json_format import ParseDict, ParseError
from livekit import api
from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest, RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration

from runtime.exceptions import ValidationError
from runtime.wire.dispatch import Dispatch

# A visitor's call waits this long for them to come back (a reload, a tab closed, a dropped line)
# before it ends. LiveKit's own 20 s would close their room under a reload.
A_VISITOR_RETURNS_S = 300
# Their room outlives that wait, so the call's own clock is the one that ends it: its session says
# the caller hung up, seals the call and deletes the room. With the two equal, LiveKit closed the
# room first, the job ended as one whose room went away, and the call was sealed `drained` (8 web
# calls on 2026-11-11).
A_ROOM_OUTLIVES_THE_WAIT_S = 60

OVERFLOW = "overflow"


# A worker registers with LiveKit under <fleet>/<worker>, the fleet's overflow under
# <fleet>/overflow: a dispatch reaches exactly the workers registered under its name.
def agent_name(fleet: str, worker: str) -> str:
    """The name a worker of a fleet is registered under with LiveKit."""
    return f"{fleet}/{worker}"


def overflow_name(fleet: str) -> str:
    """The name the fleet's overflow is registered under with LiveKit."""
    return agent_name(fleet, OVERFLOW)


# livekit creates the dispatch from the token when the join creates the room, so the browser
# cannot change the agent, the org or the env it reaches. The room outlives its visitor for as
# long as their call waits for them, and then for what the call takes to end.
def room_dispatch(fleet: str, dispatch: Dispatch) -> RoomConfiguration:
    """The room configuration a visitor's token carries: one dispatch, to the env's fleet."""
    return RoomConfiguration(
        departure_timeout=A_VISITOR_RETURNS_S + A_ROOM_OUTLIVES_THE_WAIT_S,
        agents=[RoomAgentDispatch(agent_name=fleet, metadata=dispatch.dump())],
    )


# livekit creates the room if it does not exist; its name is the call id the worker opens.
async def dispatch_into(server: api.LiveKitAPI, room: str, agent: str, dispatch: Dispatch) -> None:
    """Send the workers registered under this name into a room, with the call's dispatch."""
    await server.agent_dispatch.create_dispatch(
        CreateAgentDispatchRequest(room=room, agent_name=agent, metadata=dispatch.dump())
    )


# A stock livekit client names the agent as room_config.agents[0].agent_name, in either spelling.
def client_named_agent(room_config: Mapping[str, object] | None) -> str | None:
    """The agent a livekit client put in the room configuration, or None."""
    if not room_config:
        return None
    try:
        parsed = ParseDict(dict(room_config), RoomConfiguration(), ignore_unknown_fields=True)
    except ParseError as malformed:
        raise ValidationError(f"room_config is not a LiveKit RoomConfiguration: {malformed}") from malformed
    agents = list(parsed.agents)
    return (agents[0].agent_name or None) if agents else None
