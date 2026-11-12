"""The bodies of the operator's telephony: the numbers account, every number, the catalog and the fence, networks."""

from typing import Any, Literal, Self, override

from pydantic import Field

from runtime.enums import Channel, Env
from runtime.kit.schemas import Epoch, Row, Schema


class NumbersAccount(Row):
    """GET /v1/ops/numbers-account: the Twilio account the box buys numbers on; never its secret."""

    account_sid: str
    label: str


# `bought` on the box's account; `twilio`, `sip`, `whatsapp` the org's account it was imported
# from; `imported` from an account since forgotten; `hooked` pointed at the box by the org itself;
# `typed` a row the box's operator wrote.
type NumberCameIn = Literal["bought", "twilio", "sip", "whatsapp", "imported", "hooked", "typed"]


class BoxNumber(Row):
    """GET /v1/ops/numbers: a number the box answers at, how it came, and who picks it up."""

    number: str
    channel: Channel
    org: str
    env: Env
    agent: str
    came_in: NumberCameIn
    # A process holds the agent in the org and env now: a call to the number is answered.
    running: bool
    # The catalog carrier a number the org hooked comes through, when it named one.
    via: str | None = None
    # False for a number the org hooked that waits for the operator: no call to it opens.
    approved: bool = True


class BoxCarrier(Row):
    """A carrier of the box's catalog: its published networks, and whether it is admitted."""

    kind: str
    name: str
    # The box drives its API (lists, points, buys numbers); the others are SIP terms alone.
    control: bool
    networks: list[str]
    source: str
    read_on: str
    admitted: bool
    # The platform's own carrier: admitted always, its networks in the cloud firewall.
    fixed: bool
    # The numbers of every org that reach the box through it.
    numbers: int

    # The value is the catalog's carrier and how the box stands with it; the answer is one flat row.
    @classmethod
    @override
    def of(cls, row: Any, /) -> Self:
        """The row a carrier of the catalog answers as, with how the box stands with it."""
        known = row.carrier
        return cls(
            kind=known.kind,
            name=known.name,
            control=known.has_api,
            networks=list(known.networks),
            source=known.source,
            read_on=known.read_on.isoformat(),
            admitted=row.admitted,
            fixed=row.fixed,
            numbers=row.numbers,
        )


class FenceOpening(Row):
    """A network 5060 opens to beyond Twilio's, and why: a carrier's kind, or an org's ask."""

    network: str
    reason: str


class BoxFence(Row):
    """What the fence opens to beyond Twilio's, and every network the cloud's firewall admits."""

    openings: list[FenceOpening]
    # Twilio's first, then each opening: Terraform's `sip_sources` (`fence export`).
    networks: list[str]


class BoxCarriers(Row):
    """GET /v1/ops/carriers: the catalog, each carrier admitted or not, and the fence."""

    carriers: list[BoxCarrier]
    fence: BoxFence

    @classmethod
    @override
    def of(cls, row: Any, /) -> Self:
        """The answer the catalog and the fence read as."""
        return cls(carriers=[BoxCarrier.of(carrier) for carrier in row.carriers], fence=BoxFence.of(row))


class AdmitCarrierRequest(Schema):
    """PUT /v1/ops/carriers/{kind}: whether orgs may bring numbers through the carrier."""

    admitted: bool


class RepointRequest(Schema):
    """POST /v1/ops/sip/repoint: the names each env was reached at before, sent on from."""

    former: dict[Env, list[str]] = Field(default_factory=dict[Env, list[str]])


# The env is `world` on the wire: the CLI of the release before 2026-11 reads that word.
class RepointedTrunk(Row):
    """POST /v1/ops/sip/repoint: a trunk of an account sent on from an env's name to its SIP's."""

    account: str
    trunk: str
    world: Env = Field(validation_alias="env")
    was: str
    now: str


type NetworkStateName = Literal["waiting", "approved", "refused"]


class CarrierNetworkRow(Row):
    """A network an org asked 5060 to open to: who, for what, and the operator's answer."""

    id: int
    org: str
    source: str
    network: str
    state: str
    asked_at: Epoch
    decided_by: str | None
    decided_at: Epoch | None

    # The value is the row and its org's slug; the answer names the org by the slug.
    @classmethod
    @override
    def of(cls, row: Any, /) -> Self:
        """The row a network asked for answers as, its org by its slug."""
        asked = row.row
        return cls(
            id=asked.id,
            org=row.org,
            source=asked.source,
            network=str(asked.network),
            state=asked.state,
            asked_at=asked.asked_at,
            decided_by=asked.decided_by,
            decided_at=asked.decided_at,
        )


class BoxTestLine(Schema):
    """GET · PUT /v1/ops/test-line: the box's sandbox number a person calls to reach their own agent, or null."""

    number: str | None = None


class RouteRequest(Schema):
    """POST /v1/ops/routes: which org's agent answers a number, on a channel, in an env."""

    org: str
    number: str
    agent: str
    channel: Channel
    env: Env = Env.production
