"""An app's socket as the gateway answers it: each frame a command applied or refused; its agents, its calls."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.agents.service import declared, settings
from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.reducer import unanswered_tools
from pinecall_runtime.calls.service.binding import attach_parked, hand_on
from pinecall_runtime.calls.service.live import Live, Served, declare_for_the_call
from pinecall_runtime.calls.service.peers import send_command
from pinecall_runtime.calls.service.serving import Serving, claim_code, known_here
from pinecall_runtime.calls.service.threads import Threads
from pinecall_runtime.enums import Channel, ConsentKind
from pinecall_runtime.exceptions import (
    Conflict,
    PinecallError,
    QuotaExceeded,
    ServiceUnavailable,
    ValidationError,
)
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.postgres import DatabaseError, busy, is_cancellation
from pinecall_runtime.providers import service as providers
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import Command, Entry, WireModel
from pinecall_runtime.wire.commands import (
    COMMANDS,
    AgentConfigure,
    AgentDrain,
    AgentRegister,
    CallClaim,
    CallDial,
    CallOptOut,
    DevAnswer,
    Ping,
    PromptSet,
    command_of,
)
from pinecall_runtime.wire.events import ErrorEvent, Pong
from pinecall_runtime.wire.parts import ToolResult
from pinecall_runtime.wire.signal import Bound, ForApp

logger = logging.getLogger(__name__)

# What the transport does for the socket: one frame down, and the close.
type Send = Callable[[JsonObject], Awaitable[None]]
type Close = Callable[[str], Awaitable[None]]

# Sent on a stop: the SDK exits instead of reconnecting.
STOPPED = "stopped"
# The gateway's own Studio socket (studio/service/holder.py): a slug it holds is held by no other app.
STUDIO_SDK = "studio"
STUDIO_KEYS = "studio:"
STUDIOS = "{slug} is a Studio agent of this org: Studio holds it, so give your app's agent another name"
# `error` code on one agent killed by an admin (`POST /v1/agents/{slug}/kill`): the app keeps the others.
KILLED = "killed"
REFUSED = "refused"
BAD_SHAPE = "bad_shape"
# `error` code on a frame the database did not answer in time: the app sends it again.
BUSY = "busy"
NOT_JSON = "a frame is one JSON object: this one did not parse"
DIAL = (
    "call.dial is not answered on the app socket: POST /v1/agents/{slug}/dial places a call, with the talk scope "
    "and the org's outbound guards"
)
NO_SESSION = "{kind} names call {call!r}, which is not running here"
# Where an opt-out the agent heard came from, as the do-not-call list says it.
ASKED_THE_AGENT = "the caller asked the agent"
NO_NUMBER_TO_LIST = "call {call} has no phone number at its far end: nothing to put on the list"
NOBODY_WAITING = (
    "no tool call {call_id} is waiting on call {call!r}: it lapsed, it was answered, or the call is not here"
)
NOBODY_ASKED = "no dev.request {id} is waiting: it lapsed, it was answered, or another gateway asked it"
NO_CODE = "no code {code} is waiting for agent {agent}: nobody issued it, it expired, or a call took it"
SEARCHES_WITH_NOTHING = (
    "{slug} searches its bases, and none is attached to it in {env}: pinecall docs attach <base> --agent {slug}"
)
# How long a socket waits for the signal before listening again for the calls bound to it.
INBOX_RETRY_S = 1.0


class AppSocket:
    """One connected app: its key, its scope, and every frame it sends answered."""

    def __init__(
        self, serving: Serving, threads: Threads, actor: Actor, send: Send, close: Close, address: str | None
    ) -> None:
        """A socket that holds nothing yet."""
        self.serving = serving
        self.threads = threads
        self.actor = actor
        self.scope = actor.scope
        self.id: agents_registry.SocketId = agents_registry.new_socket_id()
        self.address = address
        self.connected_at = time.time()
        self._send = send
        self._close = close

    @property
    def registry(self) -> agents_registry.AgentRegistry:
        """Who holds which agent, on every gateway."""
        return self.serving.registry

    @property
    def live(self) -> Live:
        """The sockets open and the calls served, on every gateway."""
        return self.serving.live

    def connect(self) -> None:
        """Say the socket is open: the org's list of apps shows it from now on."""
        app = agents_registry.ConnectedApp(
            app=self.id,
            scope=self.scope,
            address=self.address,
            connected_at=self.connected_at,
            stop=self.stop,
            kill=self.kill,
        )
        self.live.connect(app, self.send)

    async def send(self, entry: Entry) -> None:
        """One entry down the socket, as the log holds it."""
        await self._send(entry.dump())

    async def stop(self, why: str) -> None:
        """Tell the app it was stopped, and close: it exits instead of reconnecting."""
        await self.send(Entry.unstored("", "error", ErrorEvent(code=STOPPED, message=why, recoverable=False).dump()))
        await self._close(why)

    # The app keeps its other agents; the killed one's calls move as on a drain, to whoever else
    # holds it, else parked. The error tells the app not to declare it again when it reconnects.
    async def kill(self, slug: str, why: str) -> None:
        """Tell the app one of its agents was killed, and let go of it here."""
        if self.registry.on_socket(self.id, self.scope.env, slug) is None:
            return
        await self.send(Entry.unstored(slug, "error", ErrorEvent(code=KILLED, message=why, recoverable=False).dump()))
        theirs = [call for call in self.live.bound_to(self.id) if self.live.calls[call].agent == slug]
        for call in theirs:
            self.live.attach(call, None)
        await self.registry.kill(self.id, self.scope.env, slug)
        await hand_on(self.live, self.registry, theirs)

    async def take(self, raw: Json) -> None:
        """One frame: its command applied, or refused in an error that names it."""
        try:
            command = Command.model_validate(raw)
        except PydanticValidationError as refused:
            await self.refuse(_named(raw, "agent"), BAD_SHAPE, f"command: {refused}", raw)
            return
        if command.type not in COMMANDS:
            await self.refuse(
                command.agent, "unknown_command", f"the protocol has no command called {command.type!r}", raw
            )
            return
        try:
            await self._apply(command)
        except QuotaExceeded as refused:
            await self.refuse(command.agent, REFUSED, str(refused), raw)
        except PinecallError as refused:
            await self.refuse(
                command.agent, BAD_SHAPE if isinstance(refused, ValidationError) else REFUSED, str(refused), raw
            )
        except DatabaseError as failed:
            # The socket outlives a database that did not answer: closed, the app would reconnect
            # and re-register its agents, and its calls would be parked and handed on for nothing;
            # the frame is answered as busy and sent again (2026-10-21: a pool with no connection
            # free cut an app's socket, and the entry it was sending was lost).
            if is_cancellation(failed):
                raise
            logger.warning("app %s: %s was not applied, the database did not answer", self.id, command.type)
            await self.refuse(command.agent, BUSY, str(busy()), raw)

    # What other gateways send this socket: a call they bound to it (served here and pumped down
    # it, from the seq they said), an entry for it (a console's dev.request), a stop, or a kill.
    async def listen(self) -> None:
        """Hear the socket's inbox on the signal, for as long as the socket is open."""
        while True:
            try:
                listener = await self.live.inbox(self.id)
            except ServiceUnavailable:
                await asyncio.sleep(INBOX_RETRY_S)
                continue
            try:
                async for data in listener:
                    await self._heard(ForApp.model_validate_json(data))
            finally:
                listener.close()
            await asyncio.sleep(INBOX_RETRY_S)

    # A message the database did not answer (a binding read in a transaction) is logged and the
    # inbox heard on: a task that died with it would leave the socket deaf for its whole life.
    async def _heard(self, message: ForApp) -> None:
        try:
            await self.hear(message)
        except DatabaseError as failed:
            if is_cancellation(failed):
                raise
            logger.warning("app %s: a message of its inbox was not applied; the database did not answer", self.id)

    async def hear(self, message: ForApp) -> None:
        """One message of the inbox, applied."""
        if message.bound is not None:
            await self._bound(message.bound)
        if message.entry is not None:
            await self.send(message.entry)
        if message.stop is not None:
            await self.stop(message.stop)
        if message.kill is not None:
            await self.kill(message.kill.agent, message.kill.why)

    async def gone(self) -> None:
        """The app went: its calls outlive the socket, parked, then handed to the next holder."""
        self.live.disconnect(self.id)
        bound = self.live.bound_to(self.id)
        for call in bound:
            self.live.attach(call, None)
        await self.registry.release(self.id)
        await hand_on(self.live, self.registry, bound)

    async def refuse(self, slug: str, code: str, message: str, raw: Json) -> None:
        """An error naming the command refused and its id; on the agent's log when it holds one."""
        text = ErrorEvent(
            code=code,
            message=message,
            command=_named(raw, "type") or None,
            id=_named(raw, "id") or None,
            recoverable=True,
        )
        await self._emit(slug, "error", text)

    # ── one arm per command ──

    async def _apply(self, command: Command) -> None:
        model = command_of(command)
        match model:
            case AgentRegister():
                await self._register(command.agent, model)
            case AgentConfigure():
                await self._configure(command.agent, model)
            case AgentDrain():
                await self._drain(command.agent)
            case Ping():
                await self._emit(command.agent, "pong", Pong(ts=time.time()))
            case DevAnswer():
                if not await self.live.dev_answered(model):
                    await self.refuse(command.agent, "no_session", NOBODY_ASKED.format(id=model.id), command.dump())
            case ToolResult():
                await self._answered(command, model)
            case CallClaim() | CallOptOut():
                await self._on_the_gateway(command, model)
            case CallDial():
                await self.refuse(command.agent, "no_handler", DIAL.format(slug=command.agent), command.dump())
            case PromptSet():
                await self._prompted(command, model)
            case _:
                await self._on_the_call(command, model)

    async def _register(self, slug: str, wanted: AgentRegister) -> None:
        keys.check_agent(self.actor, slug)
        if not self.actor.key_id.startswith(STUDIO_KEYS) and self._held_by_studio(slug):
            raise Conflict(STUDIOS.format(slug=slug))
        self.live.named(self.id, wanted.host)
        scope = self.scope
        others = self.registry.slugs_of(scope.org) - {slug}
        async with self.serving.handles.sessions.begin() as session:
            try:
                await billing.admit_agent(session, scope.org, scope.env, holding=len(others))
            except QuotaExceeded as refused:
                await alerts.credits_exhausted(session, self.serving, scope, slug, refused)
                raise
        await self.send(await self.registry.register(self.id, scope, slug, wanted))
        # A console takes no call it did not open; an app takes the calls a previous one left.
        if wanted.takes_unclaimed:
            await attach_parked(self.live, scope, slug, self.id)

    # A class that searches with no base attached, gives a plugin options on a key the box lends,
    # or asks ears that cannot end the turn to, is refused when declared, not mid-call.
    async def _configure(self, slug: str, wanted: AgentConfigure) -> None:
        found = self._holds(slug)
        config = declared.with_app_fields(found.config, wanted.config)
        async with self.serving.handles.sessions.begin() as session:
            catalog = await providers.get_catalog(session)
            running, _ = await settings.tuned_for_call(session, config, self.scope, catalog)
            if config.uses_knowledge and not running.bases:
                raise ValidationError(SEARCHES_WITH_NOTHING.format(slug=slug, env=self.scope.env))
            keyring = await providers.keys_of(session, self.serving.handles.vault, self.scope)
        providers.refuse_what_cannot_run(running, catalog, keyring)
        await self.send(
            await self.registry.configure(self.id, self.scope.env, slug, config, declared.changed_by(wanted.config))
        )
        # Declared now: what waited on WhatsApp for this agent is answered on this declaration.
        if found.takes_unclaimed:
            self.threads.answer_waiting(self._holds(slug))

    # A deploy: the calls move now, and the socket keeps the agent so its tools still answer.
    async def _drain(self, slug: str) -> None:
        self.registry.drain(self.id, self.scope.env, slug)
        mine = [call for call in self.live.bound_to(self.id) if self.live.calls[call].agent == slug]
        handed, parked = await hand_on(self.live, self.registry, mine)
        await self.send(await self.registry.drained(self.id, self.scope.env, slug, handed=handed, parked=parked))

    # The worker may have asked another gateway: the answer is written on the call's log here,
    # once per call id, and whoever waits reads it there.
    async def _answered(self, command: Command, result: ToolResult) -> None:
        self._holds(command.agent)
        served = None if command.call is None else self.live.calls.get(command.call)
        ours = served is not None and served.scope.org == self.scope.org and served.agent == command.agent
        if (
            served is not None
            and ours
            and (served.tools.answer(result) or await served.log.answer(result.dump()) is not None)
        ):
            return
        await self.refuse(
            command.agent,
            "no_session",
            NOBODY_WAITING.format(call_id=result.call_id, call=command.call),
            command.dump(),
        )

    # A code claimed and an opt-out are the gateway's to answer, whichever process runs the call.
    async def _on_the_gateway(self, command: Command, wanted: CallClaim | CallOptOut) -> None:
        self._holds(command.agent)
        served = None if command.call is None else self.live.calls.get(command.call)
        if served is None or served.agent != command.agent:
            await self.refuse(
                command.agent, "no_session", NO_SESSION.format(kind=command.type, call=command.call), command.dump()
            )
            return
        async with self.serving.handles.sessions.begin() as session:
            if isinstance(wanted, CallOptOut):
                await _opt_out(session, served, command.agent, wanted)
                return
            claimed = await claim_code(session, self.serving.codes, served, wanted.code, via="agent")
        if not claimed:
            await self.refuse(
                command.agent, "no_code", NO_CODE.format(code=wanted.code, agent=command.agent), command.dump()
            )

    # The block's words are kept once under the hash the log will name, before the call hears it.
    async def _prompted(self, command: Command, wanted: PromptSet) -> None:
        self._holds(command.agent)
        async with self.serving.handles.sessions.begin() as session:
            await self.serving.prompts.keep(session, self.scope.org, wanted.text)
        await self._on_the_call(command, wanted)

    # A written call runs here and takes the command at once; a voice call's worker reads it
    # off its command stream and applies it with the same function.
    async def _on_the_call(self, command: Command, model: WireModel) -> None:
        self._holds(command.agent)
        served = None if command.call is None else self.live.calls.get(command.call)
        if served is not None and served.agent == command.agent and served.running is not None:
            declare_for_the_call(served, model)
            await served.running.apply(model)
            return
        if command.call is not None and await send_command(self.serving.handles.signal, command):
            return
        await self.refuse(
            command.agent, "no_session", NO_SESSION.format(kind=command.type, call=command.call), command.dump()
        )

    async def _bound(self, bound: Bound) -> None:
        async with self.serving.handles.sessions.begin() as session:
            served = await known_here(session, self.serving, bound.call)
        if served is None:
            # Never silent: a call bound here that this gateway cannot serve is a call whose app
            # will not hear it, and its opener's fault (the opening must be committed before it is told).
            logger.warning(
                "call %s was bound to socket %s, and this gateway has no opening to serve it from", bound.call, self.id
            )
            return
        if self.id not in self.live.sockets or bound.call in self.live.pumps:
            return
        self.live.attach(bound.call, self.id)
        then = unanswered_tools(await served.log.whole()) if bound.after else []
        self.live.pumped(bound.call, after=bound.after, then=then)

    def _held_by_studio(self, slug: str) -> bool:
        scopes = (self.scope, agents_registry.orgs_own(self.scope))
        return any(held.sdk == STUDIO_SDK for scope in scopes for held in self.registry.holders.get((scope, slug), ()))

    def _holds(self, slug: str) -> agents_registry.Registration:
        registration = self.registry.on_socket(self.id, self.scope.env, slug)
        if registration is None:
            raise agents_registry.NotRegistered(slug)
        return registration

    # On the agent's log only when this socket holds the agent: a slug is one org's, and a frame
    # naming any other is answered down the socket alone, so nothing of it lands on a log.
    async def _emit(self, slug: str, kind: str, event: WireModel) -> None:
        if self.registry.on_socket(self.id, self.scope.env, slug) is None:
            await self.send(Entry.unstored(slug, kind, event.dump()))
            return
        await self.send(await self.serving.logs.agent(slug).append(kind, event.dump()))


def _named(raw: Json, field: str) -> str:
    if not isinstance(raw, dict):
        return ""
    named = raw.get(field)
    return named if isinstance(named, str) else ""


# The list is the org's, not the call's, and nothing lands in the log: an SDK that predates the
# command would refuse to read an entry it has no shape for.
async def _opt_out(session: AsyncSession, served: Served, agent: str, wanted: CallOptOut) -> None:
    if served.context.channel is not Channel.phone:
        raise ValidationError(NO_NUMBER_TO_LIST.format(call=served.call))
    given = telephony.Given(
        kind=ConsentKind.opt_out, source=ASKED_THE_AGENT, given_by=f"agent:{agent}", text=wanted.note, call=served.call
    )
    await telephony.give_consent(session, served.scope, served.context.caller, given)
