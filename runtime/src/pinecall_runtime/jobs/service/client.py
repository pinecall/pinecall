"""The worker's one way to the platform: the gateway over HTTP, on its fleet's key."""

import base64
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence

import httpx
from pydantic import TypeAdapter

from pinecall_runtime.agents import service as agents
from pinecall_runtime.calls import context
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.jobs.service.stream import (
    EVENT_STREAM,
    NOT_SERVED,
    STREAMED,
    TIMEOUT_S,
    EntriesStream,
    affine,
    again,
    server_sent,
    traced,
)
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import BatchedEntry, Command, Entry
from pinecall_runtime.wire.parts import PlatformTool, ToolResult

# A clip is a few hundred KB, fetched once per box.
A_FILE_S = 15.0

# Under the job's sealing budget (worker.py); what does not seal here the reaper seals. One
# request waits all of it: a seal writes memory and asks the judges, which outlast TIMEOUT_S.
SEALED_WITHIN_S = 30.0

ALREADY_OVER = 409

# A caller is waiting on the line while the open is asked again.
OPENED_WITHIN_S = 15.0

# The socket a call's batches go down: `WS /v1/calls/{call}/entries`.
STREAM_PATH = "/v1/calls/{call}/entries"

_ROUTES: TypeAdapter[list[channels.RouteRow]] = TypeAdapter(list[channels.RouteRow])
_CONFIG: TypeAdapter[agents.AgentConfig] = TypeAdapter(agents.AgentConfig)
_OBJECT: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)


class GatewayClient:
    """The gateway as a worker asks it: every endpoint it calls, on one connection pool."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        """No call opened yet."""
        self.http = http
        # What each unsealed call was opened with, said again to a gateway that restarted.
        self.opened: dict[str, calls.OpenCallRequest] = {}
        # Each unsealed call's socket for its batches; none once a gateway had no such endpoint.
        self.streams: dict[str, EntriesStream] = {}
        self.unserved = False

    # ── an agent, before its call ──

    async def routes(self, scope: Scope | None, *, number: str | None, channel: Channel) -> list[context.Route]:
        """The routes of the dispatch's scope; with no scope, the one a number rings, any org."""
        params = _scope_params(scope)
        if number is not None:
            params |= {"number": number, "channel": channel}
        rows = _ROUTES.validate_python(await self._read("GET", "/v1/routes", params=params))
        return [
            context.Route(
                org=row.org, agent=row.agent, channel=row.channel, number=row.number, env=row.env, managed=row.managed
            )
            for row in rows
        ]

    # The call, not opened yet, is named so a canary's share is picked by its id.
    async def agent(self, slug: str, scope: Scope, *, call: str | None = None) -> agents.AgentConfig:
        """The agent as the scope runs it for the call: its declaration under the settings."""
        params = _scope_params(scope) | ({} if call is None else {"for_call": call})
        return _CONFIG.validate_python(await self._read("GET", f"/v1/agents/{slug}/config", params=params))

    # The one answer that carries keys, and it carries them to the fleet's key alone.
    async def stages(self, slug: str, scope: Scope, *, call: str | None = None) -> agents.PipelineKeys:
        """The three stages the call runs, each with the key it runs on, and where its traces go."""
        params = _scope_params(scope) | ({} if call is None else {"for_call": call})
        text = await self._read("GET", f"/v1/agents/{slug}/provider-keys", params=params)
        return agents.PipelineKeys.model_validate(text)

    async def hold_audio(self, slug: str, scope: Scope) -> agents.HoldAudio:
        """What the agent plays while a tool runs."""
        text = await self._read("GET", f"/v1/agents/{slug}/hold-audio", params=_scope_params(scope))
        return agents.HoldAudio.model_validate(text)

    async def hold_clip(self, slug: str, scope: Scope) -> bytes:
        """The org's own clip, Ogg Opus."""
        answer = await self._answered(
            "GET", f"/v1/agents/{slug}/hold-audio/audio", None, A_FILE_S, _scope_params(scope)
        )
        return answer.content

    async def rings_for(self, slug: str, org: str, caller: str) -> telephony.RingHandoff:
        """Whether a production ring from this phone belongs in a developer's sandbox."""
        text = await self._read("GET", f"/v1/agents/{slug}/rings-for", params={"org": org, "caller": caller})
        return telephony.RingHandoff.model_validate(text)

    # The gateway judges the leg (shape and pace) and names the trunk; a refusal is its sentence.
    async def leg(self, slug: str, scope: Scope, *, to: str, call: str, shown: str | None) -> telephony.LegTrunk:
        """How to dial a leg of the call: the trunk inline and the number shown."""
        params = _scope_params(scope) | {"to": to, "call": call} | ({"from": shown} if shown else {})
        text = await self._read("GET", f"/v1/agents/{slug}/outbound-trunk", params=params)
        return telephony.LegTrunkResponse.model_validate(text).trunk

    # A cold transfer dials nothing of ours, so no trunk: the gateway judges the leg alone.
    async def sent_on(self, slug: str, scope: Scope, *, to: str, call: str) -> None:
        """Have the gateway judge a cold transfer's leg; its refusal is its sentence."""
        await self._read(
            "POST", f"/v1/agents/{slug}/cold-transfer", params=_scope_params(scope) | {"to": to, "call": call}
        )

    # ── a call ──

    # Asked again while the gateway is away: an open is the same call by its id (one claim, one
    # opening, one ringing), so an answer lost with a gateway that died is not a call lost.
    async def open(self, opening: calls.OpenCallRequest) -> calls.OpenCallResponse:
        """Open the call's log; the answer is what the org's minutes leave it."""
        body = opening.dump()
        data = await again(lambda: self._read("POST", "/v1/calls", body), OPENED_WITHIN_S, "open")
        self.opened[opening.context.call] = opening
        return calls.OpenCallResponse.model_validate(data)

    # Retried without a limit, the same batch after the same count: the log answers a batch it
    # already took with the seqs it gave it, so an answer lost never writes an entry twice. The
    # batches go down one socket per call; a gateway of before has no such endpoint, and from the
    # first that says so every call's batches go by request.
    async def append_many(self, call: str, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """Write a batch of the call's entries once, in order; the gateway numbers them."""
        path = STREAM_PATH.format(call=call)
        if not self.unserved:
            stream = self.streams.get(call) or self._stream_of(call)
            numbered = await again(lambda: self._streamed_batch(call, stream, entries, after), None, path)
            if numbered is not None:
                return numbered
            self.unserved = True
            self.streams.pop(call, None)
        body = calls.AppendEntriesRequest(after=after, entries=list(entries)).dump()
        answer = await again(lambda: self._on_the_call(call, "POST", path, body), None, path)
        return calls.AppendEntriesResponse.model_validate(answer).entries

    # The gateway answers a lapsed tool at its own deadline: wait past it, so the model reads
    # that answer and not a timeout of ours. Idempotent per call id, so a retry joins.
    async def tool(self, call: str, agent: str, called: JsonObject, timeout_s: float) -> ToolResult:
        """Run a tool in the app that declared it and return what it answered."""
        waiting = timeout_s + TIMEOUT_S
        path = f"/v1/calls/{call}/tools?agent={agent}"
        answer = await again(lambda: self._on_the_call(call, "POST", path, called, waiting), waiting, path)
        return ToolResult.model_validate(answer)

    async def sealed(self, call: str, sealing: calls.SealCallRequest) -> None:
        """Hand the end of the call to the gateway, which prices, judges and seals it."""
        path = f"/v1/calls/{call}/sealed"
        body = sealing.dump()
        try:
            await again(lambda: self._on_the_call(call, "POST", path, body, SEALED_WITHIN_S), SEALED_WITHIN_S, path)
        except GatewayUnavailable as refused:
            # Sealed already: by this seal, whose answer a gateway that died took with it.
            if refused.answered != ALREADY_OVER:
                raise
        self.opened.pop(call, None)
        await self._stream_closed(call)

    async def lookup(
        self, call: str, tool: PlatformTool, arguments: Mapping[str, Json], speech: str | None
    ) -> JsonObject:
        """Recall or search, run by the gateway, which writes what it found on the log."""
        data: JsonObject = {"tool": tool, "input": dict(arguments), "speech_id": speech}
        answer = _OBJECT.validate_python(await self._on_the_call(call, "POST", f"/v1/calls/{call}/lookup", data))
        return _OBJECT.validate_python(answer.get("output") or {})

    # Asked once, at the call's end: a gateway away leaves the recording plain, never unsealed
    # waiting. A gateway of before sealed recordings has no such endpoint and answers 404.
    async def recording_key(self, call: str) -> bytes | None:
        """The key the call's recording is sealed under; None from a gateway that seals none."""
        try:
            answer = await self._on_the_call(call, "POST", f"/v1/calls/{call}/recording/key")
        except GatewayUnavailable as refused:
            if refused.answered != NOT_SERVED:
                raise
            return None
        return base64.urlsafe_b64decode(calls.RecordingKeyResponse.model_validate(answer).key)

    # A code nobody issued is an ordinary answer: the caller may be dialling an extension.
    async def claim(self, call: str, code: str) -> bool:
        """Tie the call to the page showing the code; False when no page waits on it."""
        try:
            await self._on_the_call(call, "POST", f"/v1/calls/{call}/claim", {"code": code})
        except GatewayUnavailable as refused:
            if refused.answered != NOT_SERVED:
                raise
            return False
        return True

    async def state(self, call: str) -> JsonObject:
        """The call's state as the gateway folds it, with the seq it was folded to."""
        return _OBJECT.validate_python(await self._on_the_call(call, "GET", f"/v1/calls/{call}/state"))

    async def since(self, call: str, after: int) -> AsyncIterator[Entry]:
        """The stored entries above the cursor, page by page, until the log's end."""
        cursor = after
        while True:
            path = f"/v1/calls/{call}/events?after={cursor}"

            async def read_page(at: str = path) -> Json:
                return await self._read("GET", at)

            page = await again(read_page, SEALED_WITHIN_S, path)
            if page is None:
                return
            read = calls.LogPage.model_validate(page)
            for entry in read.entries:
                yield Entry.model_validate(entry)
            if read.next is None:
                return
            cursor = read.next

    async def tail(self, call: str, after: int) -> AsyncIterator[Entry]:
        """The entries above the cursor, then the live ones, until the call ends."""
        async for frame in self._streamed(f"/v1/calls/{call}/events?after={after}"):
            yield Entry.model_validate(frame)

    # A stream that ends means the gateway went away; a 404 means it forgot the call.
    async def commands(self, call: str) -> AsyncGenerator[Command]:
        """The app's commands for the call, in the order it sent them, until the call is sealed."""
        path = f"/v1/calls/{call}/commands"
        try:
            async for frame in self._streamed(path):
                yield Command.model_validate(frame)
        except GatewayUnavailable as refused:
            if not await self._reopened(call, refused):
                raise
        else:
            return
        async for frame in self._streamed(path):
            yield Command.model_validate(frame)

    # ── the fleet ──

    async def heartbeat(self, beat: fleet.HeartbeatRequest) -> fleet.HeartbeatResponse:
        """Report this worker; the answer says whether it is cordoned."""
        return fleet.HeartbeatResponse.model_validate(await self._read("POST", "/v1/fleet/heartbeat", beat.dump()))

    async def callback(self, wanted: calls.CallbackRequest) -> None:
        """Somebody the overflow told to wait for a call back."""
        await self._read("POST", "/v1/callbacks", wanted.dump())

    async def aclose(self) -> None:
        """Close every call's socket and the connection pool."""
        for call in list(self.streams):
            await self._stream_closed(call)
        await self.http.aclose()

    # ── the wire ──

    async def _read(
        self,
        method: str,
        path: str,
        data: Json = None,
        wait_s: float | None = None,
        params: Mapping[str, str] | None = None,
    ) -> Json:
        answer = await self._answered(method, path, data, wait_s, params)
        return answer.json() if answer.content else None

    async def _answered(
        self, method: str, path: str, data: Json, wait_s: float | None, params: Mapping[str, str] | None
    ) -> httpx.Response:
        try:
            answer = await self.http.request(
                method,
                path,
                json=data,
                timeout=wait_s or TIMEOUT_S,
                params=params or None,
                headers={**traced(), **affine(path)},
            )
        except httpx.HTTPError as unreachable:
            raise GatewayUnavailable(f"{method} {path}: {unreachable}") from unreachable
        if answer.status_code >= httpx.codes.BAD_REQUEST:
            raise GatewayUnavailable(
                f"{method} {path}: {answer.status_code} {answer.text}", answered=answer.status_code
            )
        return answer

    # A 404 for a call this worker opened is a gateway that restarted: say the call again, once.
    async def _on_the_call(
        self, call: str, method: str, path: str, data: Json = None, wait_s: float | None = None
    ) -> Json:
        try:
            return await self._read(method, path, data, wait_s)
        except GatewayUnavailable as refused:
            if not await self._reopened(call, refused):
                raise
        return await self._read(method, path, data, wait_s)

    def _stream_of(self, call: str) -> EntriesStream:
        path = STREAM_PATH.format(call=call)
        base = str(self.http.base_url).rstrip("/")
        url = f"ws{base.removeprefix('http')}{path}"
        # The key alone of the pool's headers: its keep-alive and encodings are not a handshake's.
        authorization = self.http.headers.get("Authorization")
        headers = {**({"Authorization": authorization} if authorization else {}), **traced(), **affine(path)}
        stream = EntriesStream(url, headers, call)
        self.streams[call] = stream
        return stream

    # A 404 on the socket is the gateway that forgot the call, as on a request; None is a gateway
    # with no such endpoint at all, which the batch endpoint serves.
    async def _streamed_batch(
        self, call: str, stream: EntriesStream, entries: Sequence[BatchedEntry], after: int
    ) -> list[Entry] | None:
        try:
            return await stream.append_many(entries, after=after)
        except GatewayUnavailable as refused:
            if stream.unserved:
                return None
            if not await self._reopened(call, refused):
                raise
        return await stream.append_many(entries, after=after)

    async def _stream_closed(self, call: str) -> None:
        stream = self.streams.pop(call, None)
        if stream is not None:
            await stream.close()

    async def _reopened(self, call: str, refused: GatewayUnavailable) -> bool:
        opening = self.opened.get(call)
        if refused.answered != NOT_SERVED or opening is None:
            return False
        await self._read("POST", f"/v1/calls/{call}/reopened", opening.dump())
        return True

    async def _streamed(self, path: str) -> AsyncIterator[JsonObject]:
        try:
            async with self.http.stream(
                "GET", path, headers={"Accept": EVENT_STREAM, **affine(path)}, timeout=STREAMED
            ) as stream:
                if stream.status_code >= httpx.codes.BAD_REQUEST:
                    raise GatewayUnavailable(f"GET {path}: {stream.status_code}", answered=stream.status_code)
                async for frame in server_sent(stream.aiter_lines()):
                    yield frame
        except httpx.HTTPError as unreachable:
            raise GatewayUnavailable(f"GET {path}: {unreachable}") from unreachable


def gateway_at(url: str, key: str | None) -> GatewayClient:
    """The gateway at this URL, asked with the fleet's key in the header, never the URL."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return GatewayClient(httpx.AsyncClient(base_url=url, headers=headers, timeout=TIMEOUT_S))


def _scope_params(scope: Scope | None) -> dict[str, str]:
    if scope is None:
        return {}
    return {"org": scope.org, "env": scope.env, "holder": scope.holder}
