"""The room's events: opened, who joined, left and spoke, what they published and sent."""

from typing import Any, Literal

from runtime.enums import Channel
from runtime.wire.base import WireModel
from runtime.wire.parts import ParticipantKind, TrackKind, TrackSource

# What a room token lets its seat do, carried as an attribute of the participant: the gateway signs it
# into the token, the worker reads it off the seat to tell a widget from a supervisor from a caller.
type RoomScope = Literal["talk", "chat", "observe", "supervise", "read", "participate"]
SCOPE_ATTRIBUTE = "pinecall.scope"
# The caller's leg a spoken simulation publishes under, and the `from` a written one carries: what
# tells a simulated caller from a person on call.started, to whichever release reads it.
A_SIMULATED_CALLER = "simulated_caller"
# The scopes that read the log of their own call and no other: a widget's.
READS_ITS_OWN_CALL: frozenset[RoomScope] = frozenset({"talk", "chat", "read", "participate"})


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
