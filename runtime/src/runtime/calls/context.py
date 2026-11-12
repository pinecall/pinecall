"""What a call is: its id, direction, who is calling, the route it came in by, its day, and the name its log goes by."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

from runtime.enums import Channel, Direction, Env
from runtime.exceptions import ValidationError
from runtime.kit.text import Json, is_e164

# Prefix of call ids minted here (`call_` + 32 hex); phone calls are named by the media plane.
A_CALL = "call_"

# An agent's own log is named "@<agent>", a name the CHECK on call_log keeps from any call id.
AGENT_LOG_PREFIX = "@"


def new_call_id() -> str:
    """A call id nobody holds yet."""
    return f"{A_CALL}{uuid4().hex}"


# Every fact of a call is an entry of its log, and what is of no call (an agent registered, an
# error, a code) is an entry of its agent's own log: one name for both, read by the log's tables,
# its channels on the signal and the endpoint that follows an agent.
def log_name(call: str | None, agent: str) -> str:
    """The name a log goes by: the call id, or the agent's with the prefix."""
    return f"{AGENT_LOG_PREFIX}{agent}" if call is None else call


@dataclass(frozen=True, slots=True)
class Contact:
    """What is known about the caller; a web visitor may be anonymous."""

    id: str | None = None
    phone: str | None = None
    name: str | None = None
    email: str | None = None
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class Route:
    """Which agent answers on a channel and number, and which org owns it."""

    org: str
    agent: str
    channel: Channel
    number: str | None = None
    label: str | None = None
    # A number belongs to one env; the registry refuses it in the other.
    env: Env = Env.production
    # Bought on the box's carrier account, so it counts against the `numbers` quota; numbers
    # imported from the tenant's own account do not.
    managed: bool = False

    def __post_init__(self) -> None:
        if not self.org or not self.agent:
            raise ValidationError("a route names the org that owns it and the agent that answers")
        if self.channel.has_a_number:
            if self.number is None or not is_e164(self.number):
                raise ValidationError(f"a {self.channel} route answers at a number in E.164 form, not {self.number!r}")
        elif self.number is not None:
            raise ValidationError(f"the {self.channel} widget answers at no number")


# Immutable: whatever changes during a call is recorded in the log. A session reads it through the
# Protocols it declares (`session/call.py`: `CallContext`, `Route`, `Contact`), which these satisfy.
@dataclass(frozen=True, slots=True)
class CallContext:
    """A call as the worker and the gateway see it when it starts."""

    call: str
    channel: Channel
    direction: Direction
    caller: str
    route: Route
    today: date
    # The day a golden pinned, when one did: `today` is then that day, and the app is told it.
    pinned_day: date | None = None
    contact: Contact | None = None
    metadata: Mapping[str, Json] = field(default_factory=dict[str, Json])
    # Eval run that opened the call; None for a real caller.
    run: str | None = None
    # Simulated caller's name, and what it expects frozen at call start so judging ignores later
    # edits.
    persona: str | None = None
    expects: tuple[str, ...] = ()
    # Sandbox developer the call belongs to; None for the org itself.
    holder: str | None = None
    # The state the call opens in, when a golden, a persona or `?state=` asked for one.
    state: Mapping[str, Json] = field(default_factory=dict[str, Json])
    # The ended call this one carries on: the agent opens on its turns, and greets no one.
    continues: str | None = None

    def __post_init__(self) -> None:
        if not self.call:
            raise ValidationError("a call context names its call")
        if not self.caller:
            raise ValidationError("a call has a calling side: a number, or the visitor id")
        if self.route.channel != self.channel:
            raise ValidationError(f"a {self.channel} call cannot come through a {self.route.channel} route")

    @property
    def env(self) -> Env:
        """The env of the call's route."""
        return self.route.env

    # The app's contact id, else the number, so phone and WhatsApp calls share one contact.
    @property
    def remembered_as(self) -> str | None:
        """The memory key for the caller, or None when the caller is anonymous."""
        if self.contact is not None and self.contact.id:
            return self.contact.id
        return self.caller if self.channel.has_a_number else None
