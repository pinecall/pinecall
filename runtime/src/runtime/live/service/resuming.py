"""Which call a written conversation goes on: the one it takes up, or the one a new call of it carries on."""

from dataclasses import dataclass
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.calls import service as calls
from runtime.whatsapp import service as whatsapp
from runtime.wire.base import Entry

# What an email call's metadata names its thread by.
EMAIL_THREAD = "email_thread"
# However the call ends, the conversation is over with it: a written call a supervisor ends only says
# so, and its thread closes its session.
OVER = {"call.ended", "supervisor.ended"}
# How many of a contact's email calls are read to find the one of a thread: one person rarely writes on more at once.
LOOKED_AT = 10


@dataclass(frozen=True, slots=True)
class Earlier:
    """The call the message is heard on, when one has idle time left; else the one a new call carries on."""

    going: str | None
    carried: str | None


# WhatsApp and SMS are one conversation a contact: the newest call on the channel is it. One contact
# writes on several email threads at once, and each is its own: the call of this thread is found
# among the contact's newest email calls by the thread its `call.started` names. A new call carries
# on the thread's own call when it has one (an email answered after the thread went quiet), else the
# contact's newest call that is over, on any channel: until 2026-11-19 it was the newest whatever
# its state, and an email thread opened beside another took that one's turns as its own past.
async def find_earlier(
    session_: AsyncSession, scope: Scope, agent: str, inbound: whatsapp.Inbound, *, now: float, idle_s: float
) -> Earlier:
    """The call a contact's message goes on, or the one a new call of theirs carries on."""
    contact = inbound.caller
    if inbound.channel.is_by_email:
        listed = await calls.list_newest_calls_with(session_, scope, agent, contact, inbound.channel, limit=LOOKED_AT)
        for call in listed:
            entries = await calls.list_entries(session_, call)
            if entries and thread_of(entries[0]) == inbound.thread:
                return Earlier(call if _is_going(entries, now, idle_s) else None, call)
    else:
        newest = await calls.find_newest_call_with(session_, scope, agent, contact, inbound.channel)
        entries = [] if newest is None else await calls.list_entries(session_, newest)
        if newest is not None and _is_going(entries, now, idle_s):
            return Earlier(newest, None)
    return Earlier(None, await calls.find_newest_call_with(session_, scope, agent, contact, ended=True))


def thread_of(started: Entry) -> object:
    """The email thread a call was opened on, as its `call.started` says it."""
    opened = started.data.get("metadata") if started.type == "call.started" else None
    return cast("dict[str, object]", opened).get(EMAIL_THREAD) if isinstance(opened, dict) else None


def _is_going(entries: list[Entry], now: float, idle_s: float) -> bool:
    return bool(entries) and not any(entry.type in OVER for entry in entries) and now - entries[-1].ts <= idle_s
