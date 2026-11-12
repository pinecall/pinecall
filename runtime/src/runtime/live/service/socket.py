"""An app's socket as the gateway answers it: each frame a command applied or refused; its agents, its calls."""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.billing import service as billing
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.compliance import service as compliance
from runtime.enums import Channel, ConsentKind, Env
from runtime.exceptions import Conflict, PinecallError, QuotaExceeded, ValidationError
from runtime.judging import service as judging
from runtime.kit.loops import is_cancellation
from runtime.kit.text import Json, JsonObject
from runtime.live.holders import AnotherOrgs, Holders, NotRegistered, Registration, new_socket_id
from runtime.live.parts import LiveParts
from runtime.live.peers import APP_INBOX
from runtime.live.served import Served
from runtime.live.service import commands, handoff, openings
from runtime.live.service.codes import NoSuchCode
from runtime.live.service.whatsapp import Threads
from runtime.live.sockets import SocketId, Sockets
from runtime.postgres import DatabaseError, busy
from runtime.providers import service as providers
from runtime.scoping import box_task
from runtime.session import service as session
from runtime.telephony import service as telephony
from runtime.wire.base import Command, Entry, WireModel
from runtime.wire.commands import (
    COMMANDS,
    AgentConfigure,
    AgentDrain,
    AgentRegister,
    CallClaim,
    CallDial,
    CallDone,
    CallOptOut,
    DevAnswer,
    Ping,
    PromptSet,
    SupervisorVerb,
    command_of,
)
from runtime.wire.events import ErrorEvent, Pong
from runtime.wire.parts import ToolResult
from runtime.wire.signal import Bound, ForApp, Scoped, SocketRow

logger = logging.getLogger(__name__)

# What the transport does for the socket: one frame down, and the close.
type SendFrame = Callable[[JsonObject], Awaitable[None]]
type Close = Callable[[str], Awaitable[None]]
# Ties a call to the page showing a code, as its agent heard it: False when no page waits on it. Given
# by whoever builds the socket (`Codes.claim_heard`).
type ClaimCode = Callable[[AsyncSession, Served, str], Awaitable[bool]]

# Sent on a stop: the SDK exits instead of reconnecting.
STOPPED = "stopped"
# `error` code on one agent killed by an admin (`POST /v1/agents/{slug}/kill`): the app keeps the others.
KILLED = "killed"
# `error` code on a frame the database did not answer in time: the app sends it again.
BUSY = "busy"
NOT_JSON = "a frame is one JSON object: this one did not parse"
DIAL = (
    "call.dial is not answered on the app socket: POST /v1/agents/{slug}/dial places a call, with the talk scope "
    "and the org's outbound guards"
)
THE_DESKS = (
    "supervisor.verb is the desk's to send, for a person and with their key: an app's socket takes none, "
    "so no app speaks in a supervisor's name"
)
NO_SESSION = "{kind} names call {call!r}, which is not running here"
# Where an opt-out the agent heard came from, as the do-not-call list says it.
ASKED_THE_AGENT = "the caller asked the agent"
NOBODY_WAITING = (
    "no tool call {call_id} is waiting on call {call!r}: it lapsed, it was answered, or the call is not here"
)
NOBODY_ASKED = "no dev.request {id} is waiting: it lapsed, it was answered, or another gateway asked it"
PLATFORMS_OWN = "{name} is the platform's own tool and the session answers it: an app answers none"
# How long the socket's first frame waits for its inbox to be asked of the signal.
INBOX_HEARD_WITHIN_S = 5.0


class AppSocket:
    """One connected app: its key, its scope, and every frame it sends answered."""

    def __init__(
        self,
        live: LiveParts,
        threads: Threads,
        claim_code: ClaimCode,
        actor: Actor,
        send: SendFrame,
        close: Close,
        address: str | None,
    ) -> None:
        """A socket that holds nothing yet."""
        self.live = live
        self.threads = threads
        self.actor = actor
        self.scope = actor.scope
        self.id: SocketId = new_socket_id()
        self.address = address
        self.connected_at = time.time()
        self._claim_code = claim_code
        self._send = send
        self._close = close
        # Set once the inbox was asked of the signal, heard on or not: what other gateways tell the socket
        # before that is lost, so the endpoint reads the socket's first frame only after.
        self.listening = asyncio.Event()
        # What each agent this socket holds declares: the row its class kept until it declares it
        # here, then what it sent. A socket's first declaration of an agent is the class whole.
        self.held: dict[str, Declaration] = {}
        self.configured: set[str] = set()

    @property
    def holders(self) -> Holders:
        """Who holds which agent, on every gateway."""
        return self.live.holders

    @property
    def sockets(self) -> Sockets:
        """The sockets open, on every gateway."""
        return self.live.sockets

    # The socket's life: shown in the org's list of apps, its inbox heard, and at the end its calls
    # parked and handed on. A call another gateway binds to this socket tells it on the inbox: heard
    # from the first frame on, or an app that registered at once could miss the call bound to it.
    @contextlib.asynccontextmanager
    async def open(self) -> AsyncGenerator[None]:
        """The socket open: said to the org, its inbox listened to; gone, with its calls handed on, after."""
        scope = Scoped(org=self.scope.org, env=self.scope.env, holder=self.scope.holder)
        row = SocketRow(app=self.id, scope=scope, address=self.address, connected_at=self.connected_at)
        self.sockets.connect(row, self)
        inbox = box_task(APP_INBOX.listen(self.live.signal, self.hear, asked=self.listening, app=self.id))
        try:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.listening.wait(), INBOX_HEARD_WITHIN_S)
            yield
        finally:
            inbox.cancel()
            await asyncio.gather(inbox, return_exceptions=True)
            await self.leave()

    async def send(self, entry: Entry) -> None:
        """One entry down the socket, as the log holds it."""
        await self._send(entry.dump())

    async def stop(self, why: str) -> None:
        """Tell the app it was stopped, and close: it exits instead of reconnecting."""
        stopped = ErrorEvent(code=STOPPED, message=why, recoverable=False)
        await self.send(Entry.make_unstored("", "error", stopped.dump()))
        await self._close(why)

    # The app keeps its other agents; the killed one's calls move as on a drain, to whoever else
    # holds it, else parked. The error tells the app not to declare it again when it reconnects.
    # The socket lets go of the agent now, so its calls stop going down it at once: they are parked
    # before the agent is let go of, and handed on after.
    async def kill(self, slug: str, why: str) -> None:
        """Tell the app one of its agents was killed, and let go of it here."""
        if self.holders.find_on_socket(self.id, self.scope.env, slug) is None:
            return
        killed = ErrorEvent(code=KILLED, message=why, recoverable=False)
        await self.send(Entry.make_unstored(slug, "error", killed.dump()))
        theirs = self.live.calls.list_bound_to(self.id, slug)
        for served in theirs:
            self.live.calls.bind(served.call, None)
        await self.holders.let_go_of(self.id, self.scope.env, slug)
        self.held.pop(slug, None)
        await handoff.hand_on(self.live.calls, self.holders, self.id, theirs)

    async def take(self, raw: Json) -> None:
        """One frame: its command applied, or refused in an error that names it."""
        try:
            command = Command.parse(raw, "command")
        except ValidationError as refused:
            await self.refuse(_read_name(raw, "agent"), commands.BAD_SHAPE, str(refused), raw)
            return
        if command.type not in COMMANDS:
            await self.refuse(
                command.agent, "unknown_command", f"the protocol has no command called {command.type!r}", raw
            )
            return
        try:
            await self._apply(command)
        except QuotaExceeded as refused:
            await self.refuse(command.agent, commands.REFUSED, str(refused), raw)
        except PinecallError as refused:
            code = commands.BAD_SHAPE if isinstance(refused, ValidationError) else commands.REFUSED
            await self.refuse(command.agent, code, str(refused), raw)
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
    async def hear(self, message: ForApp) -> None:
        """One message of the inbox, applied."""
        if message.bound is not None:
            await self._bind(message.bound)
        if message.entry is not None:
            await self.send(message.entry)
        if message.stop is not None:
            await self.stop(message.stop)
        if message.kill is not None:
            await self.kill(message.kill.agent, message.kill.why)

    # The socket is gone, so its calls stop going down it at once: parked before its agents are let
    # go of, and handed on after, to whoever holds them then.
    async def leave(self) -> None:
        """The app went: its calls outlive the socket, parked, then handed to the next holder."""
        self.sockets.disconnect(self.id)
        bound = self.live.calls.list_bound_to(self.id)
        for served in bound:
            self.live.calls.bind(served.call, None)
        await self.holders.release(self.id)
        await handoff.hand_on(self.live.calls, self.holders, self.id, bound)

    async def refuse(self, slug: str, code: str, message: str, raw: Json) -> None:
        """An error naming the command refused and its id; on the agent's log when it holds one."""
        text = ErrorEvent(
            code=code,
            message=message,
            command=_read_name(raw, "type") or None,
            id=_read_name(raw, "id") or None,
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
                if not await self.sockets.answer_dev(model):
                    await self.refuse(command.agent, "no_session", NOBODY_ASKED.format(id=model.id), command.dump())
            case ToolResult():
                await self._answer_tool(command, model)
            case CallClaim() | CallOptOut():
                await self._answer_here(command, model)
            case CallDial():
                await self.refuse(command.agent, "no_handler", DIAL.format(slug=command.agent), command.dump())
            # The body never says who sent it: the credential does. Until 2026-11 this fell through to
            # the call, and an app could leave `supervisor.took_over` in any person's name on its log.
            case SupervisorVerb():
                await self.refuse(command.agent, commands.REFUSED, THE_DESKS, command.dump())
            case PromptSet():
                await self._set_prompt(command, model)
            case _:
                await self._send_to_the_call(command, model)

    async def _register(self, slug: str, wanted: AgentRegister) -> None:
        accounts.check_agent(self.actor, slug)
        if not agents.is_studio_key(self.actor.key_id) and self.holders.is_held_as(
            self.scope, slug, agents.BUILT_IN_STUDIO
        ):
            raise Conflict(
                f"{slug} is a Studio agent of this org: Studio holds it, so give your app's agent another name"
            )
        self.sockets.name(self.id, wanted.host)
        scope = self.scope
        try:
            async with self.live.sessions.begin() as session_:
                # What the registry writes is the registration as answered: the routes the agent really has.
                routes = await telephony.list_answered_routes(session_, scope, slug, wanted.routes)
                # The stock is held while it is counted, so two agents registered at the limit are
                # admitted in turn. The count is the sockets': every slug the org holds but this one.
                await billing.hold_stock(session_, scope.org, scope.env, "agents")
                others = self.holders.slugs_of(scope.org) - {slug}
                await billing.admit_agent(session_, scope.org, scope.env, holding=len(others))
                # A slug is one org's: its log is claimed and then asked whose it is, in that order, so
                # of two orgs registering one slug nobody held, one reads the other's name here.
                if await calls.claim_agent_log(session_, slug, scope.org) != scope.org:
                    raise AnotherOrgs(slug)
                # A call that arrives before agent.configure still runs on what the agent declared.
                kept = await agents.declaration_of(session_, scope, slug)
        except QuotaExceeded as refused:
            async with self.live.sessions.begin() as own:
                await self.live.alerting.credits_exhausted(own, scope, slug, refused)
            raise
        answered = wanted.model_copy(update={"routes": routes})
        declaration = kept or Declaration(slug=slug)
        registered = await self.holders.register(self.id, scope, slug, answered, declaration)
        self.held[slug] = declaration
        await self.send(registered)
        # A console takes no call it did not open; an app takes the calls a previous one left, on
        # this gateway and on the others, which are told it took the agent.
        if wanted.takes_unclaimed:
            await handoff.attach_parked(self.live.calls, scope, slug, self.id)
            handoff.tell_taking(self.live.calls, scope, slug, self.id)

    # A class that searches with no base attached, gives a plugin options on a key the box lends,
    # or asks ears that cannot end the turn to, is refused when it is declared, not mid-call; so are a
    # judge or a persona the class declares that a PUT would refuse.
    async def _configure(self, slug: str, wanted: AgentConfigure) -> None:
        found = self._holds(slug)
        first = slug not in self.configured
        declaration = agents.declare(self.held.get(slug) or Declaration(slug=slug), wanted.config, first=first)
        async with self.live.sessions.begin() as session_:
            catalog = await providers.get_catalog(session_)
            running = (await agents.resolve_for_call(session_, declaration, self.scope, catalog)).declaration
            if declaration.uses_knowledge and not running.bases:
                raise ValidationError(
                    f"{slug} searches its bases, and none is attached to it in {self.scope.env}: pinecall docs "
                    f"attach <base> --agent {slug}"
                )
            keyring = await providers.keys_of(session_, self.live.vault, self.scope)
            providers.refuse_what_cannot_run(running, catalog, keyring)
            await judging.check_declaration(session_, catalog, keyring, self.scope.org, slug, declaration)
            # Kept past this socket: what the class fixes is read from here once nobody holds the agent.
            await agents.put_declaration(session_, self.scope, slug, wanted.config, sdk=found.sdk, first=first)
        changed = agents.list_changes(wanted.config)
        await self.send(await self.holders.configure(self.id, self.scope.env, slug, declaration, changed))
        self.held[slug] = declaration
        self.configured.add(slug)
        # Said now: what waited on WhatsApp for this agent is answered on this declaration.
        if found.takes_unclaimed:
            self.threads.answer_waiting(self._holds(slug))

    # A deploy: the calls move now, and the socket keeps the agent so its tools still answer. The
    # socket is alive, so each call goes on down it until the moment it is handed to another.
    async def _drain(self, slug: str) -> None:
        self.holders.drain(self.id, self.scope.env, slug)
        mine = self.live.calls.list_bound_to(self.id, slug)
        handed, parked = await handoff.hand_on(self.live.calls, self.holders, self.id, mine)
        env = self.scope.env
        await self.send(await self.holders.write_draining(self.id, env, slug, handed=handed, parked=parked))

    # The worker may have asked another gateway: the answer is written on the call's log here,
    # once per call id, and whoever waits reads it there.
    async def _answer_tool(self, command: Command, result: ToolResult) -> None:
        self._holds(command.agent)
        # The session writes end_call's result itself: an app's would be a second one, and could win.
        if result.name == session.END_CALL:
            why = PLATFORMS_OWN.format(name=session.END_CALL)
            await self.refuse(command.agent, commands.REFUSED, why, command.dump())
            return
        served = self.live.calls.find(command.call)
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
    async def _answer_here(self, command: Command, wanted: CallClaim | CallOptOut) -> None:
        self._holds(command.agent)
        served = self.live.calls.find(command.call)
        if served is None or served.agent != command.agent:
            await self.refuse(
                command.agent, "no_session", NO_SESSION.format(kind=command.type, call=command.call), command.dump()
            )
            return
        try:
            async with self.live.sessions.begin() as session_:
                if isinstance(wanted, CallOptOut):
                    await _opt_out(session_, served, command.agent, wanted)
                    return
                claimed = await self._claim_code(session_, served, wanted.code)
        except PinecallError as refused:
            await served.log.append("error", _refusal(command, commands.REFUSED, str(refused)).dump())
            raise
        if not claimed:
            why = str(NoSuchCode(wanted.code, command.agent))
            await served.log.append("error", _refusal(command, "no_code", why).dump())
            await self.refuse(command.agent, "no_code", why, command.dump())

    # The block's words are kept once under the hash the log will name, before the call hears it.
    async def _set_prompt(self, command: Command, wanted: PromptSet) -> None:
        self._holds(command.agent)
        async with self.live.sessions.begin() as session_:
            await self.live.prompts.keep(session_, self.scope.org, wanted.text)
        await self._send_to_the_call(command, wanted)

    # A written call runs here and takes the command at once; a voice call's worker reads it
    # off its command stream and applies it with the same function (`commands.deliver`). A refusal is
    # on the call's log already: it is answered down this socket, and written on no other log.
    async def _send_to_the_call(self, command: Command, model: WireModel) -> None:
        self._holds(command.agent)
        delivered = await commands.deliver(self.live.calls, self.live.signal, command)
        if delivered.refusal is not None:
            await self.send(Entry.make_unstored(command.agent, "error", delivered.refusal.dump()))
            return
        # The app's word after its end hook, for a call that was sealed already: nothing waits for it.
        if delivered.reached or isinstance(model, CallDone):
            return
        await self.refuse(
            command.agent, "no_session", NO_SESSION.format(kind=command.type, call=command.call), command.dump()
        )

    async def _bind(self, bound: Bound) -> None:
        async with self.live.sessions.begin() as session_:
            served = await openings.find_served(session_, self.live, bound.call)
        if served is None:
            # Never silent: a call bound here that this gateway cannot serve is a call whose app
            # will not hear it, and its opener's fault (the opening must be committed before it is told).
            logger.warning(
                "call %s was bound to socket %s, and this gateway has no opening to serve it from", bound.call, self.id
            )
            return
        if not self.sockets.is_here(self.id) or self.live.calls.has_pump(bound.call):
            return
        self.live.calls.bind(bound.call, self.id)
        waiting = folds.list_unanswered_tools(await served.log.privacy.open_all()) if bound.after else []
        self.live.calls.start_pump(bound.call, after=bound.after, then=waiting)

    def _holds(self, slug: str) -> Registration:
        registration = self.holders.find_on_socket(self.id, self.scope.env, slug)
        if registration is None:
            raise NotRegistered(slug)
        return registration

    # On the agent's log only when this socket holds the agent: a slug is one org's, and a frame
    # naming any other is answered down the socket alone, so nothing of it lands on a log.
    async def _emit(self, slug: str, kind: str, event: WireModel) -> None:
        if self.holders.find_on_socket(self.id, self.scope.env, slug) is None:
            await self.send(Entry.make_unstored(slug, kind, event.dump()))
            return
        await self.send(await self.live.logs.agent(slug).append(kind, event.dump()))


# Each socket keeps its other agents; the one killed is told why, and declares it no more.
async def kill_agent(sockets: Sockets, holders: Holders, org: str, env: Env, slug: str, why: str) -> list[SocketId]:
    """Every socket holding the agent in the org's env, in any scope, told to let go of it; their ids."""
    holding = holders.sockets_holding(org, env, slug)
    killed: list[SocketId] = []
    for row in sockets.apps_of(org, env):
        if row.app in holding:
            await sockets.kill(row.app, slug, why)
            killed.append(row.app)
    return killed


def _read_name(raw: Json, field: str) -> str:
    if not isinstance(raw, dict):
        return ""
    named = raw.get(field)
    return named if isinstance(named, str) else ""


def _refusal(command: Command, code: str, why: str) -> ErrorEvent:
    return ErrorEvent(code=code, message=why, command=command.type, id=command.id, recoverable=True)


# The list is the org's, not the call's, and nothing lands in the log: an SDK that predates the
# command would refuse to read an entry it has no shape for.
async def _opt_out(session_: AsyncSession, served: Served, agent: str, wanted: CallOptOut) -> None:
    if served.context.channel is not Channel.phone:
        raise ValidationError(f"call {served.call} has no phone number at its far end: nothing to put on the list")
    given = compliance.Given(
        kind=ConsentKind.opt_out, source=ASKED_THE_AGENT, given_by=f"agent:{agent}", text=wanted.note, call=served.call
    )
    await compliance.give_consent(session_, served.scope, served.context.caller, given)
