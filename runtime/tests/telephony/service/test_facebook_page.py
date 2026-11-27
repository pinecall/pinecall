"""Tests for a Facebook Page as an account: kept and read back, confirmed with Meta, what it answers at."""

import json

import httpx
import pytest

from runtime.enums import Channel
from runtime.exceptions import ValidationError
from runtime.telephony.service.accounts import read_carrier
from runtime.telephony.service.facebook_page import FacebookPage

ORG = "org_a"
PAGE = "1472943555898656"
INSTAGRAM = "17841400000000001"


def a_page(*, app_secret: str = "the app's secret", instagram_id: str | None = None) -> FacebookPage:
    """A Page of the org's, brought with its token and its app's secret."""
    return FacebookPage(
        org=ORG, page_id=PAGE, access_token="a page token", app_secret=app_secret, instagram_id=instagram_id
    )


def meta(*, refuses: bool = False, linked: bool = True) -> tuple[httpx.AsyncClient, list[str]]:
    """Meta's Graph for the Page: its name and Instagram on GET, the app's subscription on POST; what it was asked."""
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(f"{request.method} {request.url.path}")
        if refuses:
            return httpx.Response(400, json={"error": {"message": "Invalid OAuth access token."}})
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        linked_to = {"instagram_business_account": {"id": INSTAGRAM, "username": "pinecall.prueba"}} if linked else {}
        return httpx.Response(200, content=json.dumps({"id": PAGE, "name": "Pinecall Prueba", **linked_to}))

    return httpx.AsyncClient(transport=httpx.MockTransport(answer)), asked


def test_a_page_is_kept_and_read_back_as_it_was_with_its_instagram_account() -> None:
    kept = a_page(instagram_id=INSTAGRAM)
    again = read_carrier(ORG, kept.dump()["account"])
    assert again == kept
    assert kept.dump()["account"]["kind"] == "messenger"
    assert kept.describe() == {"instagram_id": INSTAGRAM}


def test_a_page_brought_again_with_no_secret_keeps_the_one_it_had() -> None:
    assert a_page(app_secret="").keep_from(a_page()).app_secret == "the app's secret"
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
        confirmed = await a_page().confirmed(http)
    assert (confirmed.instagram_id, confirmed.label) == (INSTAGRAM, "Pinecall Prueba")
    assert f"POST /v21.0/{PAGE}/subscribed_apps" in asked


async def test_a_token_meta_does_not_open_the_page_with_is_refused_in_metas_words() -> None:
    http, _ = meta(refuses=True)
    async with http:
        with pytest.raises(ValidationError, match="Invalid OAuth access token"):
            await a_page().confirmed(http)


async def test_a_page_answers_messenger_at_its_id_and_instagram_at_its_linked_accounts() -> None:
    http, _ = meta()
    async with http:
        await a_page().check_number(http, Channel.messenger, PAGE)
        await a_page().check_number(http, Channel.instagram, INSTAGRAM)
        with pytest.raises(ValidationError, match="Messenger at the Page's id"):
            await a_page().check_number(http, Channel.instagram, PAGE)
        with pytest.raises(ValidationError):
            await a_page().check_number(http, Channel.whatsapp, PAGE)


async def test_what_a_page_owns_is_itself_and_its_instagram_account() -> None:
    http, _ = meta()
    async with http:
        owned = await a_page().list_owned(http)
    assert [(one.number, one.name) for one in owned] == [(PAGE, "Pinecall Prueba"), (INSTAGRAM, "@pinecall.prueba")]
