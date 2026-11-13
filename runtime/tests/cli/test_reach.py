"""`reach`: what a gateway asked at its name answers, each question's finding, and one that cannot be asked."""

import httpx

from runtime.cli.reach import ask_gateway
from tests.conftest import Gateway, needs_the_services

THE_QUESTIONS = ["console", "widget", "no key", "unknown key", "unknown path", "openapi"]
A_PAGE = "<!doctype html><html><body></body></html>"


def deployed(page_headers: dict[str, str]) -> httpx.AsyncClient:
    """A gateway as a deployment answers the six questions, its page served with these headers."""

    def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/widget/pinecall-widget.js":
            return httpx.Response(200, text="export {}", headers={"access-control-allow-origin": "*"})
        if path in ("/v1/agents", "/v1/sessions"):
            return httpx.Response(401, json={"detail": "a key"}, headers={"www-authenticate": "Bearer"})
        if path == "/openapi.json":
            return httpx.Response(200, json={"paths": {"/v1/calls": {}, "/v1/tokens": {}}})
        if path.startswith("/v1/"):
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(200, text=A_PAGE, headers=page_headers)

    return httpx.AsyncClient(base_url="https://a.gateway", transport=httpx.MockTransport(answer))


async def test_a_gateway_that_answers_as_a_deployment_does_is_found_well() -> None:
    """Six questions, in their order, and nothing wrong with any."""
    async with deployed({"cache-control": "no-store"}) as http:
        found = await ask_gateway(http)
    assert [finding.name for finding in found] == THE_QUESTIONS
    assert [finding.trouble for finding in found] == [None] * 6


async def test_a_page_a_browser_may_keep_is_named_and_the_rest_is_still_asked() -> None:
    """A console served with no `no-store` is that line's trouble, in words; the five others are well."""
    async with deployed({}) as http:
        found = {finding.name: finding.trouble for finding in await ask_gateway(http)}
    assert found.pop("console") == "cache-control is not set, not no-store"
    assert set(found.values()) == {None}


async def test_a_widget_whose_modules_are_not_served_is_named_by_the_first_one_missing() -> None:
    """The widget's first file imports the ones beside it: one that answers 404 is the widget's trouble."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/widget/pinecall-widget.js":
            said = 'import { Panel } from "./panel.js";\nimport { STYLE } from "./styles.js";\n'
            return httpx.Response(200, text=said, headers={"access-control-allow-origin": "*"})
        if request.url.path == "/widget/panel.js":
            return httpx.Response(200, text="export {}")
        return httpx.Response(404, json={"detail": "Not Found"})

    async with httpx.AsyncClient(base_url="https://a.gateway", transport=httpx.MockTransport(answer)) as http:
        found = {finding.name: finding.trouble for finding in await ask_gateway(http)}
    assert found["widget"] == "/widget/pinecall-widget.js imports ./styles.js, and /widget/styles.js answered 404"


# The suite's gateway is a checkout's: no console and no widget are built into it, which is what
# the verb must say of it, while what the API itself answers is found well.
@needs_the_services
async def test_a_gateway_with_no_console_built_is_told_from_one_that_serves_it(gateway: Gateway) -> None:
    """The served gateway's own answers: its API well, its page and its widget missing."""
    found = {finding.name: finding.trouble for finding in await ask_gateway(gateway.http)}
    assert found == {
        "console": "/calls/nobody answered 404, and no page",
        "widget": "/widget/pinecall-widget.js answered 404",
        "no key": None,
        "unknown key": None,
        "unknown path": None,
        "openapi": None,
    }


async def test_a_gateway_that_is_not_there_is_six_troubles_and_never_a_traceback() -> None:
    """Nobody answering at the address is said by every line."""
    async with httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=2.0) as http:
        found = await ask_gateway(http)
    assert [finding.name for finding in found] == THE_QUESTIONS
    assert all(finding.trouble for finding in found)
