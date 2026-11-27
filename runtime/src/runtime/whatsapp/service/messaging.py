"""Meta's Messenger Platform on the webhook: a Page's and its Instagram's messages, receipts, and who signed them."""

import dataclasses
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from runtime.enums import Channel
from runtime.exceptions import Forbidden
from runtime.whatsapp.service.webhook import FEW_NUMBERS, Delivery, Inbound, OwnApp, Receipt, is_signed

# A Page's body and its Instagram account's are Meta's Messenger Platform: `entry[].messaging[]`,
# where WhatsApp's is `entry[].changes[]` (developers.facebook.com/documentation/business-messaging/
# messenger-platform/webhooks, …/instagram-messaging/webhooks).
MESSAGING_OBJECTS = {"page": Channel.messenger, "instagram": Channel.instagram}


# Meta adds fields without notice, and a webhook answered 4xx for long is disabled: every model ignores
# what it does not know.
class _Lenient(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class _Party(_Lenient):
    id: str = ""


class _Link(_Lenient):
    url: str | None = None


class _Attachment(_Lenient):
    type: str = ""
    payload: _Link | None = None


class _Written(_Lenient):
    mid: str = ""
    text: str | None = None
    attachments: list[_Attachment] = Field(default_factory=list[_Attachment])
    is_echo: bool = False


class _Postback(_Lenient):
    mid: str | None = None
    title: str | None = None
    payload: str | None = None


class _Delivered(_Lenient):
    mids: list[str] = Field(default_factory=list[str])


class _Seen(_Lenient):
    mid: str | None = None


class _Event(_Lenient):
    sender: _Party | None = None
    timestamp: int = 0
    message: _Written | None = None
    postback: _Postback | None = None
    delivery: _Delivered | None = None
    read: _Seen | None = None


class _Thread(_Lenient):
    id: str = ""
    messaging: list[_Event] = Field(default_factory=list[_Event])


class _Messaging(_Lenient):
    object: str = ""
    entry: list[_Thread] = Field(default_factory=list[_Thread])


def is_a_page_body(body: bytes) -> bool:
    """Whether the body is the Messenger Platform's (a Page's, or its Instagram account's), not WhatsApp's."""
    return _envelope_of(body) is not None


def accounts_named_in(body: bytes) -> set[str]:
    """The Pages or Instagram accounts a Messenger Platform body names; none for any other body, or too many."""
    parsed = _envelope_of(body)
    if parsed is None:
        return set()
    named = {entry.id for entry in parsed.entry if entry.id}
    return named if len(named) <= FEW_NUMBERS else set()


# Our own sends come back as echoes (Instagram's inside `messages`): they are the agent's, and not read.
def messaging_in(body: bytes, answered_from: dict[str, str]) -> Delivery:
    """A Page's or its Instagram's messages and receipts, each on the Page it is answered from."""
    parsed = _envelope_of(body)
    if parsed is None:
        return Delivery([], [])
    channel = MESSAGING_OBJECTS[parsed.object]
    messages: list[Inbound] = []
    receipts: list[Receipt] = []
    for entry in parsed.entry:
        page = answered_from.get(entry.id)
        if page is None:
            continue
        for event in entry.messaging:
            contact = "" if event.sender is None else event.sender.id
            if not contact:
                continue
            said = _words_of(event)
            if said is not None:
                kind, text, mid = said
                note = _note_in(event)
                messages.append(
                    Inbound(
                        number=entry.id,
                        phone_number_id=page,
                        wa_id=contact,
                        name=None,
                        message_id=mid,
                        kind=kind,
                        text=text,
                        media_id=note,
                        channel=channel,
                    )
                )
            seen = [] if event.delivery is None else [(mid, "delivered") for mid in event.delivery.mids]
            if event.read is not None and event.read.mid:
                seen.append((event.read.mid, "read"))
            receipts += [
                Receipt(
                    number=entry.id, phone_number_id=page, wa_id=contact, message_id=mid, status=status, channel=channel
                )
                for mid, status in seen
            ]
    return Delivery(messages, receipts)


def _words_of(event: _Event) -> tuple[str, str | None, str] | None:
    written = event.message
    if written is not None and not written.is_echo and written.mid:
        kinds = [attachment.type for attachment in written.attachments if attachment.type]
        return ("text" if written.text else (kinds[0] if kinds else "unsupported"), written.text, written.mid)
    tapped = event.postback
    if tapped is not None and (tapped.title or tapped.payload):
        return ("button", tapped.title or tapped.payload, tapped.mid or f"postback.{event.timestamp}")
    return None


# A voice note's link to Meta's CDN, heard before the message is read (`Inbound.media_id`).
def _note_in(event: _Event) -> str | None:
    written = event.message
    if written is None:
        return None
    return next((one.payload.url for one in written.attachments if one.type == "audio" and one.payload), None)


def _envelope_of(body: bytes) -> _Messaging | None:
    try:
        parsed = _Messaging.model_validate_json(body)
    except PydanticValidationError:
        return None
    return parsed if parsed.object in MESSAGING_OBJECTS else None


# Only an org's own app signs a Page's body: the box answers no Page of its own.
def read_signed(own: Sequence[OwnApp], body: bytes, header: str | None) -> Delivery:
    """What a Page's or its Instagram's body carries, when an org's own app signed it; Forbidden for any other."""
    signers: dict[str, set[str]] = {}
    pages: dict[str, str] = {}
    for app in own:
        if is_signed(app.app_secret, body, header):
            signers.setdefault(app.phone_number_id, set()).add(app.org)
            pages[app.phone_number_id] = app.answers_from or app.phone_number_id
    if not signers:
        raise Forbidden(
            "the body carries the signature of no Meta app an org brought with its Page "
            "(`pinecall carriers add messenger` asks for the app's secret)"
        )
    found = messaging_in(body, pages)
    return Delivery(
        [dataclasses.replace(message, signed_for=frozenset(signers[message.number])) for message in found.messages],
        [dataclasses.replace(receipt, signed_for=frozenset(signers[receipt.number])) for receipt in found.receipts],
    )
