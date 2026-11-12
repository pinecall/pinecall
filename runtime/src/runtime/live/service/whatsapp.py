"""The WhatsApp threads this gateway keeps open, one per contact, and the messages that wait for an agent."""

import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.calls import service as calls
from runtime.calls.context import CallContext, Contact, Route, new_call_id
from runtime.calls.log import Logs, Store
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import PinecallError, UpstreamError
from runtime.kit.loops import survive
from runtime.kit.time import today_in
from runtime.live.holders import Registration
from runtime.live.parts import LiveParts
from runtime.live.peers import THREADS, ThreadKey
from runtime.live.service import written
from runtime.scoping import box_task
from runtime.session import service as session
from runtime.telephony import service as telephony
from runtime.telephony.models import Route as RouteRow
from runtime.whatsapp import service as whatsapp
from runtime.wire.base import Entry
from runtime.wire.events import ErrorEvent, MessageTaken, MessageWaiting
from runtime.wire.signal import HandedMessage

logger = logging.getLogger(__name__)

WAITING = "message.waiting"
TAKEN = "message.taken"
NOT_SENT = "whatsapp_not_sent"

# A conversation quiet this long is over: the next message opens a new call. It is under
# Meta's 24 h customer-service window, which only the idle close keeps.
IDLE_S = 2 * 60 * 60
# Meta lets a business write freely only this long after the contact's last message
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages).
WINDOW_S = 24 * 60 * 60

# However the call ends, the conversation is over with it: a written call a supervisor ends
# only says so, and its session is closed here.
OVER = {"call.ended", "supervisor.ended"}


@dataclass(frozen=True, slots=True)
class Waiting:
    """A message kept for an agent nobody held when it arrived."""

    agent: str
    env: Env
    inbound: whatsapp.Inbound
    received_at: float


@dataclass(slots=True)
class OpenThread:
    """One contact's open conversation: its session, the token it replies with, what is unread."""

    session: session.Session
    inbound: whatsapp.Inbound
    http: httpx.AsyncClient
    token: str
    # A None is the call over: the desk ended it, or it was hung up some other way.
    heard: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue[str | None])
    serving: asyncio.Task[None] | None = None

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
            await whatsapp.send_text(self.http, self.token, self.inbound, answer)
        except (UpstreamError, httpx.HTTPError) as refused:
            error = ErrorEvent(code=NOT_SENT, message=str(refused), recoverable=True)
            # Queued, not awaited: the queue is the one appending the entry this tap runs on.
            self.session.call.writing.write("error", error)


# What `whatsapp`'s webhook is handed (`whatsapp.service.Threads`): the contacts' conversations.
class Threads:
    """The open WhatsApp threads of this process, keyed by org, env, number and contact."""

    def __init__(self, live: LiveParts) -> None:
        """No conversation open and nothing waiting until `load` reads the logs."""
        self._live = live
        self.idle_s: float = IDLE_S
        self._open: dict[ThreadKey, OpenThread] = {}
        self._waiting: list[Waiting] = []
        self._answering: set[asyncio.Task[None]] = set()
        self._handed: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Take the messages other gateways hand on for the threads held here."""
        owner = self._live.owners.id
        self._handed = box_task(THREADS.listen(self._live.signal, self._take_on, gateway=owner))

    async def load(self) -> None:
        """What was waiting when this process started, read back off the agents' logs."""
        self._waiting = await list_waiting(self._live.store)

    async def close(self) -> None:
        """Stop answering: the threads stay open in their logs for the next process."""
        tasks = [thread.serving for thread in self._open.values() if thread.serving is not None]
        tasks += list(self._answering)
        tasks += [] if self._handed is None else [self._handed]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._open.clear()

    # Meta delivers a message again when it thinks it unanswered: it is claimed before it is read,
    # marked read once queued or kept, and a reading that fails gives the claim back, each in a
    # transaction of its own (`whatsapp.read_once`). The route is read on a session of its own and
    # handed back before the message is heard: until 2026-11 the webhook's one session stayed open
    # while a conversation opened, which may wait on the model.
    async def receive(self, inbound: whatsapp.Inbound) -> bool:
        """Read the message once, onto its contact's conversation; False while another reads it."""
        async with self._live.sessions.begin() as session_:
            route = await _find_route(session_, inbound)
        if route is None:
            return True

        async def read() -> None:
            await self._hear(route, inbound)

        return await whatsapp.read_once(self._live.sessions, route.org, inbound.message_id, read, at=self._live.now)

    # Off the app socket's own loop: opening a conversation may wait on the model.
    def answer_waiting(self, registration: Registration) -> None:
        """Answer the messages that waited for this agent, now that somebody holds it."""
        if not any(waiter.agent == registration.slug for waiter in self._waiting):
            return
        task = asyncio.create_task(self._answer_waiting(registration))
        self._answering.add(task)
        task.add_done_callback(self._answering.discard)

    # ── private ──

    # Returns once the message is queued or kept: Meta sends a slow webhook again.
    # A contact's thread is held by one gateway: a message landing on another is handed to it,
    # and taken here only when nobody holds it, or its holder no longer listens. `kept` is the
    # message when it waited already: it waits on as it was, and is written on no log a second time.
    async def _hear(self, route: RouteRow, inbound: whatsapp.Inbound, kept: Waiting | None = None) -> bool:
        """Put the message on its contact's conversation; False when it waits for somebody to hold the agent."""
        scope = Scope(route.org, route.env)
        registration = self._live.holders.find_ring_taker(scope, route.agent, inbound.caller)
        key = _thread_key(registration.scope if registration else scope, inbound)
        thread = self._open.get(key)
        holder = self._live.owners.find_thread_holder(key)
        if (
            thread is None
            and holder is not None
            and await THREADS.reach(self._live.signal, _hand(inbound), gateway=holder)
        ):
            logger.info("whatsapp: a message for %s was handed to the gateway holding its thread", inbound.number)
            return True
        if thread is None and registration is None:
            self._waiting.append(kept or await keep_waiting(self._live.logs, self._live.store, route, inbound))
            logger.warning(
                "whatsapp: nobody holds agent %s, so a message to %s waits for somebody", route.agent, inbound.number
            )
            return False
        if thread is None and registration is not None:
            thread = await self._open_thread(registration, route, inbound)
        if thread is not None:
            thread.heard.put_nowait(inbound.text)
        return True

    # Oldest first, so one contact's messages reach their conversation in order. A message that
    # goes back to waiting (whoever held the agent left meanwhile) is not marked taken: until 2026-11
    # it was, and after a restart it was read as taken and lost.
    async def _answer_waiting(self, registration: Registration) -> None:
        now = self._live.store.clock()
        for waiting in [waiter for waiter in self._waiting if waiter.agent == registration.slug]:
            if waiting.env != registration.scope.env:
                continue
            self._waiting.remove(waiting)
            if now - waiting.received_at > WINDOW_S:
                logger.warning("whatsapp: a message to agent %s outlived Meta's window unanswered", waiting.agent)
                await mark_taken(self._live.logs, waiting, None)
                continue
            # Claimed and read when it was kept: it is heard, not received again.
            async with self._live.sessions.begin() as session_:
                route = await _find_route(session_, waiting.inbound)
            if route is not None and not await self._hear(route, waiting.inbound, waiting):
                continue
            opened = self._open.get(_thread_key(registration.scope, waiting.inbound))
            await mark_taken(self._live.logs, waiting, None if opened is None else opened.session.call.context.call)

    # The token and the call are read and written in a transaction of this conversation's own, over
    # before the session starts: its greeting may wait on the model.
    async def _open_thread(
        self, registration: Registration, route: RouteRow, inbound: whatsapp.Inbound
    ) -> OpenThread | None:
        live = self._live
        async with live.sessions.begin() as session_:
            token = await telephony.meta_token_for(session_, live.vault, route.org, inbound.phone_number_id)
            if token is None:
                logger.warning(
                    "whatsapp: agent %s cannot answer at %s: no Meta token here", route.agent, inbound.number
                )
                return None
            try:
                taken = await self._take_up(session_, registration, inbound)
                running = taken or await written.open_written(
                    session_, live, registration, self._context(registration, route, inbound)
                )
            except PinecallError as refused:
                logger.warning("whatsapp: agent %s cannot answer at %s: %s", route.agent, inbound.number, refused)
                return None
        thread = OpenThread(session=running, inbound=inbound, http=live.http, token=token)
        # Before the session starts, so every turn the contact is owed reaches them.
        served = live.calls.find(running.call.context.call)
        if served is not None:
            served.log.tap(thread.reply)
        if taken is None:
            await running.start()
        key = _thread_key(registration.scope, inbound)
        self._open[key] = thread
        live.owners.hold_thread(key, here=True)
        thread.serving = asyncio.create_task(self._serve(key, thread))
        return thread

    # Claimed and read by the gateway it landed on: here it is only heard.
    async def _take_on(self, handed: HandedMessage) -> None:
        inbound = whatsapp.Inbound(
            number=handed.number,
            phone_number_id=handed.phone_number_id,
            wa_id=handed.wa_id,
            name=handed.name,
            message_id=handed.message_id,
            kind=handed.kind,
            text=handed.text,
        )
        async with self._live.sessions.begin() as session_:
            route = await _find_route(session_, inbound)
        if route is not None:
            await self._hear(route, inbound)

    # A conversation this process never saw is taken up from its log while it has idle time left.
    async def _take_up(
        self, session_: AsyncSession, registration: Registration, inbound: whatsapp.Inbound
    ) -> session.Session | None:
        newest = await calls.find_newest_call_with(session_, registration.scope, registration.slug, inbound.caller)
        if newest is None:
            return None
        entries = await calls.list_entries(session_, newest)
        if not entries or self._live.store.clock() - entries[-1].ts > self.idle_s:
            return None
        return await written.resume_written(session_, self._live, registration, newest)

    def _context(self, registration: Registration, route: RouteRow, inbound: whatsapp.Inbound) -> CallContext:
        answering = Route(
            org=route.org, agent=registration.slug, channel=Channel.whatsapp, number=route.number, env=route.env
        )
        return CallContext(
            call=new_call_id(),
            channel=Channel.whatsapp,
            direction=Direction.inbound,
            caller=inbound.caller,
            route=answering,
            today=today_in(self._live.settings.timezone),
            contact=Contact(phone=inbound.caller, name=inbound.name),
            holder=registration.scope.holder or None,
        )

    # The idle period starts once every message is answered: a slow turn is never cut off. Each turn
    # is admitted before the model is asked (`written.hear`); a refusal ends the call, and the thread.
    async def _serve(self, key: ThreadKey, thread: OpenThread) -> None:
        running = thread.session
        call = running.call.context.call
        try:
            # The agent hung up on a message: the thread is over, the contact's next one opens a call.
            while not running.closed:
                try:
                    answer = await asyncio.wait_for(thread.heard.get(), timeout=self.idle_s)
                except TimeoutError:
                    await session.end(running, "timeout", "platform")
                    return
                if answer is None:
                    await running.close()
                    return
                # One message that cannot be answered is said with its call: the contact's next one is.
                with survive("answering a WhatsApp message", call):
                    if await written.hear(self._live, running, answer) is not None:
                        return
        finally:
            self._open.pop(key, None)
            self._live.owners.hold_thread(key, here=False)
            self._live.calls.close_call(call)
            self._live.logs.forget(call)


async def keep_waiting(logs: Logs, store: Store, route: RouteRow, inbound: whatsapp.Inbound) -> Waiting:
    """Keep the message on the agent's log until somebody holds the agent."""
    now = store.clock()
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


async def list_waiting(store: Store) -> list[Waiting]:
    """Every message still waiting, oldest first, read off every agent's log."""
    waiting: dict[str, Waiting] = {}
    after = 0
    while page := await store.list_across([WAITING, TAKEN], after=after):
        for row in page:
            entry = row.entry
            if entry.type == TAKEN:
                waiting.pop(str(entry.data.get("message_id")), None)
                continue
            message = MessageWaiting.model_validate(entry.data)
            inbound = whatsapp.Inbound(
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


def _thread_key(scope: Scope, inbound: whatsapp.Inbound) -> ThreadKey:
    return ThreadKey(scope.org, scope.env, inbound.number, inbound.wa_id)


def _hand(inbound: whatsapp.Inbound) -> HandedMessage:
    return HandedMessage(
        number=inbound.number,
        phone_number_id=inbound.phone_number_id,
        wa_id=inbound.wa_id,
        name=inbound.name,
        message_id=inbound.message_id,
        kind=inbound.kind,
        text=inbound.text,
    )


async def _find_route(session_: AsyncSession, inbound: whatsapp.Inbound) -> RouteRow | None:
    if inbound.kind != "text" or not inbound.text:
        logger.warning("whatsapp: a %s to %s was dropped: only text is read", inbound.kind or "message", inbound.number)
        return None
    route = await telephony.find_route_at(session_, Channel.whatsapp, inbound.number)
    if route is None:
        logger.warning(
            "whatsapp: nobody answers %s: `pinecall numbers import %s --channel whatsapp` routes it",
            inbound.number,
            inbound.number,
        )
    return route
