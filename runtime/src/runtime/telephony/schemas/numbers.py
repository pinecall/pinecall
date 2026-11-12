"""The bodies of the numbers endpoints: a number listed, its path, one imported, bought or moved, what is owned."""

from typing import Literal

from pydantic import Field

from runtime.enums import Channel, Env, RouteOrigin
from runtime.kit.schemas import Epoch, Row, Schema

type StepState = Literal["ok", "waiting", "broken"]


class RouteBody(Row):
    """A route as the numbers endpoints send it."""

    org: str
    agent: str
    channel: Channel
    number: str | None = None
    env: Env
    managed: bool = False


class NumberRow(Row):
    """GET /v1/numbers, one row: a number of the org, the agent it reaches, how it was written."""

    route: RouteBody
    origin: RouteOrigin
    # What a call to it does now, read off the tables (GET /v1/numbers/{number}/path says why).
    rings: StepState = "ok"
    # When a call to it last reached the box; null when none ever did.
    last_call_at: Epoch | None = None
    # The carrier of the box's catalog a hooked number comes through.
    via: str | None = None
    # The org's account the number lives in (GET /v1/carriers names it); null for one with none.
    account: str | None = None


class PathStep(Row):
    """One step of a call's way to its agent, what it does now, and what would make it work."""

    step: Literal["carrier", "fence", "world", "agent"]
    state: StepState
    says: str
    fix: str | None = None


class NumberPath(Row):
    """GET /v1/numbers/{number}/path: the four steps, the worst of them, and the last call."""

    number: str
    steps: list[PathStep]
    rings: StepState
    last_call_at: Epoch | None


class ImportNumberRequest(Schema):
    """POST /v1/numbers: a number of one of the org's accounts, or one the org hooks itself."""

    number: str
    agent: str
    channel: Channel = Channel.phone
    account: str | None = None
    hooked: bool = False
    networks: list[str] = Field(default_factory=list[str])
    # A hooked number's carrier from the box's catalog (GET /v1/carriers/catalog).
    via: str | None = None
    move: bool = False


class BuyNumberRequest(Schema):
    """POST /v1/numbers/buy: a number wanted from the box's own account."""

    # Two letters and digits alone: both ride a URL path the box signs with its own account.
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    area_code: str | None = Field(default=None, pattern=r"^[0-9]{1,6}$")
    agent: str
    channel: Channel = Channel.phone


class ImportNumberResponse(Row):
    """POST /v1/numbers and /v1/numbers/buy: the route, one sentence a step, whether it ran."""

    route: RouteBody
    steps: list[str]
    dry_run: bool


class MoveNumberRequest(Schema):
    """PUT /v1/numbers/{number}/env: the env the number answers in from now on."""

    env: Env


class OwnedNumberRow(Row):
    """A number an account owns: whether this env imported it, or another org of this box holds it."""

    number: str
    name: str
    imported: bool
    held_elsewhere: bool
    account: str


class AvailableNumbers(Row):
    """GET /v1/numbers/available: what the org's accounts own; a peer lists none."""

    kind: str
    numbers: list[OwnedNumberRow]
