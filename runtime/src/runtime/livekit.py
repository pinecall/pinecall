"""LiveKit's server API: one client per env on the box's key pair, who is in a room, and an event LiveKit signed."""

import asyncio
from collections.abc import AsyncGenerator, Collection, Mapping
from contextlib import asynccontextmanager

from livekit import api
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.room import DeleteRoomRequest, ListParticipantsRequest, ListRoomsRequest
from livekit.protocol.webhook import WebhookEvent

from runtime.config import Settings
from runtime.enums import Env
from runtime.exceptions import ConfigurationError, Unauthorized

NO_LIVEKIT = "LIVEKIT_API_KEY and LIVEKIT_API_SECRET are unset: this process cannot reach the SFU"

# Room names ride one request's query, so they are asked for in batches.
ROOMS_A_REQUEST = 100

# livekit's code for a room that is not there.
ROOM_GONE = "not_found"

# Who is a person in a room: a browser's participant, and a phone's leg.
A_PERSON = frozenset({ParticipantInfo.Kind.STANDARD, ParticipantInfo.Kind.SIP})

type Servers = Mapping[Env, api.LiveKitAPI]


def key_pair(settings: Settings) -> tuple[str, str]:
    """The box's LiveKit key and secret; ConfigurationError when unset."""
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise ConfigurationError(NO_LIVEKIT)
    return settings.livekit_api_key, settings.livekit_api_secret.get_secret_value()


# livekit-api opens an HTTP session per client: one per LiveKit and process. Both envs take the
# box's one key pair, so a token the gateway signs opens a room on either.
@asynccontextmanager
async def open_servers(settings: Settings) -> AsyncGenerator[Servers]:
    """Each env's LiveKit client, the one client where the envs share a LiveKit; closed after."""
    key, secret = key_pair(settings)
    production = api.LiveKitAPI(settings.livekit_url_of(Env.production), key, secret)
    servers: dict[Env, api.LiveKitAPI] = {Env.production: production, Env.sandbox: production}
    if settings.livekit_url_of(Env.sandbox) != settings.livekit_url_of(Env.production):
        servers[Env.sandbox] = api.LiveKitAPI(settings.livekit_url_of(Env.sandbox), key, secret)
    try:
        yield servers
    finally:
        for server in dict.fromkeys(servers.values()):
            await server.aclose()


# A room is a live call only while an agent is in it: a browser tab or a supervisor keeps a room
# open long after its job is gone. The rooms of a batch are asked together: asked one after
# another, a reaper's pass over a hundred calls was a hundred round trips in a row.
async def rooms_with_an_agent(server: api.LiveKitAPI, names: Collection[str]) -> set[str]:
    """The rooms of these that exist with an agent in them."""
    wanted = list(names)
    served: set[str] = set()
    for start in range(0, len(wanted), ROOMS_A_REQUEST):
        batch = wanted[start : start + ROOMS_A_REQUEST]
        listed = await server.room.list_rooms(ListRoomsRequest(names=batch))
        found = [room.name for room in listed.rooms]
        present = await asyncio.gather(*(participants_in(server, name) for name in found))
        for name, participants in zip(found, present, strict=True):
            if any(participant.kind == ParticipantInfo.Kind.AGENT for participant in participants):
                served.add(name)
    return served


async def close_room(server: api.LiveKitAPI, name: str) -> None:
    """Delete the room, which hangs up everyone still in it; a room already gone is fine."""
    try:
        await server.room.delete_room(DeleteRoomRequest(room=name))
    except api.TwirpError as refused:
        if refused.code != ROOM_GONE:
            raise


# A room gone is nobody left in it.
async def participants_in(server: api.LiveKitAPI, name: str) -> list[ParticipantInfo]:
    """Who is in the room: nobody when it is gone."""
    try:
        listed = await server.room.list_participants(ListParticipantsRequest(room=name))
    except api.TwirpError as refused:
        if refused.code != ROOM_GONE:
            raise
        return []
    return list(listed.participants)


async def is_left_alone(server: api.LiveKitAPI, name: str) -> bool:
    """Whether a person is still in the room and no agent is."""
    kinds = {participant.kind for participant in await participants_in(server, name)}
    return ParticipantInfo.Kind.AGENT not in kinds and bool(kinds & A_PERSON)


# livekit signs each event with a key of the server's: a token whose sha256 claim is the body's.
# The library raises a bare Exception for a body that does not match its token. The pair is the
# box's own, read by `key_pair`, which refuses an empty one: an event verified against an empty
# key is an event anybody can sign.
def verify_event(settings: Settings, body: str, token: str) -> WebhookEvent:
    """The event of a body LiveKit signed with the box's key, or Unauthorized."""
    key, secret = key_pair(settings)
    try:
        return api.WebhookReceiver(api.TokenVerifier(key, secret)).receive(body, token)
    except Exception as refused:
        raise Unauthorized(f"the event carries no signature of this box's LiveKit key: {refused}") from refused
