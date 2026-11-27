"""Meta's Graph, asked for a Facebook Page: which it is, its Instagram account, a reply sent, who wrote."""

from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from runtime.enums import Channel
from runtime.exceptions import UpstreamError
from runtime.kit.text import cut_in_parts
from runtime.whatsapp.service.graph import LONGEST_MEDIA, TIMEOUT_S, VENDOR, Media, ask_graph

# Meta refuses a text longer than these: Messenger's 2000 characters, Instagram's 1000
# (developers.facebook.com/docs/messenger-platform/reference/send-api, …/instagram-messaging/features/send-message).
LONGEST_TEXT = {Channel.messenger: 2000, Channel.instagram: 1000}


@dataclass(frozen=True, slots=True)
class MetaPage:
    """A Facebook Page as Meta names it, and the Instagram account linked to it, when one is."""

    page_id: str
    name: str
    instagram_id: str | None
    instagram_name: str | None


class _Instagram(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    id: str
    username: str | None = None


class _Page(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    id: str
    name: str = ""
    instagram_business_account: _Instagram | None = None


class _Person(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


async def page_of(http: httpx.AsyncClient, token: str, page_id: str) -> MetaPage:
    """The Page the token opens under this id, and its Instagram account; Meta's refusal in its words."""
    fields = "id,name,instagram_business_account{id,username}"
    answer = await ask_graph(http, "GET", page_id, token, params={"fields": fields}, said_as="Messenger")
    try:
        page = _Page.model_validate_json(answer.content)
    except PydanticValidationError:
        raise UpstreamError(f"Messenger: Meta named no Page {page_id}", vendor=VENDOR) from None
    linked = page.instagram_business_account
    return MetaPage(
        page_id=page.id,
        name=page.name,
        instagram_id=None if linked is None else linked.id,
        instagram_name=None if linked is None else linked.username,
    )


# What the Page sends its app: the messages written to it, the buttons tapped, and where a reply stands
# (developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks).
SUBSCRIBED = "messages,messaging_postbacks,message_deliveries,message_reads"


async def subscribe_page(http: httpx.AsyncClient, token: str, page_id: str) -> None:
    """Subscribe the Page to the app its token is of, for its messages; Meta's refusal in its words."""
    params = {"subscribed_fields": SUBSCRIBED}
    await ask_graph(http, "POST", f"{page_id}/subscribed_apps", token, params=params, said_as="Messenger")


# One call for both: an Instagram professional account linked to the Page is written to through the
# Page, with the Page's token (developers.facebook.com/documentation/business-messaging/instagram-messaging).
async def send_text(http: httpx.AsyncClient, token: str, page_id: str, channel: Channel, to: str, text: str) -> None:
    """Send the text to the contact from the Page, on Messenger or on its Instagram; Meta's refusal in its words."""
    for part in cut_in_parts(text, LONGEST_TEXT[channel]):
        body = {"recipient": {"id": to}, "messaging_type": "RESPONSE", "message": {"text": part}}
        await ask_graph(http, "POST", f"{page_id}/messages", token, json=body, said_as=_said(channel))


# Meta shows the contact their message was seen, then that a reply is being written
# (developers.facebook.com/docs/messenger-platform/send-messages/sender-actions).
async def mark_seen(
    http: httpx.AsyncClient, token: str, page_id: str, channel: Channel, to: str, *, typing: bool
) -> None:
    """Tell the contact their message was seen, and that a reply is being written when one is."""
    for action in ("mark_seen", "typing_on") if typing else ("mark_seen",):
        body = {"recipient": {"id": to}, "sender_action": action}
        await ask_graph(http, "POST", f"{page_id}/messages", token, json=body, said_as=_said(channel))


# What a Page may read of who writes to it: their name on Messenger, their name or username on Instagram
# (developers.facebook.com/docs/messenger-platform/identity/user-profile).
async def name_of(http: httpx.AsyncClient, token: str, channel: Channel, contact: str) -> str | None:
    """The name the contact goes by at Meta, or None when Meta says none."""
    fields = "name,username" if channel is Channel.instagram else "first_name,last_name"
    answer = await ask_graph(http, "GET", contact, token, params={"fields": fields}, said_as=_said(channel))
    try:
        person = _Person.model_validate_json(answer.content)
    except PydanticValidationError:
        return None
    full = " ".join(part for part in (person.first_name, person.last_name) if part)
    return person.name or full or person.username or None


# A Page's attachment is a link to Meta's CDN, open to whoever holds it for a while: no token is sent.
async def read_attachment(http: httpx.AsyncClient, url: str) -> Media:
    """The audio a contact sent on Messenger or Instagram; refused when it is longer than a note."""
    try:
        answer = await http.get(url, timeout=TIMEOUT_S, follow_redirects=True)
    except httpx.HTTPError as silent:
        raise UpstreamError(
            f"Messenger: Meta did not hand the note ({type(silent).__name__})", vendor=VENDOR
        ) from silent
    if answer.is_error:
        raise UpstreamError("Messenger: Meta did not hand the note", vendor=VENDOR, answered=answer.status_code)
    if len(answer.content) > LONGEST_MEDIA:
        raise UpstreamError("Messenger: a voice note longer than is heard", vendor=VENDOR)
    return Media(data=answer.content, mime_type=answer.headers.get("content-type", ""))


def _said(channel: Channel) -> str:
    return "Instagram" if channel is Channel.instagram else "Messenger"
