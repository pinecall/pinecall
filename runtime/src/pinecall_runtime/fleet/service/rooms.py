"""The LiveKit adapter: a dispatch put on a room, who is in one, and LiveKit's signed events."""

from collections.abc import Collection, Mapping

from google.protobuf.json_format import ParseDict, ParseError
from livekit import api
from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest, RoomAgentDispatch
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.room import DeleteRoomRequest, ListParticipantsRequest, ListRoomsRequest, RoomConfiguration
from livekit.protocol.webhook import WebhookEvent

from pinecall_runtime.exceptions import Unauthorized, ValidationError
from pinecall_runtime.wire.dispatch import Dispatch

# A visitor's call waits this long for them to come back (a reload, a tab closed, a dropped line)
# before it ends; their room outlives them as long. LiveKit's own 20 s would close it under a reload.
A_VISITOR_RETURNS_S = 300

# Room names ride one request's query, so they are asked for in batches.
ROOMS_A_REQUEST = 100

# livekit's code for a room that is not there.
ROOM_GONE = "not_found"

# The seats a person sits in: a browser's, and a phone's leg.
A_PERSON = frozenset({ParticipantInfo.Kind.STANDARD, ParticipantInfo.Kind.SIP})


# livekit creates the dispatch from the token when the join creates the room, so the browser
# cannot change the agent, the org or the env it reaches. The room outlives its visitor as long
# as their call waits for them.
def room_dispatch(fleet: str, dispatch: Dispatch) -> RoomConfiguration:
    """The room configuration a visitor's token carries: one dispatch, to the env's fleet."""
    return RoomConfiguration(
        departure_timeout=A_VISITOR_RETURNS_S,
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


# A room is a live call only while an agent is in it: a browser tab or a supervisor keeps a
# room open long after its job is gone.
async def rooms_with_an_agent(server: api.LiveKitAPI, names: Collection[str]) -> set[str]:
    """The rooms of these that exist with an agent in them."""
    wanted = list(names)
    served: set[str] = set()
    for start in range(0, len(wanted), ROOMS_A_REQUEST):
        batch = wanted[start : start + ROOMS_A_REQUEST]
        rooms = await server.room.list_rooms(ListRoomsRequest(names=batch))
        for room in rooms.rooms:
            seats = await server.room.list_participants(ListParticipantsRequest(room=room.name))
            if any(seat.kind == ParticipantInfo.Kind.AGENT for seat in seats.participants):
                served.add(room.name)
    return served


async def close_room(server: api.LiveKitAPI, name: str) -> None:
    """Delete the room, which hangs up everyone still in it; a room already gone is fine."""
    try:
        await server.room.delete_room(DeleteRoomRequest(room=name))
    except api.TwirpError as refused:
        if refused.code != ROOM_GONE:
            raise


# A room gone is nobody left in it.
async def seats_in(server: api.LiveKitAPI, name: str) -> list[ParticipantInfo]:
    """Who is in the room: nobody when it is gone."""
    try:
        seats = await server.room.list_participants(ListParticipantsRequest(room=name))
    except api.TwirpError as refused:
        if refused.code != ROOM_GONE:
            raise
        return []
    return list(seats.participants)


async def left_alone(server: api.LiveKitAPI, name: str) -> bool:
    """Whether a person is still in the room and no agent is."""
    kinds = {seat.kind for seat in await seats_in(server, name)}
    return ParticipantInfo.Kind.AGENT not in kinds and bool(kinds & A_PERSON)


# livekit signs each event with a key of the server's: a token whose sha256 claim is the body's.
# The library raises a bare Exception for a body that does not match its token.
def livekit_event(body: str, token: str, key: str, secret: str) -> WebhookEvent:
    """The event of a body LiveKit signed with this key, or Unauthorized."""
    try:
        return api.WebhookReceiver(api.TokenVerifier(key, secret)).receive(body, token)
    except Exception as refused:
        raise Unauthorized(f"the event carries no signature of this box's LiveKit key: {refused}") from refused
