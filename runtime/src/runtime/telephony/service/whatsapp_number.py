"""A WhatsApp number of an org at Meta: the id replies are sent from and the org's token; on no trunk, no call out."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Self, override

import httpx

from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, UpstreamError, ValidationError
from runtime.telephony.models import CarrierKind
from runtime.telephony.service.carrier import (
    Carrier,
    Outbound,
    Owned,
    SipNames,
    Step,
    read_optional_text,
    read_text,
)
from runtime.telephony.service.fence import Fenced
from runtime.telephony.service.networks import Standing
from runtime.whatsapp import service as whatsapp
from runtime.wire.worker import LegTrunk

logger = logging.getLogger(__name__)

KIND = "whatsapp"


@dataclass(frozen=True, slots=True)
class WhatsappNumber(Carrier):
    """A WhatsApp number at Meta: the id replies are sent from, and the org's token."""

    kind: ClassVar[CarrierKind] = CarrierKind.whatsapp
    name: ClassVar[str] = "Meta"
    has_api: ClassVar[bool] = False

    org: str
    phone_number_id: str
    access_token: str
    label: str = ""

    @property
    @override
    def id(self) -> str:
        """Meta's phone number id."""
        return self.phone_number_id

    @classmethod
    @override
    def read(cls, org: str, account: Mapping[str, object], outbound: Mapping[str, object] | None) -> Self:
        """The number out of what a row seals or a body brings."""
        return cls(
            org=org,
            phone_number_id=read_text(account, "phone_number_id"),
            access_token=read_text(account, "access_token"),
            label=read_optional_text(account, "label") or "",
        )

    # Every field, as the release before 2026-11 wrote it and reads it, refusing one it does not know.
    @override
    def dump(self) -> dict[str, Any]:
        """The number as its row seals it."""
        account = {
            "kind": KIND,
            "phone_number_id": self.phone_number_id,
            "access_token": self.access_token,
            "label": self.label,
        }
        return {"account": account, "outbound": None}

    @override
    def keep_from(self, was: object) -> Self:
        """The number as brought: the box made nothing on the one before."""
        return self

    # Meta is asked for the number the id names, as the inbox asks it: a token that does not open it
    # is refused here, in Meta's words, and not on the first message.
    @override
    async def verify(self, http: httpx.AsyncClient) -> None:
        """Refuse a token Meta does not open the number with."""
        try:
            await whatsapp.number_of(http, self.access_token, self.phone_number_id)
        except UpstreamError as refused:
            raise ValidationError(
                f"Meta does not open WhatsApp number {self.phone_number_id} with this token: {refused}"
            ) from refused

    @override
    def calling_networks(self) -> tuple[str, ...] | None:
        """None: a message is signed by Meta, and comes over no trunk."""
        return None

    @override
    def fence(self, number: str, standing: Standing) -> Fenced:
        """Refused: a WhatsApp number is on no SIP trunk."""
        raise ValidationError(f"{self.id} is a WhatsApp number: it is on no SIP trunk")

    @override
    def list_missing_to_dial(self) -> list[str]:
        """Everything: it places no call."""
        return [f"{self.id} is a WhatsApp number: it places no call"]

    @override
    def leg_trunk(self, shown: str) -> LegTrunk:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    # A token Meta refuses (they expire) leaves the account listed with no number, said in the log.
    @override
    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """The one number the account is, as Meta names it; none while Meta does not say."""
        try:
            found = await whatsapp.number_of(http, self.access_token, self.phone_number_id)
        except UpstreamError:
            logger.warning("Meta did not say which number %s is", self.phone_number_id, exc_info=True)
            return []
        return [Owned(number=found.number, name=found.verified_name or found.number)]

    @override
    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """The number is the one the account is, as Meta names it, and answers WhatsApp alone."""
        if channel is not Channel.whatsapp:
            return
        display = (await whatsapp.number_of(http, self.access_token, self.phone_number_id)).number
        if display != number:
            raise ValidationError(
                f"{number} is not the number the WhatsApp Business account is: Meta says it is {display}"
            )

    @override
    async def survey_hook(
        self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env, *, move: bool
    ) -> list[Step]:
        """Nothing: Meta is pointed at the box by its webhook, not by a number."""
        return []

    @override
    async def is_pointed_here(self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env) -> bool | None:
        """None: Meta is not asked where it sends a number's messages."""
        return None

    @override
    async def survey_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> Outbound:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    @override
    async def provision_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> tuple[Outbound, Self]:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])
