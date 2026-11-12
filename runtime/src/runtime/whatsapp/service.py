"""WhatsApp's Cloud API: the box's Meta app, the webhook's handshake and signature, a body's messages, a reply, once."""

import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import Forbidden, ServiceUnavailable, UpstreamError
from runtime.kit.crypto import Vault
from runtime.kit.loops import survive
from runtime.kit.text import a_mapping
from runtime.providers import service as providers
from runtime.whatsapp.models import Claim
from runtime.whatsapp.repository import WhatsappSeenRepository

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"
# Who an UpstreamError of this module names.
VENDOR = "meta"
SIGNED_WITH = "sha256="
SIGNATURE_HEADER = "x-hub-signature-256"
TIMEOUT_S = 10.0
# Meta's bodies are a few kilobytes; a webhook is never a file.
LONGEST_WEBHOOK = 1024 * 1024
# The box's Meta app, sealed in box_settings as credentials/whatsapp, beside the vendors' keys: the
# release before 2026-11 reads the same row, so it stays under that name until that release is gone.
BOX_ACCOUNT = "whatsapp"
META_APP_FIELDS = frozenset({"app_secret", "verify_token", "access_token"})
NO_META = "this box has no Meta app (credentials/whatsapp): its WhatsApp endpoint is closed"
NOT_THE_WORD = "the verify token is not this box's"
# Meta retries a webhook not answered 200 with decreasing frequency for up to 7 days
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks): an id is kept as long.
SEEN_KEPT = timedelta(days=7)
# Longer than a delivery is ever read in (the route, and opening the conversation at worst): a
# claim still unread past it is a process that died reading it, and the next delivery reads it.
READING = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class MetaApp:
    """The box's Meta app: the secret every body is signed with, the handshake word, a token."""

    app_secret: str
    verify_token: str
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


@dataclass(frozen=True, slots=True)
class MetaNumber:
    """The number a WhatsApp account answers at, in E.164, and its name at Meta."""

    number: str
    verified_name: str


# Which agent answers a number, whether an app holds it and the call a contact's messages go on are
# kept by `live`, above this domain. What keeps them is handed in under `threads`.
class Threads(Protocol):
    """The contacts' open conversations, as the webhook needs them."""

    async def receive(self, inbound: Inbound) -> bool:
        """Read the message once, onto its contact's conversation; False while another delivery reads it."""
        ...


# ── what Meta writes, read here beside the client that asks it ──


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


# ── the box's Meta app, and the webhook it signs ──


async def box_meta_app(session: AsyncSession, vault: Vault) -> MetaApp:
    """The box's Meta app; ServiceUnavailable when it has none."""
    app = _meta_app_in((await providers.box_credentials(session, vault)).get(BOX_ACCOUNT))
    if app is None:
        raise ServiceUnavailable(NO_META)
    return app


# Meta keeps the subscription only when the challenge comes back as it was sent, as plain text.
def handshake(app: MetaApp, mode: str | None, word: str | None, challenge: str | None) -> str:
    """The challenge to echo back, when Meta subscribes with this box's word."""
    if mode != "subscribe" or word is None or challenge is None:
        raise Forbidden(NOT_THE_WORD)
    if not hmac.compare_digest(word.encode(), app.verify_token.encode()):
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


# Past the signature the answer is 200: Meta disables a webhook that keeps failing, so what goes
# wrong after it is a line in the log. The one exception is a message another delivery is still
# reading: 503 keeps it on Meta's side until that reading is done or has died.
#
# Until 2026-11 the route did not do what these lines say. A message whose reading raised was a 500;
# and every claim of the body was written in the request's one transaction, so that 500 took back
# the claims of the messages before it, which were queued on their conversations already: Meta
# delivered the body again and they were answered twice.
async def receive_all(threads: Threads, messages: Sequence[Inbound]) -> int:
    """Every message of a signed body onto its contact's conversation; how many the body carried."""
    unread = 0
    for inbound in messages:
        with survive("reading a WhatsApp message", inbound.message_id):
            if not await threads.receive(inbound):
                unread += 1
    if unread:
        raise ServiceUnavailable(f"{unread} of these messages are being read by another delivery: send it again")
    return len(messages)


# ── Meta's Graph ──


async def number_of(http: httpx.AsyncClient, token: str, phone_number_id: str) -> MetaNumber:
    """The number a WhatsApp account answers at, in E.164, and its name at Meta."""
    answer = await _ask(http, "GET", phone_number_id, token, params={"fields": "display_phone_number,verified_name"})
    try:
        named = _Number.model_validate_json(answer.content)
    except PydanticValidationError:
        raise UpstreamError(
            f"WhatsApp: Meta named no number for {phone_number_id}", vendor=VENDOR, answered=answer.status_code
        ) from None
    digits = "".join(digit for digit in named.display_phone_number if digit.isdigit())
    return MetaNumber(number=f"+{digits}", verified_name=named.verified_name)


async def send_text(http: httpx.AsyncClient, token: str, inbound: Inbound, text: str) -> None:
    """Send the text to the contact from the number they wrote to; Meta's refusal in its words."""
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": inbound.wa_id,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    await _ask(http, "POST", f"{inbound.phone_number_id}/messages", token, json=body)


# ── a message read once ──


# Meta delivers a message again when it thinks it unanswered. The row is claimed before the
# message is read, so of two deliveries at once only one reads it; it is marked read once the
# message is queued or kept, and a reading that fails gives the claim back, so Meta's next
# delivery reads it again. A process that dies mid-reading leaves a claim its lease expires.
#
# Each of the three is a transaction of its own, committed before the next thing happens. Until
# 2026-11 they ran on the session of the webhook's request, which commits when the route returns: a
# second delivery never saw `reading` (its insert waited on the first one's row lock, holding a
# connection, until that request ended or the statement timed out), and a claim lasted only as long
# as the request did not fail.
async def read_once(
    sessions: async_sessionmaker[AsyncSession],
    org: str,
    message_id: str,
    read: Callable[[], Awaitable[None]],
    *,
    at: datetime,
) -> bool:
    """Read the org's message unless a delivery read it before; False while another is reading it."""
    claim = await claim_message(sessions, org, message_id, at=at)
    if claim is not Claim.new:
        logger.info("whatsapp: message %s delivered again, dropped: %s", message_id, claim)
        return claim is Claim.seen
    try:
        await read()
    except Exception:
        await release_message(sessions, org, message_id)
        raise
    await mark_message_read(sessions, org, message_id, at=at)
    return True


# The insert is the check: of two deliveries at once, one inserts and the other finds the row.
async def claim_message(
    sessions: async_sessionmaker[AsyncSession], org: str, message_id: str, *, at: datetime
) -> Claim:
    """Claim the org's message for this delivery, unless another has read it or is reading it."""
    async with sessions.begin() as session:
        repository = WhatsappSeenRepository(session)
        if await repository.claim(org, message_id, at=at, stale_before=at - READING):
            return Claim.new
        row = await repository.find(org, message_id)
    # A row gone between the two is a claim released: the delivery that held it failed.
    return Claim.seen if row is not None and row.read_at is not None else Claim.reading


async def mark_message_read(
    sessions: async_sessionmaker[AsyncSession], org: str, message_id: str, *, at: datetime
) -> None:
    """The claimed message is read: every later delivery of it is dropped."""
    async with sessions.begin() as session:
        await WhatsappSeenRepository(session).mark_read(org, message_id, at=at)


async def release_message(sessions: async_sessionmaker[AsyncSession], org: str, message_id: str) -> None:
    """Give up the claim of a message whose reading failed, so Meta's next delivery reads it."""
    async with sessions.begin() as session:
        await WhatsappSeenRepository(session).release(org, message_id)


async def forget_seen_before(session: AsyncSession, now: datetime) -> int:
    """Forget the message ids claimed longer ago than Meta retries; how many."""
    return await WhatsappSeenRepository(session).delete_before(now - SEEN_KEPT)


# ── private ──


# Read as strictly as it is written: a row that is not the three fields of an app is no app, and
# the endpoint stays closed rather than check a signature against half a secret.
def _meta_app_in(credentials: object) -> MetaApp | None:
    if not a_mapping(credentials) or not credentials.keys() <= META_APP_FIELDS:
        return None
    app_secret, verify_token = credentials.get("app_secret"), credentials.get("verify_token")
    access_token = credentials.get("access_token")
    if not isinstance(app_secret, str) or not app_secret or not isinstance(verify_token, str) or not verify_token:
        return None
    if access_token is not None and not isinstance(access_token, str):
        return None
    return MetaApp(app_secret=app_secret, verify_token=verify_token, access_token=access_token)


# The one place Meta is asked, and its no translated: a refusal in Meta's own words, with the status
# it answered; its silence and its own failures as what asking again may mend.
async def _ask(
    http: httpx.AsyncClient,
    method: str,
    path: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    try:
        answer = await http.request(
            method,
            f"{GRAPH}/{path}",
            params=params,
            json=json,
            headers={"authorization": f"Bearer {token}"},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as silent:
        raise UpstreamError(
            f"WhatsApp: Meta did not answer ({type(silent).__name__})", vendor=VENDOR, retryable=True
        ) from silent
    if answer.is_error:
        raise UpstreamError(
            f"WhatsApp: {_refusal_of(answer)}",
            vendor=VENDOR,
            answered=answer.status_code,
            retryable=answer.is_server_error,
        )
    return answer


def _refusal_of(answer: httpx.Response) -> str:
    try:
        refused = _Refusal.model_validate_json(answer.content).error
    except PydanticValidationError:
        refused = None
    if refused is not None and refused.message:
        return refused.message
    return str(answer.status_code)
