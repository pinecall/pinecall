"""A person alone in a room is offered a worker; one an agent joined, or that ended, is let go."""

from livekit.protocol.agent_dispatch import AgentDispatch
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.webhook import WebhookEvent

from pinecall_runtime.enums import Env
from pinecall_runtime.fleet.service import rooms
from pinecall_runtime.fleet.service.offers import Offering
from pinecall_runtime.wire.dispatch import Dispatch

JOINED = "participant_joined"
LEFT = "participant_left"
FINISHED = "room_finished"


# The SIP rule and a visitor's token dispatch to the fleet by its plain name, which no worker holds
# (each registers as <fleet>/<worker>), so LiveKit starts no job: the dispatch stays on the room
# with the call's metadata, and the gateway reads it there. A caller joining sends the first; a
# worker handing its caller to another fleet dispatches there and leaves, which sends the other.
# The newest dispatch decides: a call that ended, or a supervisor joining a live call, has the
# gateway's own dispatch, to a worker by its name, as the newest, and is left alone. The room is
# asked of the LiveKit of the env that sent the event. A ring production handed to the sandbox
# over SIP is made the developer's by what its leg, the person joining, carries.
async def offer_arrival(offering: Offering, env: Env, event: WebhookEvent) -> str | None:
    """Offer the room a person is alone in to a worker; the name it went to, or None."""
    if not _a_person_may_be_alone(event):
        return None
    room = event.room.name
    server = offering.servers[env]
    if not await rooms.left_alone(server, room):
        return None
    newest = _newest(await server.agent_dispatch.list_dispatch(room))
    if newest is None or not names_a_fleet(newest.agent_name) or newest.state.jobs:
        return None
    dispatch = Dispatch.parse(newest.metadata).handed_in(event.participant.attributes)
    return await offering.offer(room, newest.agent_name, dispatch)


# A dispatch creates the room it names again if it is gone: a room offered after its caller hung
# up, or after the worker sent to say the sentence closed it, would be a job on an empty room.
async def forget_settled(offering: Offering, event: WebhookEvent) -> None:
    """Let a room go that an agent joined or that ended: nothing is left to offer it to."""
    agent_in = event.event == JOINED and event.participant.kind == ParticipantInfo.Kind.AGENT
    if event.room.name and (agent_in or event.event == FINISHED):
        await offering.forget(event.room.name)


# LiveKit's own automatic dispatch names no agent (""): it goes to the workers registered with no
# name, which none of ours is, and a room kept under it would be a room of no fleet (seen
# 2026-10-21, on a simulated call's room once its agent left). A worker's name has the slash.
def names_a_fleet(agent_name: str) -> bool:
    """Whether a dispatch's agent name is a fleet's plain name, and so a call to place."""
    return agent_name != "" and "/" not in agent_name


def _a_person_may_be_alone(event: WebhookEvent) -> bool:
    agent = event.participant.kind == ParticipantInfo.Kind.AGENT
    joined = event.event == JOINED and not agent
    return bool(event.room.name) and (joined or (event.event == LEFT and agent))


def _newest(dispatches: list[AgentDispatch]) -> AgentDispatch | None:
    return max(dispatches, key=lambda dispatch: dispatch.state.created_at, default=None)
