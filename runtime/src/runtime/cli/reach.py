"""`reach`: a gateway asked at its name what a browser and a server ask first; the exit is 1 when one is wrong."""

import re
from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
import typer

from runtime.cli.command import context_of, verb
from runtime.cli.doctor import Finding, say_findings

WAITED_S = 10.0
OK, UNAUTHORIZED, NOT_THERE = 200, 401, 404
A_PAGE = "/calls/nobody"
THE_WIDGET = "/widget/pinecall-widget.js"
# A module the widget imports from beside itself: `from "./styles.js"`.
ITS_OWN_MODULE = re.compile(r'from\s+"\./([\w.-]+\.js)"')
A_KEY_NOBODY_ISSUED = {"Authorization": "Bearer pc_test_nobody"}
NOT_FOUND = {"detail": "Not Found"}
ALWAYS_THERE = ("/v1/calls", "/v1/tokens")

type Ask = Callable[[httpx.AsyncClient], Awaitable[str | None]]


# What `doctor` cannot see from inside: the gateway as it is reached, through whatever stands in
# front of it. `make deploy` ends in it, run in the new release's own pod. Until 2026-11-12 these
# were six tests of the suite, run on the operator's machine with the suite's tools.
@verb
async def reach(
    ctx: typer.Context,
    address: Annotated[str | None, typer.Argument(metavar="[<url>]", help="The box's own name, unset.")] = None,
) -> int:
    """Ask the gateway at <url> what a browser and a server ask it first, a line each."""
    context = context_of(ctx)
    async with httpx.AsyncClient(base_url=address or context.settings.base_url, timeout=WAITED_S) as http:
        return say_findings(context, await ask_gateway(http))


# A question that cannot be asked, or whose answer does not read, is that question's trouble: the
# ones after it are asked all the same.
async def ask_gateway(http: httpx.AsyncClient) -> list[Finding]:
    """What each question found, in the order they are asked."""
    findings: list[Finding] = []
    for name, ask in QUESTIONS:
        try:
            findings.append(Finding(name, await ask(http)))
        except (httpx.HTTPError, ValueError) as unanswered:
            findings.append(Finding(name, str(unanswered) or type(unanswered).__name__))
    return findings


# ── private ──


# Any path is the console's, and a browser must never keep it: a cached page is an old console.
async def _ask_console(http: httpx.AsyncClient) -> str | None:
    page = await http.get(A_PAGE)
    if page.status_code != OK or "<html" not in page.text.lower():
        return f"{A_PAGE} answered {page.status_code}, and no page"
    return _wrong_header(page, "cache-control", "no-store")


# The widget is modules: its first file imports the ones beside it, and a browser asks for each. Until
# 2026-11-13 this asked for the first alone, and a gateway that served no other was found well.
async def _ask_widget(http: httpx.AsyncClient) -> str | None:
    widget = await http.get(THE_WIDGET)
    if widget.status_code != OK:
        return f"{THE_WIDGET} answered {widget.status_code}"
    for module in sorted(set(ITS_OWN_MODULE.findall(widget.text))):
        beside = THE_WIDGET.rsplit("/", 1)[0] + "/" + module
        imported = await http.get(beside)
        if imported.status_code != OK:
            return f"{THE_WIDGET} imports ./{module}, and {beside} answered {imported.status_code}"
    return _wrong_header(widget, "access-control-allow-origin", "*")


async def _ask_without_a_key(http: httpx.AsyncClient) -> str | None:
    refused = await http.get("/v1/agents")
    if refused.status_code != UNAUTHORIZED:
        return f"/v1/agents with no key answered {refused.status_code}, not 401"
    return _wrong_header(refused, "www-authenticate", "Bearer")


async def _ask_with_an_unknown_key(http: httpx.AsyncClient) -> str | None:
    refused = await http.get("/v1/sessions", headers=A_KEY_NOBODY_ISSUED)
    if refused.status_code != UNAUTHORIZED:
        return f"/v1/sessions with a key nobody issued answered {refused.status_code}, not 401"
    return None


# A path of the API nobody declared is the API's to refuse, as JSON: never the console's page.
async def _ask_an_unknown_path(http: httpx.AsyncClient) -> str | None:
    answered = await http.get("/v1/nothing/here")
    if answered.status_code != NOT_THERE or answered.json() != NOT_FOUND:
        return f"/v1/nothing/here answered {answered.status_code}, and not the API's own 404"
    return None


async def _ask_the_openapi(http: httpx.AsyncClient) -> str | None:
    answered = await http.get("/openapi.json")
    if answered.status_code != OK:
        return f"/openapi.json answered {answered.status_code}"
    missing = [path for path in ALWAYS_THERE if path not in answered.json().get("paths", {})]
    return f"/openapi.json names no {', '.join(missing)}" if missing else None


def _wrong_header(answer: httpx.Response, name: str, wanted: str) -> str | None:
    said = answer.headers.get(name)
    return None if said == wanted else f"{name} is {said or 'not set'}, not {wanted}"


QUESTIONS: tuple[tuple[str, Ask], ...] = (
    ("console", _ask_console),
    ("widget", _ask_widget),
    ("no key", _ask_without_a_key),
    ("unknown key", _ask_with_an_unknown_key),
    ("unknown path", _ask_an_unknown_path),
    ("openapi", _ask_the_openapi),
)
