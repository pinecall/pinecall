"""LiveKit's own endpoint: every room event of the box, signed with the box's key."""

from fastapi import APIRouter

from runtime.enums import Env
from runtime.live.auth import EventsEnv, SignedRoomEvent, TheLive
from runtime.live.service import stranded
from runtime.postgres import Session

router = APIRouter()


# All but an agent lost mid-call are answered and let be (`stranded.hear_room_event` says the order).
@router.post("/v1/livekit/webhook", status_code=204)
async def receive_room_event(
    event: SignedRoomEvent, live: TheLive, session: Session, env: EventsEnv = Env.production
) -> None:
    """A room event LiveKit signed: a caller alone is offered a worker; an agent lost, told."""
    await stranded.hear_room_event(session, live, env, event)
