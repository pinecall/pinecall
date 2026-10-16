"""The WhatsApp threads this gateway keeps open, one per contact; the endpoints: endpoints/threads."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.context import CallContext, Contact, Route, new_call_id
from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.repository.inbox import InboxRepository
from pinecall_runtime.calls.service.peers import THREAD_CHANNEL
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.text import open_text, resume_text, tokens_of
from pinecall_runtime.calls.store import Store
from pinecall_runtime.channels import service as channels
from pinecall_runtime.channels.models import Route as RouteRow
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.exceptions import (
    PinecallError,
    QuotaExceeded,
    ServiceUnavailable,
    UpstreamError,
)
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.time import today_in
from pinecall_runtime.postgres import box_task
from pinecall_runtime.session import service as session
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import ErrorEvent, MessageTaken, MessageWaiting

# One conversation: the number written to, and who wrote.
type ThreadKey = tuple[str, str, str, str]

logger = logging.getLogger(__name__)

WAITING = "message.waiting"
TAKEN = "message.taken"
NOT_SENT = "whatsapp_not_sent"

# How long the listener for messages handed on waits for the signal before listening again.
HANDED_RETRY_S = 1.0

# However the call ends, the conversation is over with it: a written call a supervisor ends
# only says so, and its session is closed here.
OVER = {"call.ended", "supervisor.ended"}

_INBOUND: TypeAdapter[channels.Inbound] = TypeAdapter(channels.Inbound)


@dataclass(frozen=True)
class Waiting:
    """A message kept for an agent nobody held when it arrived."""

    agent: str
    env: Env
    inbound: channels.Inbound
    received_at: float


@dataclass
class OpenThread:
    """One contact's open conversation: its session, the token it replies with, what is unread."""

    session: session.Session
    inbound: channels.Inbound
    http: httpx.AsyncClient
    token: str
    # A None is the call over: the desk ended it, or it was hung up some other way.
    heard: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue[str | None])
    served: asyncio.Task[None] | None = None

    # The model's turns, the agent's `say` and a supervisor's reach the contact on one path.
    async def reply(self, entry: Entry) -> None:
        """Send a durable turn.agent to the contact; Meta's refusal is an error on the call."""
        if entry.type in OVER:
            self.heard.put_nowait(None)
            return
        answer = entry.data.get("text")
        if entry.type != "turn.agent" or entry.ephemeral or not isinstance(answer, str) or not answer:
            return
        try:
            await channels.send_text(self.http, self.token, self.inbound, answer)
        except (UpstreamError, httpx.HTTPError) as refused:
            error = ErrorEvent(code=NOT_SENT, message=str(refused), recoverable=True)
            # Queued, not awaited: the queue is the one appending the entry this tap runs on.
            self.session.call.writing.write("error", error)


class Threads:
    """The open WhatsApp threads of this process, keyed by org, env, number and contact."""

    def __init__(self, serving: Serving, registry: agents_registry.AgentRegistry) -> None:
        """No conversation open and nothing waiting until `load` reads the logs."""
        self.serving = serving
        self.registry = registry
        self.idle_s: float = channels.IDLE_S
        self.open: dict[ThreadKey, OpenThread] = {}
        self.waiting: list[Waiting] = []
        self.answering_now: set[asyncio.Task[None]] = set()
        self.handed: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Take the messages other gateways hand on for the threads held here."""
        self.handed = box_task(self._handed_here())

    async def load(self) -> None:
        """What was waiting when this process started, read back off the agents' logs."""
        self.waiting = await waiting_in(self.serving.logs.store)

    async def close(self) -> None:
        """Stop answering: the threads stay open in their logs for the next process."""
        tasks = [value.served for value in self.open.values() if value.served is not None]
        tasks += list(self.answering_now)
        tasks += [] if self.handed is None else [self.handed]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.open.clear()

    # Meta delivers a message again when it thinks it unanswered. The row is claimed before the
    # message is read, so of two deliveries at once only one reads it; it is marked read once the
    # message is queued or kept, and a reading that fails gives the claim back, so Meta's next
    # delivery reads it again. A process that dies mid-reading leaves a claim its lease expires.
    async def receive(self, session_: AsyncSession, inbound: channels.Inbound) -> bool:
        """Read the message once, onto its contact's conversation; False while another reads it."""
        route = await _route_of(session_, inbound)
        if route is None:
            return True
        now = datetime.fromtimestamp(self.serving.logs.store.clock(), UTC)
        claim = await channels.claim_message(session_, route.org, inbound.message_id, at=now)
        if claim != "new":
            logger.info("whatsapp: message %s delivered again, dropped: %s", inbound.message_id, claim)
            return claim == "seen"
        try:
            await self._hear(session_, route, inbound)
        except Exception:
            await channels.release_message(session_, route.org, inbound.message_id)
            raise
        await channels.mark_message_read(session_, route.org, inbound.message_id, at=now)
        return True

    # Returns once the message is queued or kept: Meta sends a slow webhook again.
    # A contact's thread is held by one gateway: a message landing on another is handed to it,
    # and taken here only when nobody holds it, or its holder no longer listens.
    async def _hear(self, session_: AsyncSession, route: RouteRow, inbound: channels.Inbound) -> None:
        scope = Scope(route.org, route.env)
        registration = self.registry.taking_a_ring(scope, route.agent, inbound.caller)
        key = _thread_key(registration.scope if registration else scope, inbound)
        thread = self.open.get(key)
        holder = self.serving.live.owners.threads_elsewhere.get("|".join(key))
        if thread is None and holder is not None and await self._hand_to(holder, inbound):
            logger.info("whatsapp: a message for %s was handed to the gateway holding its thread", inbound.number)
            return
        if thread is None and registration is None:
            self.waiting.append(await keep_waiting(self.serving.logs, route, inbound))
            logger.warning(
                "whatsapp: nobody holds agent %s, so a message to %s waits for somebody", route.agent, inbound.number
            )
            return
        if thread is None and registration is not None:
            thread = await self._open(session_, registration, route, inbound)
        if thread is not None:
            thread.heard.put_nowait(inbound.text)

    # Off the app socket's own loop: opening a conversation may wait on the model.
    def answer_waiting(self, registration: agents_registry.Registration) -> None:
        """Answer the messages that waited for this agent, now that somebody holds it."""
        if not any(waiter.agent == registration.slug for waiter in self.waiting):
            return
        task = asyncio.create_task(self._answered(registration))
        self.answering_now.add(task)
        task.add_done_callback(self.answering_now.discard)

    # Oldest first, so one contact's messages reach their conversation in order.
    async def _answered(self, registration: agents_registry.Registration) -> None:
        now = self.serving.logs.store.clock()
        for waiting in [waiter for waiter in self.waiting if waiter.agent == registration.slug]:
            if waiting.env != registration.scope.env:
                continue
            self.waiting.remove(waiting)
            if now - waiting.received_at > channels.WINDOW_S:
                logger.warning("whatsapp: a message to agent %s outlived Meta's window unanswered", waiting.agent)
                await mark_taken(self.serving.logs, waiting, None)
                continue
            # Claimed and read when it was kept: it is heard, not received again.
            async with self.serving.handles.sessions.begin() as session_:
                route = await _route_of(session_, waiting.inbound)
                if route is not None:
                    await self._hear(session_, route, waiting.inbound)
            opened = self.open.get(_thread_key(registration.scope, waiting.inbound))
            await mark_taken(self.serving.logs, waiting, None if opened is None else opened.session.call.context.call)

    async def _open(
        self,
        session_: AsyncSession,
        registration: agents_registry.Registration,
        route: RouteRow,
        inbound: channels.Inbound,
    ) -> OpenThread | None:
        handles = self.serving.handles
        token = await telephony.meta_token_for(session_, handles.vault, route.org, inbound.phone_number_id)
        if token is None:
            logger.warning("whatsapp: agent %s cannot answer at %s: no Meta token here", route.agent, inbound.number)
            return None
        try:
            taken = await self._take_up(session_, registration, inbound)
            running = taken or await open_text(
                session_, self.serving, registration, self._context(registration, route, inbound)
            )
        except PinecallError as refused:
            logger.warning("whatsapp: agent %s cannot answer at %s: %s", route.agent, inbound.number, refused)
            return None
        thread = OpenThread(session=running, inbound=inbound, http=handles.http, token=token)
        # Before the session starts, so every turn the contact is owed reaches them.
        served = self.serving.live.calls[running.call.context.call]
        served.log.tap(thread.reply)
        if taken is None:
            await running.start()
        key = _thread_key(registration.scope, inbound)
        self.open[key] = thread
        self.serving.live.owners.holding("|".join(key), here=True)
        thread.served = asyncio.create_task(self._serve(key, thread))
        return thread

    async def _hand_to(self, holder: str, inbound: channels.Inbound) -> bool:
        try:
            return (
                await self.serving.live.signal.published(
                    THREAD_CHANNEL.format(gateway=holder), _INBOUND.dump_json(inbound)
                )
                > 0
            )
        except ServiceUnavailable:
            return False

    # Claimed and read by the gateway it landed on: here it is only heard.
    async def _handed_here(self) -> None:
        signal = self.serving.live.signal
        channel = THREAD_CHANNEL.format(gateway=self.serving.live.owners.id)
        while True:
            try:
                listener = await signal.subscribe(channel)
            except ServiceUnavailable:
                await asyncio.sleep(HANDED_RETRY_S)
                continue
            try:
                async for data in listener:
                    await self._take_on(_INBOUND.validate_json(data))
            finally:
                listener.close()
            await asyncio.sleep(HANDED_RETRY_S)

    async def _take_on(self, inbound: channels.Inbound) -> None:
        async with self.serving.handles.sessions.begin() as session_:
            route = await _route_of(session_, inbound)
            if route is None:
                return
            try:
                await self._hear(session_, route, inbound)
            except PinecallError as refused:
                logger.warning("whatsapp: a message handed on by another gateway was not read: %s", refused)

    # A conversation this process never saw is taken up from its log while it has idle time left.
    async def _take_up(
        self, session_: AsyncSession, registration: agents_registry.Registration, inbound: channels.Inbound
    ) -> session.Session | None:
        newest = await InboxRepository(session_).calls_with(
            registration.scope, registration.slug, inbound.caller, limit=1
        )
        if not newest:
            return None
        entries = await self.serving.logs.store.whole(newest[0])
        if not entries or self.serving.logs.store.clock() - entries[-1].ts > self.idle_s:
            return None
        return await resume_text(
            session_, self.serving, registration, newest[0], self.serving.handles.settings.timezone
        )

    def _context(
        self, registration: agents_registry.Registration, route: RouteRow, inbound: channels.Inbound
    ) -> CallContext:
        answering = Route(
            org=route.org, agent=registration.slug, channel=Channel.whatsapp, number=route.number, env=route.env
        )
        return CallContext(
            call=new_call_id(),
            channel=Channel.whatsapp,
            direction=Direction.inbound,
            caller=inbound.caller,
            route=answering,
            today=today_in(self.serving.handles.settings.timezone),
            contact=Contact(phone=inbound.caller, name=inbound.name),
            holder=registration.scope.holder or None,
        )

    # The idle period starts once every message is answered: a slow turn is never cut off.
    async def _serve(self, key: ThreadKey, thread: OpenThread) -> None:
        running = thread.session
        route = running.call.context.route
        scope = Scope(route.org, route.env)
        try:
            while True:
                try:
                    answer = await asyncio.wait_for(thread.heard.get(), timeout=self.idle_s)
                except TimeoutError:
                    await session.end_text(running, "timeout", "platform")
                    return
                if answer is None:
                    await running.close()
                    return
                async with self.serving.handles.sessions.begin() as session_:
                    try:
                        await billing.admit_turn(
                            session_,
                            scope.org,
                            scope.env,
                            turns=running.call.turns,
                            tokens=tokens_of(running.usage),
                            at=self.serving.logs.store.clock(),
                        )
                    except QuotaExceeded as refused:
                        await alerts.credits_exhausted(
                            session_, self.serving.handles, self.serving.logs, scope, running.call.config.slug, refused
                        )
                        await session.end_text(running, "timeout", "platform")
                        return
                try:
                    await session.hear_text(running, answer)
                except PinecallError:
                    logger.warning(
                        "whatsapp: a turn of call %s failed and was not answered",
                        running.call.context.call,
                        exc_info=True,
                    )
        finally:
            self.open.pop(key, None)
            self.serving.live.owners.holding("|".join(key), here=False)
            self.serving.live.close_call(running.call.context.call)
            self.serving.logs.forget(running.call.context.call)


async def keep_waiting(logs: Logs, route: RouteRow, inbound: channels.Inbound) -> Waiting:
    """Keep the message on the agent's log until somebody holds the agent."""
    now = logs.store.clock()
    message = MessageWaiting.model_validate(
        {
            "channel": "whatsapp",
            "env": route.env.value,
            "number": inbound.number,
            "phone_number_id": inbound.phone_number_id,
            "from": inbound.wa_id,
            "name": inbound.name,
            "message_id": inbound.message_id,
            "text": inbound.text or "",
            "received_at": now,
        }
    )
    await logs.agent(route.agent).append(WAITING, message.dump())
    return Waiting(route.agent, route.env, inbound, now)


async def mark_taken(logs: Logs, waiting: Waiting, call: str | None) -> None:
    """The message off the queue: the call it went on, or none when its window closed."""
    await logs.agent(waiting.agent).append(TAKEN, MessageTaken(message_id=waiting.inbound.message_id, call=call).dump())


async def waiting_in(store: Store) -> list[Waiting]:
    """Every message still waiting, oldest first, read off every agent's log."""
    waiting: dict[str, Waiting] = {}
    after = 0
    while page := await store.across([WAITING, TAKEN], after=after):
        for row in page:
            entry = row.entry
            if entry.type == TAKEN:
                waiting.pop(str(entry.data.get("message_id")), None)
                continue
            message = MessageWaiting.model_validate(entry.data)
            inbound = channels.Inbound(
                number=message.number,
                phone_number_id=message.phone_number_id,
                wa_id=message.from_,
                name=message.name,
                message_id=message.message_id,
                kind="text",
                text=message.text,
            )
            waiting[message.message_id] = Waiting(entry.agent, Env(message.env), inbound, message.received_at)
        after = page[-1].position
    return list(waiting.values())


def _thread_key(scope: Scope, inbound: channels.Inbound) -> ThreadKey:
    return (scope.org, scope.env.value, inbound.number, inbound.wa_id)


async def _route_of(session_: AsyncSession, inbound: channels.Inbound) -> RouteRow | None:
    if inbound.kind != "text" or not inbound.text:
        logger.warning("whatsapp: a %s to %s was dropped: only text is read", inbound.kind or "message", inbound.number)
        return None
    route = await channels.route_at(session_, Channel.whatsapp, inbound.number)
    if route is None:
        logger.warning(
            "whatsapp: nobody answers %s: `pinecall numbers import %s --channel whatsapp` routes it",
            inbound.number,
            inbound.number,
        )
    return route
