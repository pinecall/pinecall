"""A Studio tool's request: built from the model's arguments, sent to the public internet alone, read back."""

import ipaddress
import json

import httpx

from pinecall_runtime.kit.dns import Address
from pinecall_runtime.studio.schemas import Header, HttpTool
from pinecall_runtime.studio.service import fetch

PUBLIC: list[Address] = [ipaddress.ip_address("93.184.216.34")]
PRIVATE: list[Address] = [ipaddress.ip_address("10.0.0.7")]


def lookup(method: str = "GET") -> HttpTool:
    """A lookup by path and query, its key in a header."""
    return HttpTool.model_validate(
        {
            "name": "slots",
            "description": "Free slots.",
            "method": method,
            "url": "https://agenda.example.com/doctors/{doctor}/slots",
            "headers": [{"name": "Authorization", "value": "Bearer {{secrets.KEY}}"}],
            "params": [{"name": "doctor"}, {"name": "day"}, {"name": "late", "type": "boolean", "required": False}],
        }
    )


VALUES = {"call": {"from": "+1555"}, "secrets": {"KEY": "s3cret"}}


def test_a_get_puts_the_path_parameter_in_the_path_and_the_rest_in_the_query() -> None:
    """The doctor in the path, encoded; the day in the query; the secret in the header; nothing invented."""
    built = fetch.request_of(lookup(), {"doctor": "vidal/1", "day": "2026-10-21", "invented": 1}, VALUES)
    assert built.url == "https://agenda.example.com/doctors/vidal%2F1/slots"
    assert built.query == {"day": "2026-10-21"}
    assert built.body is None
    assert built.headers == {"Authorization": "Bearer s3cret"}


def test_a_post_sends_the_rest_as_its_json_body() -> None:
    """A write carries its arguments as JSON, never in the URL."""
    built = fetch.request_of(lookup("POST"), {"doctor": "vidal", "day": "2026-10-21", "late": True}, VALUES)
    assert built.query == {}
    assert built.body == {"day": "2026-10-21", "late": True}


async def test_an_answer_is_read_as_json_and_a_refusal_says_its_status() -> None:
    """200 with JSON is the body; 404 is an error naming the status, with the body kept."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params.get("day") == "never":
            return httpx.Response(404, json={"detail": "no such day"})
        return httpx.Response(200, json={"slots": [{"id": "s1"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        good = fetch.request_of(lookup(), {"doctor": "vidal", "day": "2026-10-21"}, VALUES)
        answered = await fetch.send(http, good, name="slots", timeout_s=5, resolver=lambda _: PUBLIC)
        bad = fetch.request_of(lookup(), {"doctor": "vidal", "day": "never"}, VALUES)
        refused = await fetch.send(http, bad, name="slots", timeout_s=5, resolver=lambda _: PUBLIC)
    assert answered.status == 200 and answered.body == {"slots": [{"id": "s1"}]} and answered.error is None
    assert refused.status == 404 and refused.error == "slots answered 404" and refused.body == {"detail": "no such day"}
    assert seen[0].headers["authorization"] == "Bearer s3cret"


async def test_a_host_on_a_private_address_or_a_local_name_is_never_reached() -> None:
    """The fence: a name resolving to the cluster's network, or `.svc`, is refused before any request."""
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        inside = fetch.Request("GET", "https://agenda.example.com/x", {}, {}, None)
        private = await fetch.send(http, inside, name="x", timeout_s=5, resolver=lambda _: PRIVATE)
        local = fetch.Request("GET", "https://postgres.default.svc/x", {}, {}, None)
        named = await fetch.send(http, local, name="x", timeout_s=5, resolver=lambda _: PUBLIC)
    assert private.error is not None and "public internet" in private.error
    assert named.error is not None and "public internet" in named.error
    assert sent == []


async def test_a_redirect_is_not_followed_and_a_long_answer_is_cut() -> None:
    """A 302 is an answer, not a second request; past the ceiling the model reads it cut."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/moved":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        return httpx.Response(200, text="x" * (fetch.LARGEST_ANSWER + 10))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        moved = await fetch.send(
            http,
            fetch.Request("GET", "https://a.example.com/moved", {}, {}, None),
            name="x",
            timeout_s=5,
            resolver=lambda _: PUBLIC,
        )
        long = await fetch.send(
            http,
            fetch.Request("GET", "https://a.example.com/long", {}, {}, None),
            name="x",
            timeout_s=5,
            resolver=lambda _: PUBLIC,
        )
    assert moved.status == 302 and moved.error == "x answered 302"
    assert isinstance(long.body, str) and long.body.endswith("KB]") and len(long.body) < fetch.LARGEST_ANSWER + 100


def test_data_collections_post_carries_the_fields_and_its_headers() -> None:
    """The results go as JSON to the URL named, with the header's secret filled."""
    built = fetch.post_of(
        "https://crm.example.com/calls", [Header(name="X-Key", value="{{secrets.KEY}}")], {"fields": {"a": 1}}, VALUES
    )
    assert built.method == "POST" and built.headers == {"X-Key": "s3cret"}
    assert json.dumps(built.body) == '{"fields": {"a": 1}}'
