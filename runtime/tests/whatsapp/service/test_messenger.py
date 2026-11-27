"""Tests for Meta's Graph asked for a Page: which it is, a reply sent and cut, seen and typing, who wrote."""

import json

import httpx
import pytest

from runtime.enums import Channel
from runtime.exceptions import UpstreamError
from runtime.whatsapp.service import messenger

PAGE = "1472943555898656"
INSTAGRAM = "17841400000000001"


class Graph:
    """Meta's Graph for one Page: what it was asked, and its answers."""

    def __init__(self, *, refusal: str | None = None, linked: bool = True) -> None:
        self.asked: list[tuple[str, str, dict[str, object]]] = []
        self.refusal = refusal
        self.linked = linked

    def answer(self, request: httpx.Request) -> httpx.Response:
        body: dict[str, object] = json.loads(request.content) if request.content else dict(request.url.params)
        self.asked.append((request.method, request.url.path, body))
        if self.refusal is not None:
            return httpx.Response(400, json={"error": {"message": self.refusal}})
        if request.method == "GET" and request.url.path.endswith(PAGE):
            linked = (
                {"instagram_business_account": {"id": INSTAGRAM, "username": "pinecall.prueba"}} if self.linked else {}
            )
            return httpx.Response(200, json={"id": PAGE, "name": "Pinecall Prueba", **linked})
        if request.method == "GET":
            fields = request.url.params.get("fields", "")
            said = (
                {"name": "Ana Ruiz", "username": "ana.r"}
                if "username" in fields
                else {"first_name": "Ana", "last_name": "Ruiz"}
            )
            return httpx.Response(200, json=said)
        if request.url.path.endswith("subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"recipient_id": "77", "message_id": "m_1"})


def client_of(graph: Graph) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(graph.answer))


async def test_a_page_is_named_with_the_instagram_account_linked_to_it() -> None:
    async with client_of(Graph()) as http:
        page = await messenger.page_of(http, "a page token", PAGE)
    assert (page.page_id, page.name, page.instagram_id, page.instagram_name) == (
        PAGE,
        "Pinecall Prueba",
        INSTAGRAM,
        "pinecall.prueba",
    )


async def test_a_page_with_no_instagram_account_says_none() -> None:
    async with client_of(Graph(linked=False)) as http:
        page = await messenger.page_of(http, "a page token", PAGE)
    assert page.instagram_id is None


@pytest.mark.parametrize("channel", [Channel.messenger, Channel.instagram])
async def test_a_reply_goes_from_the_page_to_the_contact_as_a_response(channel: Channel) -> None:
    graph = Graph()
    async with client_of(graph) as http:
        await messenger.send_text(http, "a page token", PAGE, channel, "77", "¡Hola Ana!")
    ((method, path, body),) = graph.asked
    assert (method, path) == ("POST", f"/v21.0/{PAGE}/messages")
    assert body == {"recipient": {"id": "77"}, "messaging_type": "RESPONSE", "message": {"text": "¡Hola Ana!"}}


@pytest.mark.parametrize(("channel", "longest"), [(Channel.messenger, 2000), (Channel.instagram, 1000)])
async def test_a_long_reply_goes_out_as_several_each_under_the_channels_ceiling(channel: Channel, longest: int) -> None:
    graph = Graph()
    words = " ".join(["palabra"] * 600)
    async with client_of(graph) as http:
        await messenger.send_text(http, "a page token", PAGE, channel, "77", words)
    parts = [str(body["message"]["text"]) for _, _, body in graph.asked]  # type: ignore[index]
    assert len(parts) > 1 and all(len(part) <= longest for part in parts)
    assert " ".join(parts).split() == words.split()


async def test_a_message_is_seen_and_typing_is_shown_only_when_asked() -> None:
    graph = Graph()
    async with client_of(graph) as http:
        await messenger.mark_seen(http, "a page token", PAGE, Channel.messenger, "77", typing=False)
        await messenger.mark_seen(http, "a page token", PAGE, Channel.messenger, "77", typing=True)
    assert [body["sender_action"] for _, _, body in graph.asked] == ["mark_seen", "mark_seen", "typing_on"]


async def test_a_contact_is_named_by_first_and_last_on_messenger_and_by_name_on_instagram() -> None:
    async with client_of(Graph()) as http:
        on_messenger = await messenger.name_of(http, "a page token", Channel.messenger, "77")
        on_instagram = await messenger.name_of(http, "a page token", Channel.instagram, "88")
    assert (on_messenger, on_instagram) == ("Ana Ruiz", "Ana Ruiz")


async def test_the_page_is_subscribed_to_its_app_for_its_messages() -> None:
    graph = Graph()
    async with client_of(graph) as http:
        await messenger.subscribe_page(http, "a page token", PAGE)
    ((method, path, params),) = graph.asked
    assert (method, path) == ("POST", f"/v21.0/{PAGE}/subscribed_apps")
    assert "messages" in str(params["subscribed_fields"]).split(",")


async def test_a_refusal_is_said_in_metas_words_as_the_channel_that_asked() -> None:
    async with client_of(Graph(refusal="(#10) This message is sent outside of allowed window.")) as http:
        with pytest.raises(UpstreamError, match=r"^Instagram: \(#10\) This message is sent outside of allowed window"):
            await messenger.send_text(http, "a page token", PAGE, Channel.instagram, "88", "hola")
