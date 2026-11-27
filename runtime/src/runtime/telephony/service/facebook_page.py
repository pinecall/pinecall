"""A Facebook Page of an org at Meta: its Messenger and its linked Instagram account, answered with the Page's token."""

import dataclasses
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
from runtime.whatsapp import service as meta
from runtime.wire.worker import LegTrunk

logger = logging.getLogger(__name__)

KIND = "messenger"


@dataclass(frozen=True, slots=True)
class FacebookPage(Carrier):
    """A Facebook Page at Meta: its id, the Page's token, its own app's secret, and its linked Instagram account."""

    kind: ClassVar[CarrierKind] = CarrierKind.messenger
    name: ClassVar[str] = "Meta"
    has_api: ClassVar[bool] = False
    channel: ClassVar[Channel] = Channel.messenger

    org: str
    page_id: str
    access_token: str
    # The secret of the org's own Meta app, which signs the Page's deliveries and its Instagram's.
    app_secret: str
    label: str = ""
    # The Instagram professional account linked to the Page, as Meta said it when the Page was brought;
    # None when none is linked. Its deliveries name this id, not the Page's.
    instagram_id: str | None = None

    @property
    @override
    def id(self) -> str:
        """The Page's id at Meta."""
        return self.page_id

    @classmethod
    @override
    def read(cls, org: str, account: Mapping[str, object], outbound: Mapping[str, object] | None) -> Self:
        """The Page out of what a row seals or a body brings."""
        return cls(
            org=org,
            page_id=read_text(account, "page_id"),
            access_token=read_text(account, "access_token"),
            app_secret=read_optional_text(account, "app_secret") or "",
            label=read_optional_text(account, "label") or "",
            instagram_id=read_optional_text(account, "instagram_id"),
        )

    @override
    def dump(self) -> dict[str, Any]:
        """The Page as its row seals it."""
        account: dict[str, Any] = {
            "kind": KIND,
            "page_id": self.page_id,
            "access_token": self.access_token,
            "app_secret": self.app_secret,
            "label": self.label,
        }
        if self.instagram_id is not None:
            account["instagram_id"] = self.instagram_id
        return {"account": account, "outbound": None}

    # A token is renewed far more often than an app changes: bringing the Page again with a new token
    # and no secret keeps the secret it had.
    @override
    def keep_from(self, was: object) -> Self:
        """The Page as brought, with the app's secret it had when it brings none."""
        if self.app_secret or not isinstance(was, FacebookPage):
            return self
        return dataclasses.replace(self, app_secret=was.app_secret)

    # A Page's deliveries are signed by the org's own app, and checked against its secret: a Page with
    # none would be a webhook nobody can vouch for.
    @override
    async def verify(self, http: httpx.AsyncClient) -> None:
        """Refuse a Page with no app secret, or a token Meta does not open it with."""
        if not self.app_secret:
            raise ValidationError(
                f"Page {self.page_id} needs the secret of your Meta app (App settings ▸ Basic): it signs every message"
            )
        await self._page(http)

    def describe(self) -> dict[str, str | int]:
        """What the Page answers besides itself, as the carriers list shows it: its linked Instagram account."""
        return {} if self.instagram_id is None else {"instagram_id": self.instagram_id}

    # Asked once, when the Page is brought: which Instagram account is linked to it, and the Page
    # subscribed to the org's app for its messages, so the org types nothing more at Meta than the webhook.
    @override
    async def confirmed(self, http: httpx.AsyncClient) -> Self:
        """The Page as Meta names it, its linked Instagram account filled in, and subscribed to the app."""
        await self.verify(http)
        page = await self._page(http)
        try:
            await meta.subscribe_page(http, self.access_token, self.page_id)
        except UpstreamError as refused:
            raise ValidationError(f"Meta does not subscribe Page {self.page_id} to its app: {refused}") from refused
        return dataclasses.replace(self, instagram_id=page.instagram_id, label=self.label or page.name)

    @override
    def calling_networks(self) -> tuple[str, ...] | None:
        """None: a message is signed by Meta, and comes over no trunk."""
        return None

    @override
    def fence(self, number: str, standing: Standing) -> Fenced:
        """Refused: a Page is on no SIP trunk."""
        raise ValidationError(f"{self.id} is a Facebook Page: it is on no SIP trunk")

    @override
    def list_missing_to_dial(self) -> list[str]:
        """Everything: it places no call."""
        return [f"{self.id} is a Facebook Page: it places no call"]

    @override
    def leg_trunk(self, shown: str) -> LegTrunk:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    # What may be routed: the Page itself, and its Instagram account when one is linked. A token Meta
    # refuses leaves the account listed with nothing to route, said in the log.
    @override
    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """The Page and its Instagram account, as Meta names them; none while Meta does not say."""
        try:
            page = await meta.page_of(http, self.access_token, self.page_id)
        except UpstreamError:
            logger.warning("Meta did not say which Page %s is", self.page_id, exc_info=True)
            return []
        owned = [Owned(number=page.page_id, name=page.name or page.page_id)]
        if page.instagram_id is not None:
            owned.append(
                Owned(
                    number=page.instagram_id,
                    name=f"@{page.instagram_name}" if page.instagram_name else page.instagram_id,
                )
            )
        return owned

    # A Page answers Messenger at its own id, and Instagram at its linked account's.
    @override
    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """The id is the Page's on Messenger, its Instagram account's on Instagram; nothing else is routed to it."""
        if channel is Channel.messenger and number == self.page_id:
            return
        if channel is Channel.instagram and number == (await self._page(http)).instagram_id:
            return
        raise ValidationError(
            f"{number} is not what Page {self.page_id} answers on {channel}: Messenger at the Page's id, "
            "Instagram at the id of the Instagram account linked to it"
        )

    @override
    async def survey_hook(
        self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env, *, move: bool
    ) -> list[Step]:
        """Nothing: Meta is pointed at the box by its webhook, not by a number."""
        return []

    @override
    async def is_pointed_here(self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env) -> bool | None:
        """None: Meta is not asked where it sends a Page's messages."""
        return None

    @override
    async def survey_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> Outbound:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    @override
    async def provision_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> tuple[Outbound, Self]:
        """Refused: it places no call."""
        raise Conflict(self.list_missing_to_dial()[0])

    async def _page(self, http: httpx.AsyncClient) -> meta.MetaPage:
        try:
            return await meta.page_of(http, self.access_token, self.page_id)
        except UpstreamError as refused:
            raise ValidationError(
                f"Meta does not open Facebook Page {self.page_id} with this token: {refused}"
            ) from refused
