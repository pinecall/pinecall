"""The room's events: opened, who joined, left and spoke, what they published and sent."""

from typing import Any

from pinecall_runtime.enums import Channel
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.parts import ParticipantKind, TrackKind, TrackSource


class RoomOpened(WireModel):
    """The LiveKit room exists and the call lives in it; a text session never logs this."""

    name: str
    sid: str
    channel: Channel


class ParticipantJoined(WireModel):
    """Somebody joined the room; the attributes travel verbatim."""

    identity: str
    kind: ParticipantKind
    name: str | None = None
    attributes: dict[str, Any]


class ParticipantLeft(WireModel):
    """Somebody left the room; when it is the caller, call.ended follows."""

    identity: str
    reason: str


class ParticipantSpeaking(WireModel):
    """The room's own voice activity for one participant flipped."""

    identity: str
    speaking: bool


class TrackPublished(WireModel):
    """A participant put a track on the room."""

    identity: str
    kind: TrackKind
    source: TrackSource


class TrackUnpublished(WireModel):
    """A participant's track left the room."""

    identity: str
    kind: TrackKind
    source: TrackSource


class RoomSent(WireModel):
    """The agent pushed a payload to a browser in the room; the payload stays out of the log."""

    topic: str
    to: str | None = None
    bytes: int
