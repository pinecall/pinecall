"""A Studio tool's request to the business's API, held to the public internet: what the model reads back."""

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from runtime.kit.dns import Resolve, all_public, is_local_name, resolve
from runtime.studio.service.definition import A_PATH_PARAM, A_PLACEHOLDER, SECRETS
from runtime.studio.service.prompt import fill
from runtime.wire.studio import Header, HttpTool, Scalar

# What the model reads of an answer: past this it is cut, and the model is told so.
LARGEST_ANSWER = 256 * 1024
NOT_PUBLIC = "{host} is not on the public internet: Studio reaches public https addresses alone"
NO_ANSWER = "{tool} did not answer within {seconds:g}s"
UNREACHABLE = "{tool} could not be reached: {why}"
REFUSED = "{tool} answered {status}"
CUT = "[the answer was cut at {limit} KB]"
# What stands where an answer repeated a secret's value.
MASK = "***"


@dataclass(frozen=True, slots=True)
class Answer:
    """What came back: the status (None when nothing did), the body, or why not, and how long it took."""

    status: int | None
    body: Any
    error: str | None
    duration_ms: int


@dataclass(frozen=True, slots=True)
class Request:
    """One request, filled: the method, the URL, the headers, and the query or the JSON body."""

    method: str
    url: str
    headers: dict[str, str]
    query: dict[str, Any]
    body: dict[str, Any] | None
    # Every way the secrets in the headers may be written back, longest first: an answer that repeats
    # one (an API that echoes what it was sent) never reaches the model, the log or the console.
    secrets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Fetcher:
    """What a request leaves the box through: the process's client, and how a name is resolved."""

    http: httpx.AsyncClient
    resolver: Resolve = resolve


def fill_request(tool: HttpTool, arguments: Mapping[str, Any], values: Mapping[str, Any]) -> Request:
    """The tool's request with the model's arguments: the path's own first, the rest and the fixed fields after."""
    plain = {key: value for key, value in values.items() if key != SECRETS}
    url = fill(tool.url, plain)
    in_the_path = set(A_PATH_PARAM.findall(url))
    url = A_PATH_PARAM.sub(lambda found: quote(str(arguments.get(found.group(1), "")), safe=""), url)
    rest = {name: value for name, value in arguments.items() if name not in in_the_path and value is not None}
    known = {param.name for param in tool.params}
    rest = {name: value for name, value in rest.items() if name in known}
    # The fixed fields go over the model's: what the definition set is never the model's to change.
    rest |= {item.name: _fill_fixed(item.value, plain) for item in tool.fixed}
    headers = _fill_headers(tool.headers, values)
    hidden = _list_secrets_in(tool.headers, values)
    if tool.method == "GET" or tool.method == "DELETE":
        return Request(tool.method, url, headers, rest, None, hidden)
    return Request(tool.method, url, headers, {}, rest, hidden)


def fill_post(url: str, headers: list[Header], body: dict[str, Any], values: Mapping[str, Any]) -> Request:
    """A POST of data collection's results to the URL the definition names."""
    return Request("POST", url, _fill_headers(headers, values), {}, body, _list_secrets_in(headers, values))


# The name is resolved and checked, then the request goes to the name: every URL is https and its
# certificate must match the name, which is what holds it to the address a public name has.
async def send(fetcher: Fetcher, request: Request, *, name: str, timeout_s: float) -> Answer:
    """Send the request once, if its host is public; the answer, JSON when it is JSON."""
    started = time.monotonic()
    host = urlsplit(request.url).hostname or ""
    try:
        addresses = [] if is_local_name(host) else await asyncio.to_thread(fetcher.resolver, host)
    except OSError as unresolved:
        return Answer(None, None, UNREACHABLE.format(tool=name, why=unresolved), _since(started))
    if not all_public(addresses):
        return Answer(None, None, NOT_PUBLIC.format(host=host), _since(started))
    try:
        answered = await fetcher.http.request(
            request.method,
            request.url,
            params=request.query or None,
            json=request.body,
            headers=request.headers,
            timeout=timeout_s,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        return Answer(None, None, NO_ANSWER.format(tool=name, seconds=timeout_s), _since(started))
    except httpx.HTTPError as failed:
        return Answer(None, None, UNREACHABLE.format(tool=name, why=failed), _since(started))
    body = _read_body(answered, request.secrets)
    error = None if answered.is_success else REFUSED.format(tool=name, status=answered.status_code)
    return Answer(answered.status_code, body, error, _since(started))


def _fill_fixed(value: Scalar, values: Mapping[str, Any]) -> Any:
    return fill(value, values) if isinstance(value, str) else value


def _fill_headers(headers: list[Header], values: Mapping[str, Any]) -> dict[str, str]:
    return {header.name: fill(header.value, values) for header in headers}


# The values of the secrets the headers name, as text and as JSON writes it (a quote or a non-ASCII
# character in a secret is escaped in a body that echoes it), the longest first so a secret that holds
# another is masked whole. A secret set to nothing has nothing to hide.
def _list_secrets_in(headers: list[Header], values: Mapping[str, Any]) -> tuple[str, ...]:
    held: Mapping[str, Any] = values.get(SECRETS) or {}
    written: set[str] = set()
    for header in headers:
        for path in A_PLACEHOLDER.findall(header.value):
            head, _, name = path.partition(".")
            value = held.get(name) if head == SECRETS else None
            if isinstance(value, str) and value:
                written |= {value, json.dumps(value)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1]}
    return tuple(sorted(written, key=len, reverse=True))


# The secrets' values are taken out of the text, by value and whatever field they came back in, before
# it is cut or read as JSON: a cut through one would leave half of it, and a key may be the echo.
# Read whole and cut after: httpx has read it already, and the cap is on what the model reads.
def _read_body(answered: httpx.Response, secrets: tuple[str, ...]) -> Any:
    text = answered.text
    for secret in secrets:
        text = text.replace(secret, MASK)
    if len(text) > LARGEST_ANSWER:
        return f"{text[:LARGEST_ANSWER]}\n{CUT.format(limit=LARGEST_ANSWER >> 10)}"
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def _since(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
