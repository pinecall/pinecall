"""Tests for a Facebook Page as an account: kept and read back, confirmed with Meta, what it answers at."""

import json

import httpx
import pytest

from runtime.enums import Channel
from runtime.exceptions import ValidationError
from runtime.telephony.service.accounts import read_carrier
from runtime.telephony.service.facebook_page import FacebookPage
from runtime.whatsapp.service.webhook import Subscription

ORG = "org_a"
PAGE = "1472943555898656"
INSTAGRAM = "17841400000000001"


def a_page(*, app_secret: str = "the app's secret", instagram_id: str | None = None) -> FacebookPage:
    """A Page of the org's, brought with its token and its app's secret."""
    return FacebookPage(
        org=ORG, page_id=PAGE, access_token="a page token", app_secret=app_secret, instagram_id=instagram_id
    )


def meta(*, refuses: bool = False, linked: bool = True, reads: bool = True) -> tuple[httpx.AsyncClient, list[str]]:
    """Meta's Graph for the Page: its conversations, its subscription, its name and Instagram where the token reads."""
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(f"{request.method} {request.url.path}")
        if refuses:
            return httpx.Response(400, json={"error": {"message": "Invalid OAuth access token."}})
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/conversations"):
            return httpx.Response(200, json={"data": []})
        if not reads:
            return httpx.Response(
                400, json={"error": {"message": "This endpoint requires the 'pages_read_engagement' permission"}}
            )
        linked_to = {"instagram_business_account": {"id": INSTAGRAM, "username": "pinecall.prueba"}} if linked else {}
        return httpx.Response(200, content=json.dumps({"id": PAGE, "name": "Pinecall Prueba", **linked_to}))

    return httpx.AsyncClient(transport=httpx.MockTransport(answer)), asked


def test_a_page_is_kept_and_read_back_as_it_was_with_its_instagram_account() -> None:
    kept = a_page(instagram_id=INSTAGRAM)
    again = read_carrier(ORG, kept.dump()["account"])
    assert again == kept
    assert kept.dump()["account"]["kind"] == "messenger"
    assert kept.describe() == {"instagram_id": INSTAGRAM}


def test_a_page_brought_again_with_a_token_alone_keeps_its_secret_and_its_instagram_account() -> None:
    kept = a_page(app_secret="").keep_from(a_page(instagram_id=INSTAGRAM))
    assert (kept.app_secret, kept.instagram_id) == ("the app's secret", INSTAGRAM)
    assert a_page(app_secret="a new one").keep_from(a_page()).app_secret == "a new one"


async def test_a_page_with_no_app_secret_is_refused_before_meta_is_asked() -> None:
    http, asked = meta()
    async with http:
        with pytest.raises(ValidationError, match="secret of your Meta app"):
            await a_page(app_secret="").verify(http)
    assert asked == []


async def test_a_page_confirmed_is_named_its_instagram_account_found_and_subscribed_to_its_app() -> None:
    http, asked = meta()
    async with http:
        confirmed = await a_page().confirm(http)
    assert (confirmed.instagram_id, confirmed.label) == (INSTAGRAM, "Pinecall Prueba")
    assert f"GET /v21.0/{PAGE}/conversations" in asked
    assert f"POST /v21.0/{PAGE}/subscribed_apps" in asked


async def test_a_dashboards_token_which_reads_nothing_of_the_page_keeps_the_page_as_it_was_brought() -> None:
    """Meta's dashboard gives a token with pages_messaging alone: it opens the conversations, and names nothing."""
    http, asked = meta(reads=False)
    async with http:
        confirmed = await a_page(instagram_id=INSTAGRAM).confirm(http)
    assert (confirmed.instagram_id, confirmed.label) == (INSTAGRAM, "")
    assert f"POST /v21.0/{PAGE}/subscribed_apps" in asked


async def test_a_token_meta_does_not_open_the_page_with_is_refused_in_metas_words() -> None:
    http, _ = meta(refuses=True)
    async with http:
        with pytest.raises(ValidationError, match="Invalid OAuth access token"):
            await a_page().confirm(http)


async def test_a_page_answers_messenger_at_its_id_and_instagram_at_its_linked_accounts() -> None:
    http, asked = meta()
    linked = a_page(instagram_id=INSTAGRAM)
    async with http:
        await linked.check_number(http, Channel.messenger, PAGE)
        await linked.check_number(http, Channel.instagram, INSTAGRAM)
        with pytest.raises(ValidationError, match="Messenger at the Page's id"):
            await linked.check_number(http, Channel.instagram, PAGE)
        with pytest.raises(ValidationError):
            await a_page().check_number(http, Channel.instagram, INSTAGRAM)
        with pytest.raises(ValidationError):
            await linked.check_number(http, Channel.whatsapp, PAGE)
    assert asked == [], "what a Page answers at is what was kept: Meta is not asked"


async def test_what_a_page_owns_is_itself_and_its_instagram_account() -> None:
    http, _ = meta()
    named = FacebookPage(
        org=ORG, page_id=PAGE, access_token="t", app_secret="s", label="Pinecall Prueba", instagram_id=INSTAGRAM
    )
    async with http:
        owned = await named.list_owned(http)
    assert [(one.number, one.name) for one in owned] == [
        (PAGE, "Pinecall Prueba"),
        (INSTAGRAM, "Pinecall Prueba · Instagram"),
    ]


async def test_bringing_a_page_gives_its_apps_webhook_the_message_fields_and_its_instagrams() -> None:
    """Verifying the callback in Meta's dashboard chooses no field, and then Meta delivers nothing."""
    asked: list[tuple[str, dict[str, str]]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append((f"{request.method} {request.url.path}", dict(request.url.params)))
        if request.url.path.endswith("/app"):
            return httpx.Response(200, json={"id": "1392113999481103"})
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        webhook = Subscription(callback_url="https://box.example/v1/whatsapp/webhook", verify_token="org_a.mark")
        await a_page(instagram_id=INSTAGRAM).subscribe_webhook(http, webhook)
    subscribed = [params for path, params in asked if path == "POST /v21.0/1392113999481103/subscriptions"]
    assert [(one["object"], one["callback_url"], one["verify_token"]) for one in subscribed] == [
        ("page", "https://box.example/v1/whatsapp/webhook", "org_a.mark"),
        ("instagram", "https://box.example/v1/whatsapp/webhook", "org_a.mark"),
    ]
    assert "messages" in subscribed[0]["fields"].split(",") and "messages" in subscribed[1]["fields"].split(",")
