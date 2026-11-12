"""The gateway as a worker asks it: the box's endpoints (routes, an agent, the fleet) and the wire they ride on."""

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from opentelemetry import propagate

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.calls import service as calls
from runtime.calls.context import Route
from runtime.enums import Channel
from runtime.exceptions import UpstreamError
from runtime.kit.sse import EVENT_STREAM, Sent, read_sse
from runtime.kit.text import Json, a_list
from runtime.providers import service as providers
from runtime.providers.stage import Pipeline
from runtime.wire.worker import (
    AgentConfigResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    HoldAudio,
    PipelineKeys,
    RingAtTestLine,
    RingHandoff,
    RouteRow,
)

# A caller is waiting on the line.
TIMEOUT_S = 5.0
# A clip is a few hundred KB, fetched once per box.
A_FILE_S = 15.0
# A restarting gateway is back in seconds; the cap keeps the log catching up after it.
LONGEST_WAIT_S = 5.0
# A stream is timed only on connect: a quiet one is kept open by the gateway's ping every 25 s.
STREAMED = httpx.Timeout(TIMEOUT_S, read=None)

# The header a balancer keeps a call's requests on one gateway by: `/v1/calls/{call}/...`.
CALL_HEADER = "Pinecall-Call"
CALL_AT = 3


@dataclass(frozen=True, slots=True)
class Stages:
    """The stages a call runs, each on the key it runs on, and the org's collector for its traces."""

    pipeline: Pipeline
    telemetry: providers.Telemetry | None = None


# The gateway's failure as a worker reads it. Away (unreachable, or a 5xx) is what asking again
# outlasts; a 4xx is an answer, read by whoever asked (`answered`).
def unavailable(what: str, *, answered: int | None = None) -> UpstreamError:
    """The failure of one request to the gateway: away, which a retry outlasts, or its answer."""
    is_away = answered is None or answered >= httpx.codes.INTERNAL_SERVER_ERROR
    return UpstreamError(what, vendor="the gateway", answered=answered, retryable=is_away)


class GatewayClient:
    """The gateway as a worker asks it, on its fleet's key and one connection pool."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        """The pool, its key in its headers."""
        self.http = http

    # ── an agent, before its call ──

    async def list_routes(self, scope: Scope | None, *, number: str | None, channel: Channel) -> list[Route]:
        """The routes of the dispatch's scope; with no scope, the one a number rings, any org."""
        params = scope_params(scope)
        if number is not None:
            params |= {"number": number, "channel": channel}
        answer: object = await self.read("GET", "/v1/routes", params=params)
        rows: list[object] = list(answer) if a_list(answer) else []
        return [Route(**RouteRow.model_validate(row).model_dump()) for row in rows]

    # The call, not opened yet, is named so a canary's share is picked by its id.
    async def get_agent(
        self, slug: str, scope: Scope, *, call: str | None = None, test: Mapping[str, Any] | None = None
    ) -> Declaration:
        """The agent as the scope runs it for the call: its declaration under the settings, and a test room's values."""
        params = scope_params(scope) | _for_call(call) | _test_param(test)
        answer = AgentConfigResponse.model_validate(await self.read("GET", f"/v1/agents/{slug}/config", params=params))
        return calls.read_declaration(answer.model_dump(mode="json"))

    # The one answer that carries keys, and it carries them to the fleet's key alone.
    async def get_stages(
        self, slug: str, scope: Scope, *, call: str | None = None, test: Mapping[str, Any] | None = None
    ) -> Stages:
        """The stages the call runs, each with the key it runs on, and where its traces go."""
        params = scope_params(scope) | _for_call(call) | _test_param(test)
        keys = PipelineKeys.model_validate(await self.read("GET", f"/v1/agents/{slug}/provider-keys", params=params))
        telemetry = None if keys.telemetry is None else providers.Telemetry(**keys.telemetry.model_dump())
        return Stages(Pipeline.read(keys.model_dump()), telemetry)

    async def get_hold(self, slug: str, scope: Scope) -> HoldAudio:
        """What the agent plays while a tool runs."""
        answer = await self.read("GET", f"/v1/agents/{slug}/hold-audio", params=scope_params(scope))
        return HoldAudio.model_validate(answer)

    async def get_hold_clip(self, slug: str, scope: Scope) -> bytes:
        """The org's own clip, Ogg Opus."""
        path = f"/v1/agents/{slug}/hold-audio/audio"
        return (await self.answer("GET", path, wait_s=A_FILE_S, params=scope_params(scope))).content

    async def ring_for(self, slug: str, org: str, caller: str) -> RingHandoff:
        """Whether a production ring from this phone belongs in a developer's sandbox."""
        answer = await self.read("GET", f"/v1/agents/{slug}/rings-for", params={"org": org, "caller": caller})
        return RingHandoff.model_validate(answer)

    async def ring_at_test_line(self, number: str, caller: str) -> RingAtTestLine:
        """Whose sandbox agent a ring at the box's test line is for, if the number is it and the phone is known."""
        answer = await self.read("GET", "/v1/test-line/rings-for", params={"number": number, "caller": caller})
        return RingAtTestLine.model_validate(answer)

    # ── the fleet ──

    async def beat(self, beat: HeartbeatRequest) -> HeartbeatResponse:
        """Report this worker; the answer says whether it is cordoned."""
        return HeartbeatResponse.model_validate(await self.read("POST", "/v1/fleet/heartbeat", beat.dump()))

    async def ask_callback(self, agent: str, channel: Channel, number: str, call: str) -> None:
        """Somebody the overflow told to wait for a call back."""
        wanted: Json = {"agent": agent, "channel": channel.value, "number": number, "call": call}
        await self.read("POST", "/v1/callbacks", wanted)

    async def aclose(self) -> None:
        """Close the connection pool."""
        await self.http.aclose()

    # ── the wire ──

    async def read(
        self,
        method: str,
        path: str,
        data: Json = None,
        *,
        wait_s: float | None = None,
        params: Mapping[str, str] | None = None,
    ) -> Json:
        """One request's JSON answer; None for an answer with no body."""
        answer = await self.answer(method, path, data, wait_s=wait_s, params=params)
        return answer.json() if answer.content else None

    async def answer(
        self,
        method: str,
        path: str,
        data: Json = None,
        *,
        wait_s: float | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """One request's answer; a gateway away or one that refused raises what `unavailable` says."""
        try:
            answer = await self.http.request(
                method,
                path,
                json=data,
                timeout=wait_s or TIMEOUT_S,
                params=params or None,
                headers={**trace_headers(), **affinity_headers(path)},
            )
        except httpx.HTTPError as unreachable:
            raise unavailable(f"{method} {path}: {unreachable}") from unreachable
        if answer.status_code >= httpx.codes.BAD_REQUEST:
            raise unavailable(f"{method} {path}: {answer.status_code} {answer.text}", answered=answer.status_code)
        return answer

    async def stream(self, path: str) -> AsyncIterator[Sent]:
        """Each message of one of the gateway's event streams, until the gateway ends it."""
        headers = {"Accept": EVENT_STREAM, **affinity_headers(path)}
        try:
            async with self.http.stream("GET", path, headers=headers, timeout=STREAMED) as answer:
                if answer.status_code >= httpx.codes.BAD_REQUEST:
                    raise unavailable(f"GET {path}: {answer.status_code}", answered=answer.status_code)
                async for sent in read_sse(answer.aiter_lines()):
                    yield sent
        except httpx.HTTPError as unreachable:
            raise unavailable(f"GET {path}: {unreachable}") from unreachable

    # The key alone of the pool's headers: its keep-alive and encodings are not a handshake's.
    def socket_at(self, path: str) -> tuple[str, dict[str, str]]:
        """Where a socket of the gateway's is, and the headers its handshake carries."""
        base = str(self.http.base_url).rstrip("/")
        authorization = self.http.headers.get("Authorization")
        key = {"Authorization": authorization} if authorization else {}
        return f"ws{base.removeprefix('http')}{path}", {**key, **trace_headers(), **affinity_headers(path)}


def open_gateway(url: str, key: str | None) -> GatewayClient:
    """The gateway at this URL, asked with the fleet's key in the header, never the URL."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return GatewayClient(httpx.AsyncClient(base_url=url, headers=headers, timeout=TIMEOUT_S))


# The worker's current span rides each request as W3C traceparent, so the gateway's handling of an
# append joins the turn's trace; with no tracer set (no PINECALL_OTLP_ENDPOINT) nothing is added.
def trace_headers() -> dict[str, str]:
    """The headers that carry the current trace to the gateway; none when nothing traces."""
    carried: dict[str, str] = {}
    propagate.inject(carried)
    return carried


# A box of several gateways hashes this header at its balancer, so a call's requests land on one
# gateway while it lives: its first sights, its sequencer's fills and its writers stay rare. Only
# a speed-up: any gateway serves any endpoint.
def affinity_headers(path: str) -> dict[str, str]:
    """The header naming the call a request is about, when its path names one."""
    parts = path.split("/")
    if len(parts) > CALL_AT and parts[1:CALL_AT] == ["v1", "calls"] and parts[CALL_AT]:
        return {CALL_HEADER: parts[CALL_AT].partition("?")[0]}
    return {}


# The worker's scope rides the query of every endpoint it asks, read where its key is resolved.
def scope_params(scope: Scope | None) -> dict[str, str]:
    """The scope a question of a worker carries; nothing for the box's own trunk, where the number decides."""
    if scope is None:
        return {}
    return {"org": scope.org, "env": scope.env, "holder": scope.holder}


def _for_call(call: str | None) -> dict[str, str]:
    return {} if call is None else {"for_call": call}


# A test room's values, said to the gateway as the JSON they rode the dispatch in.
def _test_param(test: Mapping[str, Any] | None) -> dict[str, str]:
    return {"test": json.dumps(dict(test), separators=(",", ":"))} if test else {}
