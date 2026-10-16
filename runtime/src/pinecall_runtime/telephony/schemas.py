"""The bodies of the telephony endpoints: accounts, numbers, dialling out, a leg, consent, the operator's."""

from ipaddress import ip_network
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pinecall_runtime.billing.schemas import OrgQuotas
from pinecall_runtime.enums import Channel, ConsentKind, Env, RouteOrigin
from pinecall_runtime.kit.schemas import Schema
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.parts import Projection

type Transport = Literal["auto", "udp", "tcp", "tls"]
type StepState = Literal["ok", "waiting", "broken"]

A_SID = r"^(AC|SK)[0-9a-fA-F]{32}$"
AN_ACCOUNT_SID = r"^AC[0-9a-fA-F]{32}$"


# ── the accounts an org brings, as they are sealed and as they are sent ──


class TwilioAccount(BaseModel):
    """A Twilio account: its SID, and an API key SID with its secret (or the SID and auth token)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["twilio"] = "twilio"
    account_sid: Annotated[str, Field(pattern=AN_ACCOUNT_SID)]
    user: Annotated[str, Field(pattern=A_SID)]
    secret: Annotated[str, Field(min_length=1)]
    label: str = ""


class SipPeer(BaseModel):
    """A PBX or carrier that speaks SIP: where it calls from, its pair, where it is dialled."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sip"] = "sip"
    username: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]
    addresses: Annotated[list[str], Field(min_length=1)]
    outbound_host: str | None = None
    outbound_transport: Transport = "auto"
    outbound_username: str | None = None
    outbound_password: str | None = None
    label: str = ""

    @field_validator("addresses")
    @classmethod
    def _networks(cls, addresses: list[str]) -> list[str]:
        for address in addresses:
            try:
                ip_network(address, strict=False)
            except ValueError:
                raise ValueError(f"{address} is not a network a peer calls from, like 203.0.113.0/24") from None
        return addresses

    # One account in both directions is what most carriers sell: unsaid, the inbound pair dials.
    @model_validator(mode="after")
    def _a_whole_pair(self) -> Self:
        if self.outbound_username and not self.outbound_password:
            raise ValueError("outbound_username is given without outbound_password: a peer is dialled with both")
        return self


class WhatsappAccount(BaseModel):
    """A WhatsApp number at Meta: the id replies are sent from, and the org's token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["whatsapp"] = "whatsapp"
    phone_number_id: Annotated[str, Field(min_length=1)]
    access_token: Annotated[str, Field(min_length=1)]
    label: str = ""


type Account = Annotated[TwilioAccount | SipPeer | WhatsappAccount, Field(discriminator="kind")]


class Termination(BaseModel):
    """How the box dials out through a Twilio account: the host and the credential it made."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str
    username: str
    password: str


class SealedCarrier(BaseModel):
    """What a carrier's row seals: the account, and its termination when provisioning made one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account: Account
    outbound: Termination | None = None


# ── dialling out ──


class DialResponse(WireModel):
    """POST /v1/agents/{slug}/dial, the answer."""

    call: str
    agent: str
    to: str
    from_: str = Field(alias="from")
    env: Env
    log_token: str


class PutDialGuards(Schema):
    """PUT /v1/ops/orgs/{named}/dialling: the guards whole; one left out is the default."""

    dial_anywhere: bool | None = None
    per_minute: int | None = None
    per_day: int | None = None
    max_duration_s: int | None = None


class OrgHolding(WireModel):
    """What the org holds right now, across both envs, against its stock quotas."""

    memory_facts: int
    knowledge_chunks: int
    numbers: int
    seats: int


class DialGuards(WireModel):
    """GET /v1/carrier/outbound, the guards: what this org may dial and how often."""

    dial_anywhere: bool
    per_minute: int
    per_day: int
    max_duration_s: int


class OutboundStatus(WireModel):
    """GET /v1/carrier/outbound, the answer."""

    ready: bool
    kind: str | None
    from_numbers: list[str]
    steps_missing: list[str]
    guards: DialGuards


class ProvisionOutboundResponse(WireModel):
    """POST /v1/carrier/outbound, the answer: the plan, and whether it was carried out."""

    steps: list[str]
    dry_run: bool
    ready: bool
    trunk: str | None = None
    address: str | None = None


class Consent(WireModel):
    """The consent a call runs on: express or written, where it came from, the words, a proof."""

    kind: Literal["express", "written"]
    source: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=500)


class DialRequest(WireModel):
    """POST /v1/agents/{slug}/dial: the far end, the org's number it is shown, the consent."""

    to: str
    from_: str | None = Field(None, alias="from")
    consent: Consent | None = None
    # What the log token handed back reads the call through.
    log: Projection = "tenant"


class LegTrunk(WireModel):
    """How the worker dials a leg: the host, its transport, the pair, the number shown."""

    hostname: str
    transport: Transport
    username: str
    password: str
    shown: str


class LegTrunkResponse(WireModel):
    """GET /v1/agents/{slug}/outbound-trunk: the leg's trunk, inline, after the guards."""

    trunk: LegTrunk


class RingHandoff(WireModel):
    """Where a production ring goes: a developer's scope and its fleet, or nowhere (null)."""

    holder: str | None = None
    fleet: str | None = None
    # Where the sandbox has a LiveKit of its own: the ring is dialled to its SIP through this.
    trunk: LegTrunk | None = None


class ColdTransferQuery(Schema):
    """A worker asking whether the caller may be sent on: to whom, from which call."""

    to: str
    call: str


class LegTrunkQuery(Schema):
    """A worker asking how to dial a leg of a call: to whom, from which of the org's numbers."""

    to: str
    call: str
    shown: str | None = Field(None, alias="from")


# ── numbers and the accounts they live in ──


class NetworkRow(WireModel):
    """A network a peer of the org calls from, and whether the box's operator admitted it."""

    network: str
    state: str


class CarrierRow(WireModel):
    """GET /v1/carrier: one account of the org, named, never its secret."""

    kind: str
    account: str
    label: str = ""
    # A SIP peer's networks, each waiting, approved or refused; none for an account with an API.
    networks: list[NetworkRow] = Field(default_factory=list[NetworkRow])


class CatalogCarrier(WireModel):
    """A carrier the org may bring numbers through: automatic (its API) or guided (SIP terms)."""

    kind: str
    name: str
    how: Literal["automatic", "guided"]
    networks: list[str]


class CarrierCatalog(WireModel):
    """GET /v1/carriers/catalog: the carriers this box admits, and whether it sells numbers."""

    carriers: list[CatalogCarrier]
    sells: bool


class CarrierList(WireModel):
    """GET /v1/carriers: every account of the org, oldest first."""

    carriers: list[CarrierRow]


class OwnedNumberRow(WireModel):
    """A number an account owns, and whether this env imported it."""

    number: str
    name: str
    imported: bool
    account: str


class AvailableNumbers(WireModel):
    """GET /v1/numbers/available: what the org's Twilio accounts own; a peer lists none."""

    kind: str
    numbers: list[OwnedNumberRow]


class RouteBody(WireModel):
    """A route as the numbers endpoints send it."""

    org: str
    agent: str
    channel: Channel
    number: str | None = None
    env: Env
    managed: bool = False


class NumberRow(WireModel):
    """GET /v1/numbers, one row: a number of the org, the agent it reaches, how it was written."""

    route: RouteBody
    origin: RouteOrigin
    # What a call to it does now, read off the tables (GET /v1/numbers/{number}/path says why).
    rings: StepState = "ok"
    # When a call to it last reached the box; null when none ever did.
    last_call_at: float | None = None
    # The carrier of the box's catalog a hooked number comes through.
    via: str | None = None
    # The org's account the number lives in (GET /v1/carriers names it); null for one with none.
    account: str | None = None


class PathStep(WireModel):
    """One step of a call's way to its agent, what it does now, and what would make it work."""

    step: Literal["carrier", "fence", "world", "agent"]
    state: StepState
    says: str
    fix: str | None = None


class NumberPath(WireModel):
    """GET /v1/numbers/{number}/path: the four steps, the worst of them, and the last call."""

    number: str
    steps: list[PathStep]
    rings: StepState
    last_call_at: float | None


class ImportNumberResponse(WireModel):
    """POST /v1/numbers and /v1/numbers/buy: the route, one sentence a step, whether it ran."""

    route: RouteBody
    steps: list[str]
    dry_run: bool


class ImportNumberRequest(WireModel):
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


class BuyNumberRequest(WireModel):
    """POST /v1/numbers/buy: a number wanted from the box's own account."""

    # Two letters and digits alone: both ride a URL path the box signs with its own account.
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    area_code: str | None = Field(default=None, pattern=r"^[0-9]{1,6}$")
    agent: str
    channel: Channel = Channel.phone


class MoveNumberRequest(WireModel):
    """PUT /v1/numbers/{number}/env: the env the number answers in from now on."""

    env: Env


# ── consent and the do-not-call list ──


class ConsentRow(WireModel):
    """One fact about a number: a consent or an opt-out, by whom, from what, on which call."""

    kind: ConsentKind
    source: str
    text: str | None
    evidence: str | None
    given_by: str
    call: str | None
    given_at: float


class ConsentHistory(WireModel):
    """GET /v1/org/consents/{number}: what stands for the number, and every row, newest first."""

    number: str
    standing: Literal["consented", "opted_out", "unknown"]
    rows: list[ConsentRow]


class OptedOut(WireModel):
    """A number on the org's do-not-call list: since when, from what, and who put it there."""

    number: str
    since: float
    source: str
    given_by: str


class DoNotCall(WireModel):
    """GET /v1/org/dnc: the numbers whose newest row is an opt-out, newest first, a page."""

    numbers: list[OptedOut]
    next: str | None


class DoNotCallImport(WireModel):
    """POST /v1/org/dnc: numbers the org's own list or a Registry scrub says not to call."""

    numbers: list[str] = Field(min_length=1, max_length=10000)
    source: str = Field(min_length=1, max_length=200)


class DoNotCallImported(WireModel):
    """POST /v1/org/dnc, the answer: how many numbers joined the list, and the ones refused."""

    added: int
    refused: list[str]


class RecordConsent(WireModel):
    """POST /v1/org/consents: one fact about a number, a consent given or an opt-out."""

    number: str
    kind: ConsentKind
    source: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=500)


# ── the operator's ──


class NumbersAccount(WireModel):
    """GET /v1/ops/numbers-account: the Twilio account the box buys numbers on; never its secret."""

    account_sid: str
    label: str


# `bought` on the box's account; `twilio`, `sip`, `whatsapp` the org's account it was imported
# from; `imported` from an account since forgotten; `hooked` pointed at the box by the org itself;
# `typed` a row the box's operator wrote.
type NumberCameIn = Literal["bought", "twilio", "sip", "whatsapp", "imported", "hooked", "typed"]


class BoxNumber(WireModel):
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


class BoxCarrier(WireModel):
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


class FenceOpening(WireModel):
    """A network 5060 opens to beyond Twilio's, and why: a carrier's kind, or an org's ask."""

    network: str
    reason: str


class BoxFence(WireModel):
    """What the fence opens to beyond Twilio's, and every network the cloud's firewall admits."""

    openings: list[FenceOpening]
    # Twilio's first, then each opening: Terraform's `sip_sources` (`fence export`).
    networks: list[str]


class BoxCarriers(WireModel):
    """GET /v1/ops/carriers: the catalog, each carrier admitted or not, and the fence."""

    carriers: list[BoxCarrier]
    fence: BoxFence


class RepointRequest(WireModel):
    """POST /v1/ops/sip/repoint: the names each env was reached at before, sent on from."""

    former: dict[Env, list[str]] = Field(default_factory=dict[Env, list[str]])


class RepointedTrunk(WireModel):
    """POST /v1/ops/sip/repoint: a trunk of an account sent on from an env's name to its SIP's."""

    account: str
    trunk: str
    world: Env
    was: str
    now: str


class AdmitCarrierRequest(WireModel):
    """PUT /v1/ops/carriers/{kind}: whether orgs may bring numbers through the carrier."""

    admitted: bool


class CarrierNetworkRow(WireModel):
    """A network an org asked 5060 to open to: who, for what, and the operator's answer."""

    id: int
    org: str
    source: str
    network: str
    state: str
    asked_at: float
    decided_by: str | None
    decided_at: float | None


class TracebackCall(WireModel):
    """One phone call with the number: whose, which way, when, how it ended, whether erased."""

    call: str
    org: str | None
    env: str | None
    direction: str | None
    from_number: str | None
    to_number: str | None
    started_at: float | None
    ended_at: float | None
    end_reason: str | None
    # The call's log is gone and only its detail record is left.
    erased: bool


class TracebackDial(WireModel):
    """One dial to the number: whose, the call it placed, the number shown, who asked, the guard."""

    org: str
    env: str
    agent: str
    call: str | None
    shown: str | None
    asked_by: str
    refused: str | None
    at: float


class Traceback(WireModel):
    """GET /v1/ops/traceback: what the box keeps of one number since a day, oldest first."""

    number: str
    since: float
    calls: list[TracebackCall]
    dials: list[TracebackDial]


class OrgProfile(WireModel):
    """GET /v1/ops/orgs/{named}: one org, its quotas per env, its dial guards, what it holds."""

    id: str
    slug: str
    name: str
    quotas: dict[Env, OrgQuotas]
    dialling: DialGuards
    holding: OrgHolding
