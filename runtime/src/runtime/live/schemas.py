"""The bodies of the live side's endpoints, a family after another: tokens, codes, seats, verbs, a chat, apps, lines."""

from typing import Literal

from pydantic import ConfigDict, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from runtime.calls.schemas import TokenQuery
from runtime.enums import Channel, Env
from runtime.exceptions import ValidationError
from runtime.kit.schemas import Row, Schema
from runtime.kit.text import Json, JsonObject
from runtime.wire.parts import Projection

# ── tokens ──


class MintTokenRequest(Schema):
    """livekit's token request body, and ours beside it."""

    agent: str | None = None
    scope: str = "talk"
    # An opaque contact id; never a number or a name.
    contact: str | None = None
    # Reaches the worker inside the signed dispatch: the browser reads it, never changes it.
    metadata: JsonObject = Field(default_factory=dict[str, Json])
    # A test room's own voice and models, `stt`, `llm`, `tts`, `tts_model`, `voice`, `language` and
    # `temperature`, over the agent's settings for this call alone; the sandbox's, and never kept. On
    # the wire it is `tuning`, the word every SDK sends.
    test_values: JsonObject | None = Field(default=None, alias="tuning")
    ttl_s: int | None = None
    log: Projection = "public"
    participant_identity: str | None = None
    participant_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    room_config: JsonObject | None = None
    # An earlier answer's resume_token: back into that call while it waits, else one carrying it on.
    resume: str | None = None
    # Declared so they are refused with the reason instead of an unknown key.
    room_name: str | None = None
    participant_name: str | None = None
    participant_metadata: str | None = None


class MintTokenResponse(Row):
    """livekit's token response, the call it opens and a token that reads its log."""

    server_url: str
    participant_token: str
    call: str
    log_token: str
    # What the browser keeps to carry this conversation on later: `resume` in a mint.
    resume_token: str


# ── codes ──


class IssueCodeRequest(Schema):
    """Four digits a caller keys to tie their call to a page."""

    agent: str
    ttl_s: int = Field(default=600, ge=60, le=1800)
    log: Projection = "public"


class IssueCodeResponse(Row):
    """A code issued: the digits, the number to call, and the token its page polls with."""

    code: str
    number: str
    expires_at: float
    code_token: str


class CodeStatus(Row):
    """How a code stands; claimed, it names the call and a token that reads it."""

    code: str
    status: Literal["waiting", "claimed", "expired"]
    expires_at: float
    call: str | None
    log_token: str | None


class CodeQuery(TokenQuery):
    """Whether a page's ask waits for its code to be keyed."""

    wait: bool = False


# ── seats ──


class SeatResponse(Row):
    """A seat in a live call: the server, the token, and who it says the person is."""

    server_url: str
    participant_token: str
    call: str
    identity: str
    org: str
    subject: str | None
    name: str | None


# ── verbs ──


class VerbResponse(Row):
    """A supervise verb queued; the call's log says what it did."""

    call: str
    verb: str
    seq: int | None


class HangupResponse(Row):
    """The caller's hang-up heard; the call ends as `caller_hung_up`."""

    call: str


class RestageRequest(Schema):
    """POST /v1/calls/{call}/stages: with `agent`, the call takes that agent's stages from here on, not its own's."""

    agent: str | None = Field(default=None, min_length=1, max_length=120)


class RestageResponse(Row):
    """The call was told to take its stages anew; `stage.changed` on its log says each one that did."""

    call: str


class ThreadMessageRequest(Schema):
    """What a supervisor writes on a contact's open WhatsApp conversation, said as the agent."""

    text: str


class ThreadMessageResponse(Row):
    """A message handed to the conversation's call; its log says when it was sent."""

    contact: str
    call: str


# ── a chat ──

NOT_A_STATE = "?state= is the state the call opens in: a JSON object of the class's fields"
NOT_PLAYED_BY = "?played_by= is who plays the persona this run: a JSON object of llm, tts and voice, each a string"
A_STATE_AT_MOST = 16 * 1024
_A_STATE: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)


class PlayedBy(Schema):
    """Who plays a persona for one run, over the persona's own: its model, its voice's vendor, its voice."""

    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


# Read off the socket's URL by the endpoint, which refuses with these sentences as a close reason: a
# query FastAPI validated would close the socket with its own code and no word a person reads.
class ChatQuery(Schema):
    """What `WS /v1/chat` opens with: the agent, the app, a call taken up, who writes and as whom, the opening state."""

    # A client's own parameters ride the URL beside ours: read past, as they always were.
    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)

    agent: str = ""
    app: str | None = None
    call: str | None = None
    persona: str | None = None
    played_by: str | None = None
    contact: str | None = None
    caller: str | None = None
    state: str | None = None

    def read_state(self) -> JsonObject:
        """The state the call opens in; refused past sixteen kibibytes, or when it is no JSON object."""
        if not self.state:
            return {}
        size = len(self.state.encode())
        if size > A_STATE_AT_MOST:
            raise ValidationError(
                f"?state= is {size} bytes: the state a call opens in is {A_STATE_AT_MOST} bytes at most"
            )
        try:
            return _A_STATE.validate_json(self.state)
        except PydanticValidationError:
            raise ValidationError(NOT_A_STATE) from None

    def read_played_by(self) -> dict[str, str] | None:
        """Who plays the persona this run, as named; None when the query names nobody."""
        if self.played_by is None:
            return None
        try:
            return PlayedBy.model_validate_json(self.played_by).model_dump(exclude_none=True)
        except PydanticValidationError:
            raise ValidationError(NOT_PLAYED_BY) from None


# ── apps, and the agents they hold ──


class ScopeHolder(Row):
    """A scope by its member id and email; both null for the org's own."""

    holder: str | None
    name: str | None


class AgentRow(Row):
    """An agent some socket of the org holds, the channels it answers, whose scope, and what it is."""

    slug: str
    channels: list[Channel]
    holder: ScopeHolder | None = None
    # A class an app of the org holds, or a definition the gateway holds for Studio: the console
    # draws Studio for the second alone, and writes a golden, a persona or a judge for it alone.
    kind: Literal["class", "studio"] = "class"


class AgentList(Row):
    """The org's held agents in the request's env."""

    agents: list[AgentRow]


class AppRow(Row):
    """One connected app socket and what it holds."""

    app: str
    agents: list[str]
    env: Env
    host: str | None
    address: str | None
    sdk: str | None
    holder: ScopeHolder | None
    connected_at: float


class AppList(Row):
    """The app sockets of the org this key may see."""

    apps: list[AppRow]


class StopAppResponse(Row):
    """A stop answered."""

    app: str
    stopped: bool


class KilledAgent(Row):
    """An agent killed: the envs it was held in, and the app sockets that let go of it."""

    agent: str
    envs: list[Env]
    apps: list[str]


class MoveAgentRequest(Schema):
    """PUT /v1/ops/orgs/{named}/agents: the agent to move into this org."""

    agent: str


class AgentMoved(Row):
    """The move: how many logs came, which numbers came, which stayed where they were."""

    agent: str
    org: str
    logs: int
    numbers: list[str]
    stayed: list[str]


# ── the line, and a developer's phone ──


class RingTarget(Row):
    """Whose terminal a ring at the agent lands in, and who else could take it."""

    agent: str
    env: Env
    held: bool
    holding: ScopeHolder | None = None
    yours: bool
    waiting: list[ScopeHolder]
    calling: list[str]


class DeveloperPhone(Schema):
    """The phone a developer calls from, and the agent a call from it reaches (none: the one the org holds)."""

    number: str
    agent: str | None = None


class TestNumber(Row):
    """A production number and the agent it reaches."""

    number: str
    agent: str


class TestNumbers(Row):
    """The person's own phone, the agent it reaches, the box's test line, and the production numbers it can dial."""

    calling: list[str]
    numbers: list[TestNumber]
    agent: str | None = None
    # The box's own sandbox number a call from the phone reaches that agent at; null on a box with none.
    test_line: str | None = None


class ForgottenPhones(Row):
    """The phones a person's scope no longer takes rings from."""

    forgot: list[str]
