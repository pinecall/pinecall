"""A Studio tool's request to the business's API, held to the public internet: what the model reads back."""

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from pinecall_runtime.kit.dns import Address, all_public, is_local_name, resolve
from pinecall_runtime.studio.schemas import Header, HttpTool
from pinecall_runtime.studio.service.definition import A_PATH_PARAM, rendered

# What the model reads of an answer: past this it is cut, and the model is told so.
LARGEST_ANSWER = 256 * 1024
NOT_PUBLIC = "{host} is not on the public internet: Studio reaches public https addresses alone"
NO_ANSWER = "{tool} did not answer within {seconds:g}s"
UNREACHABLE = "{tool} could not be reached: {why}"
REFUSED = "{tool} answered {status}"
CUT = "[the answer was cut at {limit} KB]"

# Resolving is the box's DNS: a test hands its own, so a fake API on loopback is reachable there.
type Resolve = Callable[[str], list[Address]]


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


def request_of(tool: HttpTool, arguments: Mapping[str, Any], values: Mapping[str, Any]) -> Request:
    """The tool's request with the model's arguments: the path's own first, the rest the query or the body."""
    url = rendered(tool.url, {key: value for key, value in values.items() if key != "secrets"})
    in_the_path = set(A_PATH_PARAM.findall(url))
    url = A_PATH_PARAM.sub(lambda found: quote(str(arguments.get(found.group(1), "")), safe=""), url)
    rest = {name: value for name, value in arguments.items() if name not in in_the_path and value is not None}
    declared = {param.name for param in tool.params}
    rest = {name: value for name, value in rest.items() if name in declared}
    headers = _headers(tool.headers, values)
    if tool.method == "GET" or tool.method == "DELETE":
        return Request(tool.method, url, headers, rest, None)
    return Request(tool.method, url, headers, {}, rest)


def post_of(url: str, headers: list[Header], body: dict[str, Any], values: Mapping[str, Any]) -> Request:
    """A POST of data collection's results to the URL the definition names."""
    return Request("POST", url, _headers(headers, values), {}, body)


async def send(
    http: httpx.AsyncClient, request: Request, *, name: str, timeout_s: float, resolver: Resolve = resolve
) -> Answer:
    """Send the request once, if its host is public; the answer, JSON when it is JSON."""
    started = time.monotonic()
    host = urlsplit(request.url).hostname or ""
    try:
        addresses = [] if is_local_name(host) else await asyncio.to_thread(resolver, host)
    except OSError as unresolved:
        return Answer(None, None, UNREACHABLE.format(tool=name, why=unresolved), _since(started))
    if not all_public(addresses):
        return Answer(None, None, NOT_PUBLIC.format(host=host), _since(started))
    try:
        answered = await http.request(
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
    body = _body(answered)
    error = None if answered.is_success else REFUSED.format(tool=name, status=answered.status_code)
    return Answer(answered.status_code, body, error, _since(started))


def _headers(headers: list[Header], values: Mapping[str, Any]) -> dict[str, str]:
    return {header.name: rendered(header.value, values) for header in headers}


# Read whole and cut after: httpx has read it already, and the cap is on what the model reads.
def _body(answered: httpx.Response) -> Any:
    text = answered.text
    if len(text) > LARGEST_ANSWER:
        return f"{text[:LARGEST_ANSWER]}\n{CUT.format(limit=LARGEST_ANSWER >> 10)}"
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def _since(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
