"""Against a deployed gateway, by its name: the page, the widget, the refusals, as a browser and a server meet them."""

import os

import httpx
import pytest

URL = os.environ.get("PINECALL_URL", "")

deployed = pytest.mark.skipif(not URL, reason="PINECALL_URL: a deployed gateway's address, `make deploy`")


@deployed
async def test_the_console_is_served_at_any_path_and_never_cached() -> None:
    async with httpx.AsyncClient(base_url=URL, timeout=10) as browser:
        page = await browser.get("/calls/nobody")
    assert page.status_code == 200
    assert "<html" in page.text.lower()
    assert page.headers["cache-control"] == "no-store"


@deployed
async def test_the_widget_is_served_to_any_site() -> None:
    async with httpx.AsyncClient(base_url=URL, timeout=10) as browser:
        widget = await browser.get("/widget/pinecall-widget.js")
    assert widget.status_code == 200
    assert widget.headers["access-control-allow-origin"] == "*"


@deployed
async def test_an_endpoint_asked_without_a_key_asks_for_one() -> None:
    async with httpx.AsyncClient(base_url=URL, timeout=10) as nobody:
        refused = await nobody.get("/v1/agents")
    assert refused.status_code == 401
    assert refused.headers["www-authenticate"] == "Bearer"


@deployed
async def test_a_key_nobody_issued_is_refused_like_no_key() -> None:
    headers = {"Authorization": "Bearer pc_test_nobody"}
    async with httpx.AsyncClient(base_url=URL, timeout=10, headers=headers) as stranger:
        refused = await stranger.get("/v1/sessions")
    assert refused.status_code == 401


@deployed
async def test_a_path_under_the_api_nobody_declared_is_a_json_404() -> None:
    async with httpx.AsyncClient(base_url=URL, timeout=10) as anybody:
        answered = await anybody.get("/v1/nothing/here")
    assert answered.status_code == 404
    assert answered.json() == {"detail": "Not Found"}


@deployed
async def test_the_openapi_names_the_calls_endpoints() -> None:
    async with httpx.AsyncClient(base_url=URL, timeout=10) as anybody:
        schema = (await anybody.get("/openapi.json")).json()
    assert "/v1/calls" in schema["paths"]
    assert "/v1/tokens" in schema["paths"]
