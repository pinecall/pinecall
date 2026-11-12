"""A token the gateway signs, as it is read back: the attributes its seat carries, its claims, the key id of our own."""

from pydantic import ConfigDict, Field

from runtime.enums import Env
from runtime.wire.base import WireModel
from runtime.wire.parts import Projection
from runtime.wire.room import SCOPE_ATTRIBUTE, RoomScope

# A room token's scope rides the seat as a LiveKit attribute (`wire.room.SCOPE_ATTRIBUTE`), so the worker
# reads it without a lookup; these ride beside it: who a supervisor is, what a reading token reads
# through, and the code, the agent and the env a code's token asks after.
SUBJECT_ATTRIBUTE = "pinecall.subject"
NAME_ATTRIBUTE = "pinecall.name"
PROJECTION_ATTRIBUTE = "pinecall.projection"
CODE_ATTRIBUTE = "pinecall.code"
AGENT_ATTRIBUTE = "pinecall.agent"
ENV_ATTRIBUTE = "pinecall.env"

# The header of a token the gateway signs with its own key; a LiveKit token names no key id.
OUR_KEY_ID = "pinecall"


class _Read(WireModel):
    # A token carries what LiveKit and the libraries put beside ours: read past, never refused.
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class TokenRoom(_Read):
    """The room a token names, as LiveKit's grant spells it."""

    room: str = ""


class TokenAttributes(_Read):
    """What a token's seat carries of ours, by the names a worker reads them under."""

    scope: RoomScope = Field(alias=SCOPE_ATTRIBUTE)
    subject: str | None = Field(None, alias=SUBJECT_ATTRIBUTE)
    name: str | None = Field(None, alias=NAME_ATTRIBUTE)
    projection: Projection | None = Field(None, alias=PROJECTION_ATTRIBUTE)
    code: str | None = Field(None, alias=CODE_ATTRIBUTE)
    agent: str | None = Field(None, alias=AGENT_ATTRIBUTE)
    env: Env | None = Field(None, alias=ENV_ATTRIBUTE)


class TokenClaims(_Read):
    """The claims of a token of one call: until when, who, which room, and what its seat carries."""

    exp: float
    sub: str | None = None
    video: TokenRoom = TokenRoom()
    attributes: TokenAttributes


class ResumeClaims(_Read):
    """The claims of a token that carries one call on."""

    exp: float
    resumes: str
