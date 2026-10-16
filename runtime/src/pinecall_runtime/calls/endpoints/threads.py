"""An agent's WhatsApp inbox by contact: the threads, one thread, read, written to."""

import time
from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.agents.auth import KnownAgent
from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import CallsKey, TalkKey, TheServing
from pinecall_runtime.calls.facts import facts_of
from pinecall_runtime.calls.service import Inbox, lists
from pinecall_runtime.channels import service as channels
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.commands import SayVerb, SupervisorVerb
from pinecall_runtime.wire.parts import Supervisor

router = APIRouter()

NO_THREAD = "no thread with {contact} on agent {agent} in this scope"
ONLY_WHATSAPP = "a message is written on a WhatsApp thread, and {contact}'s newest call is {channel}"
WINDOW_CLOSED = (
    "WhatsApp's window with {contact} closed 24 h after their last message: only a template reaches them now"
)
NOTHING_OPEN = "{contact}'s conversation went quiet and is sealed: their next message opens a new one"


@router.get("/v1/agents/{slug}/threads")
async def list_threads(
    slug: KnownAgent, actor: CallsKey, session: Session, page: Annotated[schemas.ThreadQuery, Query()]
) -> schemas.ThreadList:
    """The agent's contacts, the one that moved last first, with what this reader has not read."""
    found = await lists.inbox_page(
        session, Inbox(actor.scope, slug, _reader_of(actor)), after=page.after, limit=page.limit
    )
    rows = [
        lists.thread_row(row.contact, row.name, facts_of(row.newest), row.moved_at, row.unread, row.calls)
        for row in found.rows
    ]
    return schemas.ThreadList(threads=rows, next=found.next)


@router.get("/v1/agents/{slug}/threads/{contact}")
async def get_thread(
    slug: KnownAgent, contact: str, actor: CallsKey, serving: TheServing, session: Session
) -> schemas.ThreadResponse:
    """A contact's calls with the agent merged into one thread, oldest first."""
    calls = await _thread_of(session, actor.scope, slug, contact)
    facts = await lists.facts_of_calls(session, calls)
    messages: list[schemas.ThreadMessage] = []
    for call in reversed(calls):
        if call in facts:
            messages += lists.thread_messages(facts[call], await serving.logs.store.whole(call))
    name = next((facts[call].name for call in calls if call in facts and facts[call].name), None)
    return schemas.ThreadResponse(contact=contact, name=name, messages=messages)


# The read cursor is the person's; a server's key keeps its own.
@router.post("/v1/agents/{slug}/threads/{contact}/read", status_code=204)
async def mark_thread_read(slug: KnownAgent, contact: str, actor: CallsKey, session: Session) -> None:
    """This reader has read the thread up to now."""
    await _thread_of(session, actor.scope, slug, contact)
    await lists.mark_thread_read(session, Inbox(actor.scope, slug, _reader_of(actor)), contact, time.time())


# A supervisor's `say` on the open conversation, sent to the contact by its reply tap. Meta lets
# a business write freely only within 24 h of the contact's last message.
@router.post("/v1/agents/{slug}/threads/{contact}/messages", status_code=202)
async def send_thread_message(
    slug: KnownAgent,
    contact: str,
    body: schemas.ThreadMessageRequest,
    actor: TalkKey,
    serving: TheServing,
    session: Session,
) -> schemas.ThreadMessageResponse:
    """Say something as the agent on the contact's open WhatsApp conversation."""
    newest = (await _thread_of(session, actor.scope, slug, contact))[0]
    facts = (await lists.facts_of_calls(session, [newest])).get(newest)
    channel = None if facts is None else facts.channel
    if facts is None or channel != "whatsapp":
        raise Conflict(ONLY_WHATSAPP.format(contact=contact, channel=channel))
    # The log's own clock, which stamped when the contact last wrote.
    if serving.logs.store.clock() - max(facts.heard_at, default=0.0) > channels.WINDOW_S:
        raise Conflict(WINDOW_CLOSED.format(contact=contact))
    served = serving.live.calls.get(newest)
    if served is None or served.running is None:
        raise Conflict(NOTHING_OPEN.format(contact=contact))
    by = Supervisor(id=_reader_of(actor), name=None if actor.person is None else actor.person.name)
    await served.running.supervise(SupervisorVerb(by=by, verb=SayVerb(text=body.text)))
    return schemas.ThreadMessageResponse(contact=contact, call=newest)


async def _thread_of(session: Session, scope: Scope, slug: str, contact: str) -> list[str]:
    calls = await lists.thread_of(session, scope, slug, contact)
    if not calls:
        raise NotFound(NO_THREAD.format(contact=contact, agent=slug))
    return calls


def _reader_of(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id
