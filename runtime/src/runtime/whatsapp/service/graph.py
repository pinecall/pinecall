"""Meta's Graph, asked for a WhatsApp number: which number it is, a reply sent, a message read, a voice note's audio."""

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from runtime.exceptions import UpstreamError
from runtime.kit.text import cut_in_parts
from runtime.whatsapp.service.webhook import Inbound

GRAPH = "https://graph.facebook.com/v21.0"
# Who an UpstreamError of this module names.
VENDOR = "meta"
TIMEOUT_S = 10.0
# Meta refuses a text body longer than this (developers.facebook.com/docs/whatsapp/cloud-api/reference/messages).
LONGEST_TEXT = 4096
# Meta keeps a voice note under 16 MB; one this long is minutes of speech, more than a chat's note.
LONGEST_MEDIA = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MetaNumber:
    """The number a WhatsApp account answers at, in E.164, and its name at Meta."""

    number: str
    verified_name: str


@dataclass(frozen=True, slots=True)
class Media:
    """What a contact sent that is no text: its bytes, and the type Meta names them."""

    data: bytes
    mime_type: str


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


class _Kept(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    url: str
    mime_type: str = ""
    file_size: int = 0


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
    # A reply longer than Meta takes goes out as several.
    for part in cut_in_parts(text, LONGEST_TEXT):
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": inbound.wa_id,
            "type": "text",
            "text": {"body": part, "preview_url": False},
        }
        await _ask(http, "POST", f"{inbound.phone_number_id}/messages", token, json=body)


# One call does both: Meta shows the contact their message was read (the two blue ticks), and,
# asked to, that a reply is being written, until one goes out or 25 seconds pass
# (developers.facebook.com/documentation/business-messaging/whatsapp/typing-indicators).
async def mark_read(http: httpx.AsyncClient, token: str, inbound: Inbound, *, typing: bool) -> None:
    """Tell the contact their message was read, and that a reply is being written when one is."""
    body: dict[str, Any] = {"messaging_product": "whatsapp", "status": "read", "message_id": inbound.message_id}
    if typing:
        body["typing_indicator"] = {"type": "text"}
    await _ask(http, "POST", f"{inbound.phone_number_id}/messages", token, json=body)


# Meta names where the bytes are, and gives them only to the token that asked: two requests.
async def read_media(http: httpx.AsyncClient, token: str, media_id: str) -> Media:
    """The audio a contact sent, as Meta keeps it; refused when it is longer than a note."""
    answer = await _ask(http, "GET", media_id, token)
    try:
        kept = _Kept.model_validate_json(answer.content)
    except PydanticValidationError:
        raise UpstreamError(
            f"WhatsApp: Meta named no file for {media_id}", vendor=VENDOR, answered=answer.status_code
        ) from None
    if kept.file_size > LONGEST_MEDIA:
        raise UpstreamError(f"WhatsApp: a voice note of {kept.file_size} bytes is longer than is heard", vendor=VENDOR)
    data = await _fetch(http, kept.url, token)
    # Meta's own count is not trusted over the bytes it sent.
    if len(data.content) > LONGEST_MEDIA:
        raise UpstreamError("WhatsApp: a voice note longer than is heard", vendor=VENDOR)
    return Media(data=data.content, mime_type=kept.mime_type or data.headers.get("content-type", ""))


# ── private ──


async def _ask(
    http: httpx.AsyncClient,
    method: str,
    path: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    return await _fetch(http, f"{GRAPH}/{path}", token, method=method, params=params, json=json)


# The one place Meta is asked, and its no translated: a refusal in Meta's own words, with the status
# it answered; its silence and its own failures as what asking again may mend.
async def _fetch(
    http: httpx.AsyncClient,
    url: str,
    token: str,
    *,
    method: str = "GET",
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    try:
        answer = await http.request(
            method, url, params=params, json=json, headers={"authorization": f"Bearer {token}"}, timeout=TIMEOUT_S
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
