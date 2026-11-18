"""The WhatsApp threads this gateway keeps open, one per contact, and the messages that wait for an agent."""

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.declaration import STOP_MESSAGES
from runtime.calls import service as calls
from runtime.calls.context import CallContext, Contact, Route, new_call_id
from runtime.enums import Direction
from runtime.exceptions import PinecallError, QuotaExceeded, UpstreamError
from runtime.kit.loops import survive
from runtime.kit.time import today_in
from runtime.live.holders import Registration
from runtime.live.parts import LiveParts
from runtime.live.peers import THREADS, ThreadKey
from runtime.live.service import written
from runtime.live.service.opt_outs import Stop, refuses_messages, take_off, take_word
from runtime.live.service.replies import Reaches, way_to
from runtime.live.service.waiting import Waiting, keep_waiting, list_waiting, mark_taken
from runtime.scoping import box_task
from runtime.session import service as session
from runtime.telephony import service as telephony
from runtime.telephony.models import Route as RouteRow
from runtime.whatsapp import service as whatsapp
from runtime.wire.base import Entry
from runtime.wire.events import ErrorEvent, MessageStatus
from runtime.wire.signal import HandedMessage

logger = logging.getLogger(__name__)

# The error a reply the channel refused is said with: `whatsapp_not_sent`, `sms_not_sent`.
NOT_SENT = "{channel}_not_sent"

# A conversation quiet this long is over: the next message opens a new call. It is under
# Meta's 24 h customer-service window, which only the idle close keeps.
IDLE_S = 2 * 60 * 60
# Meta lets a business write freely only this long after the contact's last message
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages).
WINDOW_S = 24 * 60 * 60


# However the call ends, the conversation is over with it: a written call a supervisor ends
# only says so, and its session is closed here.
OVER = {"call.ended", "supervisor.ended"}


# What a conversation's own task takes off its queue: a message, the call over, the contact stopping.
type Heard = whatsapp.Inbound | Stop | None


@dataclass(slots=True)
class OpenThread:
    """One contact's open conversation: its session, the token it replies with, what is unread."""

    session: session.Session
    inbound: whatsapp.Inbound
    reaches: Reaches
    # A None is the call over: the desk ended it, or it was hung up some other way. A Stop is the
    # contact asking for no more messages: the conversation ends once what came before it is done.
    heard: asyncio.Queue[Heard] = field(default_factory=asyncio.Queue[Heard])
    serving: asyncio.Task[None] | None = None
    # Whether the contact asked, in writing, for no more messages; asked of the list before each reply.
    refuses: Callable[[], Awaitable[bool]] | None = None
    stopped: bool = False

    def stop(self, stop: Stop) -> None:
        """Write nothing more to the contact, and end the conversation when its turn comes."""
        self.stopped = True
        self.heard.put_nowait(stop)

    # The model's turns, the agent's `say` and a supervisor's reach the contact on one path.
    async def reply(self, entry: Entry) -> None:
        """Send a durable turn.agent to the contact; the channel's refusal is an error on the call."""
        if entry.type in OVER:
            self.heard.put_nowait(None)
            return
        # The model called the platform's tool: nothing it wrote beside the call is sent.
        if entry.type == "tool.call" and entry.data.get("name") == STOP_MESSAGES and not self.stopped:
            self.stop(Stop(by="agent", written=False, call=entry.call))
            return
        answer = entry.data.get("text")
        if entry.type != "turn.agent" or entry.ephemeral or not isinstance(answer, str) or not answer:
            return
        if self.stopped or (self.refuses is not None and await self.refuses()):
            logger.info(
                "%s: a reply to %s was not sent: they asked for no more",
                self.inbound.channel.value,
                self.inbound.caller,
            )
            return
        try:
            await self.reaches.send(self.inbound, answer)
        except (UpstreamError, httpx.HTTPError) as refused:
            code = NOT_SENT.format(channel=self.inbound.channel.value)
            error = ErrorEvent(code=code, message=str(refused), recoverable=True)
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
        if not inbound.may_reach(route.org, route.account):
            logger.warning(
                "whatsapp: a message to %s was dropped: the Meta app that signed it is not that number's",
                inbound.number,
            )
            return True

        async def read() -> None:
            # A word that stops, starts again or asks who writes is answered before the model is asked.
            open_here = self._open.get(_thread_key(Scope(route.org, route.env), inbound))
            taken = await take_word(
                self._live, route, inbound, None if open_here is None else open_here.session.call.context.call
            )
            if taken == "stop" and open_here is not None:
                open_here.stop(Stop(by="caller"))
            if taken is not None:
                return
            await self._hear(route, inbound)

        return await whatsapp.read_once(self._live.sessions, route.org, inbound.message_id, read, at=self._live.now)

    # A receipt is said on the conversation it belongs to while that is open, on whichever gateway
    # holds it; one for a conversation that went quiet says nothing anybody is reading.
    async def note(self, receipt: whatsapp.Receipt, *, handed: bool = False) -> None:
        """Say on the contact's open conversation where a message the agent wrote stands."""
        async with self._live.sessions.begin() as session_:
            route = await telephony.find_route_at(session_, receipt.channel, receipt.number)
        if route is None or not receipt.may_reach(route.org, route.account):
            return
        scope = Scope(route.org, route.env)
        registration = self._live.holders.find_ring_taker(scope, route.agent, receipt.caller)
        key = _thread_key(registration.scope if registration else scope, receipt)
        thread = self._open.get(key)
        if thread is not None:
            said = MessageStatus(
                message_id=receipt.message_id, status=receipt.status, to=receipt.caller, error=receipt.error
            )
            thread.session.call.writing.write("message.status", said)
            return
        # Handed on once: a receipt another gateway sent here is not sent on again.
        holder = None if handed else self._live.owners.find_thread_holder(key)
        if holder is not None:
            await THREADS.reach(self._live.signal, _hand_receipt(receipt), gateway=holder)

    # The app's own command took the contact off the list: the conversation is told, and ends.
    def stop(self, call: str) -> bool:
        """End the open conversation of this call as one whose contact asked for no more; whether it is here."""
        thread = next((one for one in self._open.values() if one.session.call.context.call == call), None)
        if thread is not None and not thread.stopped:
            thread.stop(Stop(by="agent"))
        return thread is not None

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
            # What waits is kept as its words: a voice note is heard now, with nobody to hand it to.
            worded = None if kept is not None else await self._word(route, inbound)
            if kept is None and worded is None:
                return True
            self._waiting.append(
                kept or await keep_waiting(self._live.logs, self._live.store, route, worded or inbound)
            )
            logger.warning(
                "whatsapp: nobody holds agent %s, so a message to %s waits for somebody", route.agent, inbound.number
            )
            return False
        if thread is None and registration is not None:
            thread = await self._open_thread(registration, route, inbound)
        if thread is not None:
            thread.heard.put_nowait(inbound)
        return True

    # Off the webhook's request wherever it can be: a note for an open conversation is heard by the
    # conversation's own task (`_serve`), and here only when the message waits for an agent.
    async def _word(self, route: RouteRow, inbound: whatsapp.Inbound) -> whatsapp.Inbound | None:
        if inbound.media_id is None:
            return inbound
        async with self._live.sessions.begin() as session_:
            reaches = await way_to(session_, self._live, route, inbound)
        text = None if reaches is None else await reaches.hear_note(inbound)
        return None if text is None else dataclasses.replace(inbound, text=text, media_id=None)

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
            reaches = await way_to(session_, live, route, inbound)
            if reaches is None:
                logger.warning(
                    "%s: agent %s cannot answer at %s: nothing here to answer with (a Meta token, a Twilio account)",
                    inbound.channel.value,
                    route.agent,
                    inbound.number,
                )
                return None
            try:
                taken = await self._take_up(session_, registration, inbound)
                # A new conversation carries on what this contact and the agent last said, on any channel.
                earlier = await calls.find_newest_call_with(
                    session_, registration.scope, registration.slug, inbound.caller
                )
                running = taken or await written.open_written(
                    session_, live, registration, self._context(registration, route, inbound, earlier)
                )
            except PinecallError as refused:
                logger.warning("whatsapp: agent %s cannot answer at %s: %s", route.agent, inbound.number, refused)
                return None
        thread = OpenThread(session=running, inbound=inbound, reaches=reaches)
        thread.refuses = partial(refuses_messages, live, Scope(route.org, route.env), inbound.caller)
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
        if handed.status is not None:
            await self.note(_receipt_of(handed, handed.status), handed=True)
            return
        inbound = whatsapp.Inbound(
            number=handed.number,
            phone_number_id=handed.phone_number_id,
            wa_id=handed.wa_id,
            name=handed.name,
            message_id=handed.message_id,
            kind=handed.kind,
            text=handed.text,
            media_id=handed.media_id,
            channel=handed.channel,
        )
        async with self._live.sessions.begin() as session_:
            route = await _find_route(session_, inbound)
        if route is not None:
            await self._hear(route, inbound)

    # A conversation this process never saw is taken up from its log while it has idle time left.
    async def _take_up(
        self, session_: AsyncSession, registration: Registration, inbound: whatsapp.Inbound
    ) -> session.Session | None:
        contact = (registration.scope, registration.slug, inbound.caller)
        newest = await calls.find_newest_call_with(session_, *contact, inbound.channel)
        if newest is None:
            return None
        entries = await calls.list_entries(session_, newest)
        if not entries or self._live.store.clock() - entries[-1].ts > self.idle_s:
            return None
        return await written.resume_written(session_, self._live, registration, newest)

    def _context(
        self, registration: Registration, route: RouteRow, inbound: whatsapp.Inbound, earlier: str | None
    ) -> CallContext:
        answering = Route(
            org=route.org, agent=registration.slug, channel=inbound.channel, number=route.number, env=route.env
        )
        return CallContext(
            call=new_call_id(),
            channel=inbound.channel,
            direction=Direction.inbound,
            caller=inbound.caller,
            route=answering,
            today=today_in(self._live.settings.timezone),
            contact=Contact(phone=inbound.caller, name=inbound.name),
            holder=registration.scope.holder or None,
            continues=earlier,
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
                    heard = await asyncio.wait_for(thread.heard.get(), timeout=self.idle_s)
                except TimeoutError:
                    await session.end(running, "timeout", "platform")
                    return
                if heard is None:
                    await running.close()
                    return
                if isinstance(heard, Stop):
                    await take_off(self._live, Scope(key.org, key.env), thread.inbound, thread.reaches, heard)
                    await session.end(running, "caller_hung_up" if heard.by == "caller" else "agent_hung_up", heard.by)
                    return
                # One message that cannot be answered is said with its call: the contact's next one is.
                with survive("answering a WhatsApp message", call):
                    if await take_up(self._live, thread, heard) is not None:
                        return
        finally:
            self._open.pop(key, None)
            self._live.owners.hold_thread(key, here=False)
            self._live.calls.close_call(call)
            self._live.logs.forget(call)


# The contact sees their message read as it is taken up, and "typing…" while the model writes; with
# a person on the line the model is not asked, so the message is read and nothing is promised.
async def take_up(live: LiveParts, thread: OpenThread, heard: whatsapp.Inbound) -> QuotaExceeded | None:
    """One message of an open conversation read and answered; the refusal when the org's quota ran out."""
    running = thread.session
    text = heard.text or await thread.reaches.hear_note(heard)
    try:
        await thread.reaches.mark_read(heard, typing=bool(text) and running.line.agent_may_speak)
    except (UpstreamError, httpx.HTTPError):
        logger.warning("%s: a message to %s was not marked read", heard.channel.value, heard.number, exc_info=True)
    return None if not text else await written.hear(live, running, text)


def _thread_key(scope: Scope, inbound: whatsapp.Inbound | whatsapp.Receipt) -> ThreadKey:
    return ThreadKey(scope.org, scope.env, inbound.number, inbound.wa_id, inbound.channel)


def _hand_receipt(receipt: whatsapp.Receipt) -> HandedMessage:
    return HandedMessage(
        number=receipt.number,
        phone_number_id=receipt.phone_number_id,
        wa_id=receipt.wa_id,
        name=None,
        message_id=receipt.message_id,
        kind="status",
        text=None,
        status=receipt.status,
        error=receipt.error,
        channel=receipt.channel,
    )


# Vouched for by the gateway that took it off the webhook: handed on, it names no signer.
def _receipt_of(handed: HandedMessage, status: str) -> whatsapp.Receipt:
    return whatsapp.Receipt(
        number=handed.number,
        phone_number_id=handed.phone_number_id,
        wa_id=handed.wa_id,
        message_id=handed.message_id,
        status=status,
        error=handed.error,
        channel=handed.channel,
    )


def _hand(inbound: whatsapp.Inbound) -> HandedMessage:
    return HandedMessage(
        number=inbound.number,
        phone_number_id=inbound.phone_number_id,
        wa_id=inbound.wa_id,
        name=inbound.name,
        message_id=inbound.message_id,
        kind=inbound.kind,
        text=inbound.text,
        media_id=inbound.media_id,
        channel=inbound.channel,
    )


# Text, the words of a button or a list row, and a voice note are read; an image, a sticker, a
# location carry nothing the model is given.
async def _find_route(session_: AsyncSession, inbound: whatsapp.Inbound) -> RouteRow | None:
    if not inbound.text and inbound.media_id is None:
        logger.warning(
            "whatsapp: a %s to %s was dropped: only words and voice notes are read",
            inbound.kind or "message",
            inbound.number,
        )
        return None
    route = await telephony.find_route_at(session_, inbound.channel, inbound.number)
    if route is None:
        logger.warning(
            "%s: nobody answers %s: `pinecall numbers import %s --channel %s` routes it",
            inbound.channel.value,
            inbound.number,
            inbound.number,
            inbound.channel.value,
        )
    return route
