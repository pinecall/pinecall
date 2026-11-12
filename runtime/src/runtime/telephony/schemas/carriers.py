"""The bodies of the carriers endpoints: an account brought and listed, the catalog, and calling out through one."""

from ipaddress import ip_network
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from runtime.compliance.schemas import DialGuards
from runtime.kit.schemas import Row, Schema
from runtime.wire.worker import Transport

A_SID = r"^(AC|SK)[0-9a-fA-F]{32}$"
AN_ACCOUNT_SID = r"^AC[0-9a-fA-F]{32}$"


# ── the accounts an org brings ──


class TwilioAccount(Schema):
    """A Twilio account: its SID, and an API key SID with its secret (or the SID and auth token)."""

    kind: Literal["twilio"] = "twilio"
    account_sid: Annotated[str, Field(pattern=AN_ACCOUNT_SID)]
    user: Annotated[str, Field(pattern=A_SID)]
    secret: Annotated[str, Field(min_length=1)]
    label: str = ""


class SipPeer(Schema):
    """A PBX or carrier that speaks SIP: where it calls from, its pair, where it is dialled."""

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


class WhatsappAccount(Schema):
    """A WhatsApp number at Meta: the id replies are sent from, and the org's token."""

    kind: Literal["whatsapp"] = "whatsapp"
    phone_number_id: Annotated[str, Field(min_length=1)]
    access_token: Annotated[str, Field(min_length=1)]
    label: str = ""


# A new kind of account is a line here, a module of its own, and a line of the registry.
type Account = Annotated[TwilioAccount | SipPeer | WhatsappAccount, Field(discriminator="kind")]


class NetworkRow(Row):
    """A network a peer of the org calls from, and whether the box's operator admitted it."""

    network: str
    state: str


class CarrierRow(Row):
    """GET /v1/carrier: one account of the org, named, never its secret."""

    kind: str
    account: str
    label: str = ""
    # A SIP peer's networks, each waiting, approved or refused; none for an account with an API.
    networks: list[NetworkRow] = Field(default_factory=list[NetworkRow])


class CarrierList(Row):
    """GET /v1/carriers: every account of the org, oldest first."""

    carriers: list[CarrierRow]


# ── the catalog ──


class CatalogCarrier(Row):
    """A carrier the org may bring numbers through: automatic (its API) or guided (SIP terms)."""

    kind: str
    name: str
    how: Literal["automatic", "guided"]
    networks: list[str]


class CarrierCatalog(Row):
    """GET /v1/carriers/catalog: the carriers admitted, whether numbers are sold, where a carrier sends a call."""

    carriers: list[CatalogCarrier]
    sells: bool
    # The name a carrier or a PBX sends the key's environment's calls to, on port 5060; null where there is none.
    sip_domain: str | None = None


# ── calling out ──


class OutboundStatus(Row):
    """GET /v1/carrier/outbound, the answer."""

    ready: bool
    kind: str | None
    from_numbers: list[str]
    steps_missing: list[str]
    guards: DialGuards


class ProvisionOutboundResponse(Row):
    """POST /v1/carrier/outbound, the answer: the plan, and whether it was carried out."""

    steps: list[str]
    dry_run: bool
    ready: bool
    trunk: str | None = None
    address: str | None = None
