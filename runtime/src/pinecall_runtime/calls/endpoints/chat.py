"""A written call over a WebSocket: a message in, every entry of the call out."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from starlette.websockets import WebSocketState

from pinecall_runtime.accounts.service.keys import check_agent
from pinecall_runtime.agents.service import registry
from pinecall_runtime.agents.service.registry import Registration
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.auth import serving_of
from pinecall_runtime.calls.context import CallContext, Contact, Route, new_call_id
from pinecall_runtime.calls.fanout import Subscription
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.text import open_text, resume_text, tokens_of
from pinecall_runtime.enums import Channel, Direction, KeyScope
from pinecall_runtime.exceptions import (
    Conflict,
    NotFound,
    PinecallError,
    QuotaExceeded,
    Unauthorized,
    ValidationError,
)
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Actor, Scope, check_scopes
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.kit.time import today_in
from pinecall_runtime.kit.websockets import close_reason, code_of, refuse_socket
from pinecall_runtime.postgres import Session
from pinecall_runtime.session import service as session

router = APIRouter()

NOT_TAKEN_UP = "call {call} cannot be taken up: it is over, or not this agent's; open a new one"
NOT_A_STATE = "?state= is the state the call opens in: a JSON object of the class's fields"
A_STATE_AT_MOST = 16 * 1024
_A_STATE: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
OVER = "the call ended: {reason}"
# What uvicorn closes with on a stop; a caller never sends it, so the call is left for the next
# process to take up.
SERVICE_RESTART = 1012


# The org's key, never a room token (`pinecall chat`, `test`, `simulate`).
@router.websocket("/v1/chat")
async def chat(websocket: WebSocket) -> None:
    """One text call: {text} frames in, every entry of the call out."""
    serving = serving_of(websocket)
    try:
        registration, again = _chatting(websocket, serving)
        async with serving.handles.sessions.begin() as session_:
            if again is not None:
                running = await resume_text(session_, serving, registration, again, serving.handles.settings.timezone)
                if running is None:
                    raise Conflict(NOT_TAKEN_UP.format(call=again))
            else:
                context = await _chat_context(session_, websocket, serving, registration)
                running = await open_text(session_, serving, registration, context)
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()
    served = serving.live.calls.get(running.call.context.call)
    heard = await served.log.follow() if served is not None else None
    sending = asyncio.create_task(_send(websocket, heard)) if heard is not None else None
    # The call can end from the desk or by the model: the socket is closed under the caller.
    ending = asyncio.create_task(_hung_up(websocket, running))
    try:
        if again is None:
            await running.start()
        await _turns(websocket, serving, running)
    finally:
        ending.cancel()
        if sending is not None:
            sending.cancel()


async def _hung_up(websocket: WebSocket, running: session.Session) -> None:
    await running.over.wait()
    reason, _ = running.ended or ("error", "platform")
    if websocket.application_state is WebSocketState.CONNECTED:
        await websocket.close(reason=close_reason(OVER.format(reason=reason)))


def _chatting(websocket: WebSocket, serving: Serving) -> tuple[Registration, str | None]:
    actor: Actor | None = getattr(websocket.state, "actor", None)
    if actor is None:
        raise Unauthorized("this endpoint takes an API key")
    check_scopes(actor, (KeyScope.talk,))
    slug = websocket.query_params.get("agent", "")
    check_agent(actor, slug)
    app = websocket.query_params.get("app")
    registration = serving.registry.serving(actor.scope, slug, app)
    if registration is None:
        raise NotFound(_why_not(serving, actor.scope, slug, app))
    return registration, websocket.query_params.get("call")


# A web caller is a visitor id; the org's own key may name who it is (`?contact=`) and which of
# the agent's synthetic callers plays it (`?persona=`), its own or Pinecall's, whose expectations
# are frozen into the call here.
async def _chat_context(
    session_: Session, websocket: WebSocket, serving: Serving, registration: Registration
) -> CallContext:
    scope = registration.scope
    named = websocket.query_params.get("persona") or None
    persona = None if named is None else await judging.persona_named(session_, scope.org, registration.slug, named)
    contact = websocket.query_params.get("contact")
    return CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller=websocket.query_params.get("caller") or f"web_{new_call_id()[5:17]}",
        contact=Contact(id=contact) if contact else None,
        persona=named,
        expects=() if persona is None else persona.expects,
        route=Route(org=scope.org, agent=registration.slug, channel=Channel.web, env=scope.env),
        today=today_in(serving.handles.settings.timezone),
        holder=scope.holder or None,
        state=_opening_state(websocket),
    )


def _opening_state(websocket: WebSocket) -> JsonObject:
    query = websocket.query_params.get("state")
    if not query:
        return {}
    size = len(query.encode())
    if size > A_STATE_AT_MOST:
        raise ValidationError(f"?state= is {size} bytes: the state a call opens in is {A_STATE_AT_MOST} bytes at most")
    try:
        return _A_STATE.validate_json(query)
    except PydanticValidationError:
        raise ValidationError(NOT_A_STATE) from None


# A failed send flips the application state; a receive after it raises RuntimeError, so the
# state is asked before each receive.
async def _turns(websocket: WebSocket, serving: Serving, running: session.Session) -> None:
    route = running.call.context.route
    scope = Scope(route.org, route.env)
    try:
        while websocket.application_state is WebSocketState.CONNECTED:
            frame = await websocket.receive_json()
            if _hangs_up(frame):
                # Ended before the socket closes, so the caller hears the call is over before it
                # stops whatever served it.
                await session.end_text(running, "caller_hung_up", "caller")
                await websocket.close(reason=close_reason(OVER.format(reason="caller_hung_up")))
                return
            data = _text_of(frame)
            if not data:
                continue
            async with serving.handles.sessions.begin() as session_:
                try:
                    await billing.admit_turn(
                        session_,
                        scope.org,
                        scope.env,
                        turns=running.call.turns,
                        tokens=tokens_of(running.usage),
                        at=serving.logs.store.clock(),
                    )
                except QuotaExceeded as refused:
                    await alerts.credits_exhausted(
                        session_, serving.handles, serving.logs, scope, running.call.config.slug, refused
                    )
                    await session.end_text(running, "timeout", "platform")
                    await websocket.close(code=code_of(refused), reason=close_reason(str(refused)))
                    return
            await session.hear_text(running, data)
    except WebSocketDisconnect as gone:
        if gone.code != SERVICE_RESTART and not running.closed:
            await session.end_text(running, "caller_hung_up", "caller")
        return
    # A send that found the caller gone closed the socket under the loop, with no close to hear.
    if not running.closed:
        await session.end_text(running, "caller_hung_up", "caller")


async def _send(websocket: WebSocket, heard: Subscription) -> None:
    async for entry in heard:
        await websocket.send_json(entry.dump())


def _hangs_up(data: Json) -> bool:
    return isinstance(data, dict) and data.get("hangup") is True


def _text_of(data: Json) -> str:
    if not isinstance(data, dict):
        return ""
    said = data.get("text")
    return said if isinstance(said, str) else ""


def _why_not(serving: Serving, scope: Scope, slug: str, app: str | None) -> str:
    if app is not None:
        return f"app {app} does not hold agent {slug}"
    if serving.registry.holder_of(scope, slug) is not None:
        return f"every app holding agent {slug} takes only the calls that name it"
    return str(registry.NoApp(slug))
