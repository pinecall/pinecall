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

# What a Page token needs to read and answer the Instagram account linked to the Page.
INSTAGRAM_SCOPES = frozenset({"instagram_basic", "instagram_manage_messages"})


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
    # The Instagram professional account linked to the Page: as Meta says it when the token may read the
    # Page, else as the org brought it; None when none is linked. Its deliveries name this id, not the Page's.
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
    # alone keeps the secret it had, and the Instagram account its messages are known by.
    @override
    def keep_from(self, was: object) -> Self:
        """The Page as brought, with the app's secret and the Instagram account it had where it brings none."""
        if not isinstance(was, FacebookPage):
            return self
        return dataclasses.replace(
            self, app_secret=self.app_secret or was.app_secret, instagram_id=self.instagram_id or was.instagram_id
        )

    # A Page's deliveries are signed by the org's own app, and checked against its secret: a Page with
    # none would be a webhook nobody can vouch for.
    @override
    async def verify(self, http: httpx.AsyncClient) -> None:
        """Refuse a Page with no app secret, or a token Meta does not open it with."""
        if not self.app_secret:
            raise ValidationError(
                f"Page {self.page_id} needs the secret of your Meta app (App settings ▸ Basic): it signs every message"
            )
        try:
            await meta.open_conversations(http, self.access_token, self.page_id)
        except UpstreamError as refused:
            raise ValidationError(
                f"Meta does not open Facebook Page {self.page_id} with this token: {refused}"
            ) from refused

    def describe(self) -> dict[str, str | int]:
        """What the Page answers besides itself, as the carriers list shows it: its linked Instagram account."""
        return {} if self.instagram_id is None else {"instagram_id": self.instagram_id}

    # Done once, when the Page is brought: the Page subscribed to the org's app for its messages, so the
    # org types nothing more at Meta than the webhook. A token that may read the Page (`pages_read_engagement`)
    # names it and its linked Instagram account; the dashboard's, which may not, keeps what the org brought.
    @override
    async def confirm(self, http: httpx.AsyncClient) -> Self:
        """Confirm the Page with Meta: opened, subscribed, and named with its Instagram account where Meta says."""
        await self.verify(http)
        try:
            await meta.subscribe_page(http, self.access_token, self.page_id)
        except UpstreamError as refused:
            raise ValidationError(f"Meta does not subscribe Page {self.page_id} to its app: {refused}") from refused
        try:
            page = await meta.page_of(http, self.access_token, self.page_id)
        except UpstreamError:
            logger.info("Page %s: the token reads nothing of the Page, so it is kept as it was brought", self.page_id)
            whole = self
        else:
            whole = dataclasses.replace(
                self, instagram_id=page.instagram_id or self.instagram_id, label=self.label or page.name
            )
        if whole.instagram_id:
            await whole.check_instagram(http)
        return whole

    # The token Meta's Messenger settings generate carries pages_messaging alone: it answers Messenger, and
    # every Instagram reply would be refused at Meta, with nobody told (tried 2026-11-27).
    async def check_instagram(self, http: httpx.AsyncClient) -> None:
        """Refuse a Page with an Instagram account whose token cannot answer it."""
        try:
            app = await meta.app_of(http, self.access_token)
            scopes = await meta.scopes_of(http, app, self.app_secret, self.access_token)
        except UpstreamError as refused:
            raise ValidationError(f"Meta does not say what Page {self.page_id}'s token may do: {refused}") from refused
        missing = sorted(INSTAGRAM_SCOPES - scopes)
        if missing:
            raise ValidationError(
                f"Page {self.page_id}'s token cannot answer Instagram account {self.instagram_id}: it lacks"
                f" {', '.join(missing)}. The token Meta's Messenger settings generate answers Messenger alone;"
                " one for both is made in the Graph API Explorer"
                " (docs.pinecall.io/integrations/messenger-and-instagram/, step 4)"
            )

    # The app's webhook is given its fields here, not in Meta's dashboard: verifying the callback there
    # chooses none, and then Meta delivers nothing. Its Instagram's too, where the Page has one.
    async def subscribe_webhook(self, http: httpx.AsyncClient, webhook: meta.Subscription) -> None:
        """Subscribe the Page's app to its message fields at this box's callback, and its Instagram's."""
        try:
            app = await meta.app_of(http, self.access_token)
            for channel in (Channel.messenger, Channel.instagram) if self.instagram_id else (Channel.messenger,):
                await meta.subscribe_app(
                    http, app, self.app_secret, channel, webhook.callback_url, webhook.verify_token
                )
        except UpstreamError as refused:
            raise ValidationError(
                f"Meta does not subscribe the app of Page {self.page_id} to its messages: {refused}"
            ) from refused

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

    # What may be routed: the Page itself, and its Instagram account when one is linked, as they were kept.
    @override
    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """The Page and its Instagram account, by the name the Page was given."""
        name = self.label or self.page_id
        owned = [Owned(number=self.page_id, name=name)]
        if self.instagram_id is not None:
            owned.append(Owned(number=self.instagram_id, name=f"{name} · Instagram"))
        return owned

    # A Page answers Messenger at its own id, and Instagram at its linked account's.
    @override
    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """The id is the Page's on Messenger, its Instagram account's on Instagram; nothing else is routed to it."""
        if channel is Channel.messenger and number == self.page_id:
            return
        if channel is Channel.instagram and number == self.instagram_id:
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
