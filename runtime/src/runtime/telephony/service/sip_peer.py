"""A SIP peer of an org, a PBX or a carrier that speaks SIP: where it calls from, its pair, where it is dialled."""

from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import ip_network
from typing import Any, ClassVar, Self, override

import httpx

from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, ValidationError
from runtime.kit.text import a_list
from runtime.telephony.models import CarrierKind
from runtime.telephony.service.carrier import (
    NOT_A_WHATSAPP_ACCOUNT,
    Carrier,
    Outbound,
    Owned,
    SipNames,
    Step,
    read_optional_text,
    read_text,
)
from runtime.telephony.service.fence import Fence, Fenced
from runtime.telephony.service.networks import Standing
from runtime.wire.worker import LegTrunk, Transport

KIND = "sip"
TRANSPORTS: tuple[Transport, ...] = ("auto", "udp", "tcp", "tls")


@dataclass(frozen=True, slots=True)
class SipPeer(Carrier):
    """A PBX or carrier that speaks SIP: the networks it calls from, its digest pair, where it takes calls."""

    kind: ClassVar[CarrierKind] = CarrierKind.sip
    name: ClassVar[str] = "your PBX"
    has_api: ClassVar[bool] = False

    org: str
    username: str
    password: str
    addresses: tuple[str, ...]
    outbound_host: str | None = None
    outbound_transport: Transport = "auto"
    # One account in both directions is what most carriers sell: unsaid, the inbound pair dials.
    outbound_username: str | None = None
    outbound_password: str | None = None
    label: str = ""

    @property
    @override
    def id(self) -> str:
        """The peer's username."""
        return self.username

    @classmethod
    @override
    def read(cls, org: str, account: Mapping[str, object], outbound: Mapping[str, object] | None) -> Self:
        """The peer out of what a row seals or a body brings."""
        addresses = account.get("addresses")
        if not a_list(addresses) or not addresses:
            raise ValueError("addresses is missing")
        for address in addresses:
            ip_network(str(address), strict=False)
        transport = read_optional_text(account, "outbound_transport") or "auto"
        return cls(
            org=org,
            username=read_text(account, "username"),
            password=read_text(account, "password"),
            addresses=tuple(str(address) for address in addresses),
            outbound_host=read_optional_text(account, "outbound_host"),
            outbound_transport=_read_transport(transport),
            outbound_username=read_optional_text(account, "outbound_username"),
            outbound_password=read_optional_text(account, "outbound_password"),
            label=read_optional_text(account, "label") or "",
        )

    # Every field, as the release before 2026-11 wrote it and reads it, refusing one it does not know.
    @override
    def dump(self) -> dict[str, Any]:
        """The peer as its row seals it: the box makes nothing on somebody else's switch, so no termination."""
        account = {
            "kind": KIND,
            "username": self.username,
            "password": self.password,
            "addresses": list(self.addresses),
            "outbound_host": self.outbound_host,
            "outbound_transport": self.outbound_transport,
            "outbound_username": self.outbound_username,
            "outbound_password": self.outbound_password,
            "label": self.label,
        }
        return {"account": account, "outbound": None}

    @override
    def keep_from(self, was: object) -> Self:
        """The peer as brought: the box made nothing on the one before."""
        return self

    @override
    async def verify(self, http: httpx.AsyncClient) -> None:
        """A peer is not asked: nothing answers for it before its first call."""
        return

    @override
    def calling_networks(self) -> tuple[str, ...] | None:
        """The networks the peer says it calls from."""
        return self.addresses

    @override
    def fence(self, number: str, standing: Standing) -> Fenced:
        """The peer's own trunk: its approved networks and its pair; none until one is approved."""
        own = standing.sort(self.addresses)
        if not own.approved:
            return Fenced(None, waiting=own.waiting, refused=own.refused)
        trunk = Fence(
            trunk=f"{self.org}:{self.username}", networks=own.approved, username=self.username, password=self.password
        )
        return Fenced(trunk, waiting=own.waiting, refused=own.refused)

    @override
    def list_missing_to_dial(self) -> list[str]:
        """The host it takes calls at, when it named none."""
        if self.outbound_host:
            return []
        return [
            f"SIP peer {self.id} declared no outbound_host: the networks a peer calls FROM are not an "
            f"address it takes calls AT"
        ]

    @override
    def leg_trunk(self, shown: str) -> LegTrunk:
        """A leg dialled where the peer said, with its outbound pair or the inbound one."""
        if not self.outbound_host:
            raise Conflict(self.list_missing_to_dial()[0])
        return LegTrunk(
            hostname=self.outbound_host,
            transport=self.outbound_transport,
            username=self.outbound_username or self.username,
            password=self.outbound_password or self.password,
            shown=shown,
        )

    # A SIP peer owns what it owns and nobody here can list it: its import takes the number typed.
    @override
    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """None: nobody can list a peer's numbers."""
        return []

    @override
    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """A peer's number answers the phone."""
        if channel is Channel.whatsapp:
            raise ValidationError(NOT_A_WHATSAPP_ACCOUNT)

    @override
    async def survey_hook(
        self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env, *, move: bool
    ) -> list[Step]:
        """Nothing: the org points its own switch at the box."""
        return []

    @override
    async def is_pointed_here(self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env) -> bool | None:
        """None: nobody can ask a peer where it sends a number."""
        return None

    # This box makes nothing on somebody else's switch: a peer is dialled where it said.
    @override
    async def survey_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> Outbound:
        """The one thing a peer needs to be dialled: the host it named."""
        dialled = self.leg_trunk("")
        says = f"SIP peer: dialled at {dialled.hostname} over {dialled.transport}: stands"
        return Outbound(steps=[says], ready=True, address=dialled.hostname)

    @override
    async def provision_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> tuple[Outbound, Self]:
        """Nothing to make: the peer as it stands."""
        return await self.survey_outbound(http, names, env), self


def _read_transport(named: str) -> Transport:
    for transport in TRANSPORTS:
        if transport == named:
            return transport
    raise ValueError(f"{named} is no transport")
