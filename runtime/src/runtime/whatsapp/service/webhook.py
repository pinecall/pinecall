"""Meta's webhook: the app that signs it (the box's, or an org's own), its handshake, and the messages of a body."""

import dataclasses
import hashlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Channel
from runtime.exceptions import Forbidden, ServiceUnavailable
from runtime.kit.crypto import Vault
from runtime.kit.loops import survive
from runtime.kit.text import a_mapping
from runtime.providers import service as providers

SIGNED_WITH = "sha256="
SIGNATURE_HEADER = "x-hub-signature-256"
# The path Meta is given as an app's callback URL, at the box's public name.
PATH = "/v1/whatsapp/webhook"
# What an app subscribes to, of Meta's `whatsapp_business_account` object: its numbers' messages.
FIELD = "messages"
# Meta's bodies are a few kilobytes; a webhook is never a file.
LONGEST_WEBHOOK = 1024 * 1024
# The box's Meta app, sealed in box_settings as credentials/whatsapp, beside the vendors' keys: the
# release before 2026-11 reads the same row, so it stays under that name until that release is gone.
BOX_ACCOUNT = "whatsapp"
META_APP_FIELDS = frozenset({"app_secret", "verify_token", "access_token"})
# A body the box's own app did not sign names the numbers of one org's app: a handful. One that
# names more is read no further, so a stranger's body costs a bounded look at the accounts.
FEW_NUMBERS = 8
# What an org's verify token is the vault's mark on, with the org.
WORD_OF = "whatsapp webhook of "


@dataclass(frozen=True, slots=True)
class MetaApp:
    """The box's Meta app: the secret every body is signed with, the handshake word, a token."""

    app_secret: str
    verify_token: str
    # Replies for an org that brought no token of its own.
    access_token: str | None = None


# An org that made its own Meta app brings the app's secret with its number: Meta signs that
# number's deliveries with it, and the box's app never hears of them.
@dataclass(frozen=True, slots=True)
class OwnApp:
    """An org's own Meta app, as an account of it names it: the id a body names, and the secret it signs with."""

    org: str
    # The id a body names: a WhatsApp number's at Meta, a Page's, or its linked Instagram account's.
    phone_number_id: str
    app_secret: str
    # The account the contact is answered from: the Page an Instagram account is linked to; the id
    # itself when empty (a WhatsApp number, a Page).
    answers_from: str = ""


@dataclass(frozen=True, slots=True)
class Subscription:
    """What an org types in its own Meta app: the callback URL, the verify token, the field to subscribe to."""

    callback_url: str
    verify_token: str
    field: str = FIELD


@dataclass(frozen=True, slots=True)
class Inbound:
    """One message a contact wrote to one of the box's addresses: on WhatsApp, by SMS, or by email."""

    number: str
    # The provider's id for that number: Meta's phone number id, or the Twilio account an SMS came through.
    phone_number_id: str
    # The provider's id for who wrote: the contact's number, digits alone.
    wa_id: str
    name: str | None
    message_id: str
    kind: str
    # What the contact wrote, or the words of the button or the list row they chose.
    text: str | None
    # A voice note's audio at Meta (its media id on WhatsApp, its link on Messenger and Instagram),
    # heard before the message is read.
    media_id: str | None = None
    # The orgs whose own app signed the body for this number; None when the box's app did.
    signed_for: frozenset[str] | None = None
    # The channel it was written on: a thread of a number is a channel's, and so is how it is answered.
    channel: Channel = Channel.whatsapp
    # The carrier read the message as a word of its own (STOP, START, HELP) and answered it itself.
    carrier_replied: bool = False
    # An email's subject, the ids of the messages before it in its thread, and the thread's first id:
    # one contact's emails on two subjects are two conversations.
    subject: str | None = None
    references: tuple[str, ...] = ()
    thread: str = ""

    @property
    def caller(self) -> str:
        """The sender: in E.164 (WhatsApp names them by digits alone), their email address, or Meta's id of them."""
        if self.channel.is_by_meta_id:
            return meta_caller(self.channel, self.wa_id)
        return self.wa_id if self.channel.is_by_email else f"+{self.wa_id}"

    def may_reach(self, org: str, account: str | None) -> bool:
        """Whether a number of this org, in this account, is one the body's signature vouches for."""
        return _vouches(self.signed_for, self.phone_number_id, org, account)


@dataclass(frozen=True, slots=True)
class Receipt:
    """Where a message the agent wrote stands with its contact, as Meta says it: sent, delivered, read, failed."""

    number: str
    phone_number_id: str
    wa_id: str
    message_id: str
    status: str
    # Meta's words for a message that failed.
    error: str | None = None
    signed_for: frozenset[str] | None = None
    channel: Channel = Channel.whatsapp
    # No email is answered with a receipt: a receipt names no thread of its own.
    thread: str = ""

    @property
    def caller(self) -> str:
        """The contact in E.164, or Meta's id of them."""
        return meta_caller(self.channel, self.wa_id) if self.channel.is_by_meta_id else f"+{self.wa_id}"

    def may_reach(self, org: str, account: str | None) -> bool:
        """Whether a number of this org, in this account, is one the body's signature vouches for."""
        return _vouches(self.signed_for, self.phone_number_id, org, account)


@dataclass(frozen=True, slots=True)
class Delivery:
    """What one signed body carries: the contacts' messages, and the receipts of the agent's."""

    messages: list[Inbound]
    receipts: list[Receipt]


# Which agent answers a number, whether an app holds it and the call a contact's messages go on are
# kept by `live`, above this domain. What keeps them is handed in under `threads`.
class Threads(Protocol):
    """The contacts' open conversations, as the webhook needs them."""

    async def receive(self, inbound: Inbound) -> bool:
        """Read the message once, onto its contact's conversation; False while another delivery reads it."""
        ...

    async def note(self, receipt: Receipt) -> None:
        """Say on the contact's open conversation where a message the agent wrote stands."""
        ...


# ── what Meta writes, read here beside the client that asks it ──


# Meta adds fields without notice, and a webhook answered 4xx for long is disabled: every
# model ignores what it does not know.
class _Lenient(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class _Text(_Lenient):
    body: str | None = None


class _Chosen(_Lenient):
    title: str | None = None


# What comes back when the contact taps a reply button or a row of a list the agent sent.
class _Interactive(_Lenient):
    button_reply: _Chosen | None = None
    list_reply: _Chosen | None = None


# A template's quick-reply button, which Meta writes in a shape of its own.
class _Button(_Lenient):
    text: str | None = None


class _Audio(_Lenient):
    id: str | None = None


class _Message(_Lenient):
    id: str = ""
    sender: str = Field("", alias="from")
    type: str = ""
    text: _Text | None = None
    interactive: _Interactive | None = None
    button: _Button | None = None
    audio: _Audio | None = None

    @property
    def words(self) -> str | None:
        """What the contact wrote, or the words of what they tapped; None for what carries none."""
        if self.text is not None:
            return self.text.body
        if self.button is not None:
            return self.button.text
        chosen = None if self.interactive is None else self.interactive.button_reply or self.interactive.list_reply
        return None if chosen is None else chosen.title


class _Profile(_Lenient):
    name: str | None = None


class _Contact(_Lenient):
    wa_id: str = ""
    profile: _Profile | None = None


class _Metadata(_Lenient):
    display_phone_number: str = ""
    phone_number_id: str = ""


class _Failure(_Lenient):
    title: str | None = None
    message: str | None = None


class _Status(_Lenient):
    id: str = ""
    status: str = ""
    recipient_id: str = ""
    errors: list[_Failure] = Field(default_factory=list[_Failure])

    @property
    def failure(self) -> str | None:
        """Why Meta says the message failed, in its words; None for one that did not."""
        said = (error.message or error.title for error in self.errors)
        return next((words for words in said if words), None)


# A delivery receipt arrives in this shape, with `statuses` and no messages.
class _Value(_Lenient):
    metadata: _Metadata | None = None
    contacts: list[_Contact] = Field(default_factory=list[_Contact])
    messages: list[_Message] = Field(default_factory=list[_Message])
    statuses: list[_Status] = Field(default_factory=list[_Status])


class _Change(_Lenient):
    value: _Value | None = None


class _Entry(_Lenient):
    changes: list[_Change] = Field(default_factory=list[_Change])


class _Body(_Lenient):
    entry: list[_Entry] = Field(default_factory=list[_Entry])


# ── the box's Meta app, and the webhook it signs ──


async def find_box_meta_app(session: AsyncSession, vault: Vault) -> MetaApp | None:
    """The box's Meta app, or None on a box that has none."""
    return _meta_app_in((await providers.box_credentials(session, vault)).get(BOX_ACCOUNT))


async def box_meta_app(session: AsyncSession, vault: Vault) -> MetaApp:
    """The box's Meta app; ServiceUnavailable when it has none."""
    app = await find_box_meta_app(session, vault)
    if app is None:
        raise ServiceUnavailable("this box has no Meta app (credentials/whatsapp): it answers no number of its own")
    return app


# The word is the vault's mark on the org, so the box knows it again with nothing kept. It is typed
# once, when the app's webhook is saved; a vault key that changes later asks nothing of an app
# already subscribed.
def subscription_of(vault: Vault, org: str, base_url: str) -> Subscription:
    """What the org types in its own Meta app: where Meta delivers, and the word it subscribes with."""
    return Subscription(callback_url=f"{base_url}{PATH}", verify_token=f"{org}.{vault.sign(WORD_OF + org)}")


# Meta keeps the subscription only when the challenge comes back as it was sent, as plain text.
def handshake(box: MetaApp | None, vault: Vault, mode: str | None, word: str | None, challenge: str | None) -> str:
    """The challenge to echo back, when Meta subscribes with the box's word or one it gave an org."""
    if mode != "subscribe" or word is None or challenge is None:
        raise Forbidden("the verify token is not this box's")
    org, _, mark = word.rpartition(".")
    if org and vault.is_signed(WORD_OF + org, mark):
        return challenge
    if box is None or not hmac.compare_digest(word.encode(), box.verify_token.encode()):
        raise Forbidden("the verify token is not this box's, nor one it gave an org for its own Meta app")
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
                text=message.words,
                media_id=None if message.audio is None else message.audio.id,
            )
            for message in value.messages
        ]
    return found


def receipts_in(body: bytes) -> list[Receipt]:
    """Every receipt in Meta's body, in Meta's order: where a message the agent wrote stands."""
    try:
        parsed = _Body.model_validate_json(body)
    except PydanticValidationError:
        return []
    found: list[Receipt] = []
    for change in (change for entry in parsed.entry for change in entry.changes):
        value = change.value
        if value is None or value.metadata is None:
            continue
        found += [
            Receipt(
                number=f"+{value.metadata.display_phone_number.lstrip('+')}",
                phone_number_id=value.metadata.phone_number_id,
                wa_id=status.recipient_id,
                message_id=status.id,
                status=status.status,
                error=status.failure,
            )
            for status in value.statuses
            if status.id and status.status and status.recipient_id
        ]
    return found


# Read before anybody vouched for the body, and for one thing: whose app may have signed it.
def numbers_named_in(body: bytes) -> set[str]:
    """The phone number ids a body names; none for a body that is no envelope, or one that names too many."""
    try:
        parsed = _Body.model_validate_json(body)
    except PydanticValidationError:
        return set()
    values = (change.value for entry in parsed.entry for change in entry.changes)
    named = {value.metadata.phone_number_id for value in values if value is not None and value.metadata is not None}
    return named if len(named) <= FEW_NUMBERS else set()


# A body of receipts alone is signed like any other, and answered 200 like any other.
def read_signed(box: MetaApp | None, own: Sequence[OwnApp], body: bytes, header: str | None) -> Delivery:
    """What a body the box's app signed carries, or an org's own for its numbers; Forbidden for any other."""
    if box is not None and is_signed(box.app_secret, body, header):
        return Delivery(messages_in(body), receipts_in(body))
    signers: dict[str, set[str]] = {}
    for app in own:
        if is_signed(app.app_secret, body, header):
            signers.setdefault(app.phone_number_id, set()).add(app.org)
    if not signers:
        raise Forbidden(
            "the body carries the signature of no Meta app this box knows: its own, or one an org brought "
            "with its number (`pinecall carriers add whatsapp` asks for the app's secret)"
        )
    return Delivery(
        [
            dataclasses.replace(message, signed_for=frozenset(signers[message.phone_number_id]))
            for message in messages_in(body)
            if message.phone_number_id in signers
        ],
        [
            dataclasses.replace(receipt, signed_for=frozenset(signers[receipt.phone_number_id]))
            for receipt in receipts_in(body)
            if receipt.phone_number_id in signers
        ],
    )


# Past the signature the answer is 200: Meta disables a webhook that keeps failing, so what goes
# wrong after it is a line in the log. The one exception is a message another delivery is still
# reading: 503 keeps it on Meta's side until that reading is done or has died.
#
# Until 2026-11 the route did not do what these lines say. A message whose reading raised was a 500;
# and every claim of the body was written in the request's one transaction, so that 500 took back
# the claims of the messages before it, which were queued on their conversations already: Meta
# delivered the body again and they were answered twice.
async def receive_all(threads: Threads, delivery: Delivery) -> int:
    """Every message of a signed body onto its contact's conversation, every receipt said; how many messages."""
    unread = 0
    for inbound in delivery.messages:
        with survive("reading a WhatsApp message", inbound.message_id):
            if not await threads.receive(inbound):
                unread += 1
    for receipt in delivery.receipts:
        with survive("noting a WhatsApp receipt", receipt.message_id):
            await threads.note(receipt)
    if unread:
        raise ServiceUnavailable(f"{unread} of these messages are being read by another delivery: send it again")
    return len(delivery.messages)


# ── a contact Meta names by an id of one account ──


def meta_caller(channel: Channel, contact: str) -> str:
    """How a contact Meta names by an id of one account is said as a caller: `messenger:<PSID>`, `instagram:<IGSID>`."""
    return f"{channel.value}:{contact}"


# ── private ──


# A body an org's own app signed vouches for that org's number and for nothing else: without this,
# an org could sign a body that names another org's number as the one written to.
def _vouches(signed_for: frozenset[str] | None, phone_number_id: str, org: str, account: str | None) -> bool:
    return signed_for is None or (org in signed_for and account == phone_number_id)


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
