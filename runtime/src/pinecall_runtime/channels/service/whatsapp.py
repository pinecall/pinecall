"""WhatsApp's Cloud API: the webhook's handshake and signature, the messages in a body, a reply."""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.channels.repository import WhatsappSeenRepository
from pinecall_runtime.exceptions import Forbidden, ServiceUnavailable, UpstreamError
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers import service as providers

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"
SIGNED_WITH = "sha256="
SIGNATURE_HEADER = "x-hub-signature-256"
TIMEOUT_S = 10.0
# A conversation quiet this long is over: the next message opens a new call. It is under
# Meta's 24 h customer-service window, which only the idle close keeps.
IDLE_S = 2 * 60 * 60
# Meta lets a business write freely only this long after the contact's last message
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages).
WINDOW_S = 24 * 60 * 60
# The box's Meta app, sealed in box_settings as credentials/whatsapp.
BOX_ACCOUNT = "whatsapp"
NO_META = "this box has no Meta app (credentials/whatsapp): its WhatsApp endpoint is closed"
NOT_THE_WORD = "the verify token is not this box's"
# Meta retries a webhook not answered 200 with decreasing frequency for up to 7 days
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks): an id is kept as long.
SEEN_KEPT = timedelta(days=7)
# Longer than a delivery is ever read in (the route, and opening the conversation at worst): a
# claim still unread past it is a process that died reading it, and the next delivery reads it.
READING = timedelta(minutes=10)

# `new`: this delivery claimed it and reads it; `seen`: another read it; `reading`: another
# delivery is reading it now, and Meta must be told to come back.
type Claim = Literal["new", "seen", "reading"]


class Meta(BaseModel):
    """The box's Meta app: the secret every body is signed with, the handshake word, a token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_secret: str = Field(min_length=1)
    verify_token: str = Field(min_length=1)
    # Replies for an org that brought no token of its own.
    access_token: str | None = None


@dataclass(frozen=True, slots=True)
class Inbound:
    """One message to one of the box's WhatsApp numbers."""

    number: str
    phone_number_id: str
    wa_id: str
    name: str | None
    message_id: str
    kind: str
    text: str | None

    @property
    def caller(self) -> str:
        """The sender in E.164: WhatsApp names them by digits alone."""
        return f"+{self.wa_id}"


# Meta adds fields without notice, and a webhook answered 4xx for long is disabled: every
# model ignores what it does not know.
class _Lenient(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class _Text(_Lenient):
    body: str | None = None


class _Message(_Lenient):
    id: str = ""
    sender: str = Field("", alias="from")
    type: str = ""
    text: _Text | None = None


class _Profile(_Lenient):
    name: str | None = None


class _Contact(_Lenient):
    wa_id: str = ""
    profile: _Profile | None = None


class _Metadata(_Lenient):
    display_phone_number: str = ""
    phone_number_id: str = ""


# A delivery receipt arrives in this shape, with `statuses` and no messages.
class _Value(_Lenient):
    metadata: _Metadata | None = None
    contacts: list[_Contact] = Field(default_factory=list[_Contact])
    messages: list[_Message] = Field(default_factory=list[_Message])


class _Change(_Lenient):
    value: _Value | None = None


class _Entry(_Lenient):
    changes: list[_Change] = Field(default_factory=list[_Change])


class _Body(_Lenient):
    entry: list[_Entry] = Field(default_factory=list[_Entry])


class _Refused(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    message: str = ""


class _Refusal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    error: _Refused | None = None


class _Number(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    display_phone_number: str
    verified_name: str = ""


async def box_meta_app(session: AsyncSession, vault: Vault) -> Meta:
    """The box's Meta app; ServiceUnavailable when it has none."""
    credentials = (await providers.box_credentials(session, vault)).get(BOX_ACCOUNT)
    try:
        return Meta.model_validate(credentials)
    except PydanticValidationError:
        raise ServiceUnavailable(NO_META) from None


# Meta keeps the subscription only when the challenge comes back as it was sent, as plain text.
def handshake(meta: Meta, mode: str | None, word: str | None, challenge: str | None) -> str:
    """The challenge to echo back, when Meta subscribes with this box's word."""
    if mode != "subscribe" or word is None or challenge is None:
        raise Forbidden(NOT_THE_WORD)
    if not hmac.compare_digest(word.encode(), meta.verify_token.encode()):
        raise Forbidden(NOT_THE_WORD)
    return challenge


# The raw bytes, before anything parses them: a body re-serialised signs differently.
def is_signed(app_secret: str, body: bytes, header: str | None) -> bool:
    """Whether the body carries the app's HMAC-SHA256 signature."""
    if header is None or not header.startswith(SIGNED_WITH):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix(SIGNED_WITH), expected)


def messages_in(body: bytes) -> list[Inbound]:
    """Every message in Meta's body, in Meta's order; none in a receipt or a stranger's body."""
    try:
        parsed = _Body.model_validate_json(body)
    except PydanticValidationError:
        return []
    found: list[Inbound] = []
    for change in (change for entry in parsed.entry for change in entry.changes):
        value = change.value
        if value is None or value.metadata is None:
            continue
        names = {contact.wa_id: contact.profile.name for contact in value.contacts if contact.profile}
        found += [
            Inbound(
                number=f"+{value.metadata.display_phone_number.lstrip('+')}",
                phone_number_id=value.metadata.phone_number_id,
                wa_id=message.sender,
                name=names.get(message.sender),
                message_id=message.id,
                kind=message.type,
                text=None if message.text is None else message.text.body,
            )
            for message in value.messages
        ]
    return found


async def display_number(http: httpx.AsyncClient, token: str, phone_number_id: str) -> tuple[str, str]:
    """The number a WhatsApp account answers at, in E.164, and its name at Meta."""
    answer = await http.get(
        f"{GRAPH}/{phone_number_id}",
        params={"fields": "display_phone_number,verified_name"},
        headers={"authorization": f"Bearer {token}"},
        timeout=TIMEOUT_S,
    )
    if answer.is_error:
        raise UpstreamError(f"WhatsApp: {_refused_by(answer)}")
    named = _Number.model_validate_json(answer.content)
    return "+" + "".join(digit for digit in named.display_phone_number if digit.isdigit()), named.verified_name


async def send_text(http: httpx.AsyncClient, token: str, inbound: Inbound, text: str) -> None:
    """Send the text to the contact from the number they wrote to; Meta's refusal in its words."""
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": inbound.wa_id,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    answer = await http.post(
        f"{GRAPH}/{inbound.phone_number_id}/messages",
        json=body,
        headers={"authorization": f"Bearer {token}"},
        timeout=TIMEOUT_S,
    )
    if answer.is_error:
        raise UpstreamError(f"WhatsApp: {_refused_by(answer)}")


# The insert is the check: of two deliveries at once, one inserts and the other finds the row.
async def claim_message(session: AsyncSession, org: str, message_id: str, *, at: datetime) -> Claim:
    """Claim the org's message for this delivery, unless another has read it or is reading it."""
    repository = WhatsappSeenRepository(session)
    if await repository.claim(org, message_id, at=at, stale_before=at - READING):
        return "new"
    row = await repository.get(org, message_id)
    # A row gone between the two is a claim released: the delivery that held it failed.
    return "seen" if row is not None and row.read_at is not None else "reading"


async def mark_message_read(session: AsyncSession, org: str, message_id: str, *, at: datetime) -> None:
    """The claimed message is read: every later delivery of it is dropped."""
    await WhatsappSeenRepository(session).mark_read(org, message_id, at=at)


async def release_message(session: AsyncSession, org: str, message_id: str) -> None:
    """Give up the claim of a message whose reading failed, so Meta's next delivery reads it."""
    await WhatsappSeenRepository(session).release(org, message_id)


async def forget_seen_before(session: AsyncSession, now: datetime) -> int:
    """Forget the message ids claimed longer ago than Meta retries; how many."""
    return await WhatsappSeenRepository(session).forget_before(now - SEEN_KEPT)


def _refused_by(answer: httpx.Response) -> str:
    try:
        refused = _Refusal.model_validate_json(answer.content).error
    except PydanticValidationError:
        refused = None
    if refused is not None and refused.message:
        return refused.message
    return str(answer.status_code)
