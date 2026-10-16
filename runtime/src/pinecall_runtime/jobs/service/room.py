"""What a job finds in its call's room: the caller's seat, the hold clip it plays, the widget's channel."""

import asyncio
import logging
import os
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path

from livekit import rtc

from pinecall_runtime.accounts.service import tokens
from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Channel
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.session import service as session
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.state import State

logger = logging.getLogger(__name__)

# The talk seat may join after the agent; a session started with nobody seated records nothing.
WAIT_FOR_THE_CALLER_S = 5.0

# Clips are cached by their hash: each is fetched once per box.
HOLD_CACHE = Path(tempfile.gettempdir()) / "pinecall-hold"


# Only the talk seat is the caller: a listener and a supervisor share the room.
async def seat_of(room: rtc.Room, channel: Channel, *, typed: bool) -> str | None:
    """The one participant the session listens to; none on a written call."""
    if typed:
        return None
    if channel is Channel.phone:
        phone_leg = await telephony.caller_leg(room, channel)
        return None if phone_leg is None else phone_leg.identity
    if channel is Channel.web:
        return await _talk_seat(room)
    return None


# The default clip is the box's data, not the wheel's: a box that holds none plays silence.
async def hold_music_for(
    gateway: GatewayClient, agent: str, scope: Scope, played: str, sha256: str | None
) -> session.HoldMusic | None:
    """The org's own clip, from this box's cache or fetched into it; None for the default."""
    if played != "custom" or sha256 is None:
        return None
    cached = HOLD_CACHE / f"{sha256}.ogg"
    if not cached.is_file():
        try:
            audio = await gateway.hold_clip(agent, scope)
        except GatewayUnavailable:
            logger.warning("the hold clip of %s could not be fetched: the call plays none", agent)
            return None
        await asyncio.to_thread(_write_beside, cached, audio)
    return session.HoldMusic(cached)


# Only the gateway numbers a log, so a widget is sent what is read back from it, projected for
# the public the widget's seat is.
def widget_for(
    gateway: GatewayClient, call: session.Call, room: rtc.Room, hang_up: Callable[[], None]
) -> session.Widget:
    """The call's channel to the widgets in its room, watching."""
    name = call.context.call

    async def state(viewer: str) -> tuple[JsonObject, int]:
        data = await gateway.state(name)
        folded = State.model_validate(data["state"])
        return calls.project_state(folded, "public", call.config, viewer), int(str(data["last_seq"]))

    def public(entry: Entry, viewer: str) -> JsonObject | None:
        return calls.project_entry(entry, "public", call.config, viewer)

    reading = session.Reading(
        state=state, since=partial(gateway.since, name), tail=partial(gateway.tail, name), public=public
    )
    widget = session.Widget(call, room, reading)
    widget.when_hung_up(hang_up)
    widget.watch()
    return widget


async def _talk_seat(room: rtc.Room) -> str | None:
    seated = _talker_in(room)
    if seated is not None or not room.isconnected():
        return seated
    joined: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def if_the_caller(seat: rtc.RemoteParticipant) -> None:
        if seat.attributes.get(tokens.SCOPE_ATTRIBUTE) == "talk" and not joined.done():
            joined.set_result(seat.identity)

    room.on("participant_active", if_the_caller)  # pyright: ignore[reportUnknownMemberType]
    try:
        # Asked again after listening: a join between the two reads would be missed.
        seated = _talker_in(room)
        if seated is not None:
            return seated
        async with asyncio.timeout(WAIT_FOR_THE_CALLER_S):
            return await joined
    except TimeoutError:
        return None
    finally:
        room.off("participant_active", if_the_caller)  # pyright: ignore[reportUnknownMemberType]


def _talker_in(room: rtc.Room) -> str | None:
    return next(
        (
            seat.identity
            for seat in room.remote_participants.values()
            if seat.attributes.get(tokens.SCOPE_ATTRIBUTE) == "talk"
        ),
        None,
    )


# Written beside and renamed, so a job reading the cache never reads half a file.
def _write_beside(cached: Path, audio: bytes) -> None:
    cached.parent.mkdir(parents=True, exist_ok=True)
    part = cached.with_suffix(f".{os.getpid()}.part")
    part.write_bytes(audio)
    part.replace(cached)
