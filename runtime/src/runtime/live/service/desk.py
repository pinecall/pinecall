"""The supervisor's desk: a seat in a live call, to listen or to speak, and the verbs sent to it."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.calls import service as calls
from runtime.compliance import service as compliance
from runtime.enums import Channel, ReadKind
from runtime.exceptions import Conflict, NotFound
from runtime.live.parts import LiveParts
from runtime.live.service import commands, tokens
from runtime.wire.commands import SayVerb, SupervisorVerb, Verb
from runtime.wire.parts import Supervisor
from runtime.wire.room import RoomScope

# Meta lets a business write freely only this long after the contact's last message
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages).
WHATSAPP_WINDOW_S = 24 * 60 * 60
# The channels a contact writes on message by message, as a call's facts name them.
THREAD_CHANNELS = frozenset(channel.value for channel in Channel if channel.is_a_thread)


@dataclass(frozen=True, slots=True)
class Seated:
    """A person seated in a live call: where its room is, the token that opens it, and who it says they are."""

    server_url: str
    participant_token: str
    call: str
    identity: str
    org: str
    subject: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class Supervising:
    """A call somebody may steer, and who its verbs are sent as."""

    call: str
    by: Supervisor


# A seat hears the call live: it is recorded as a read of the call, once it is handed out.
async def take_seat(
    session: AsyncSession,
    live: LiveParts,
    signer: tokens.Signer,
    actor: Actor,
    call: str,
    scope: RoomScope,
    what: ReadKind,
) -> Seated:
    """A seat in the live call for the person behind the key: hidden to listen, heard to supervise."""
    kept = await calls.find_head(session, call)
    if kept is None or kept.scope is None or kept.scope.org != actor.org:
        raise NotFound(f"no call {call} in this key's org and env")
    accounts.check_agent(actor, kept.agent)
    if await live.store.is_sealed(call):
        raise Conflict(f"call {call} is over: read its log or its recording instead")
    seat = tokens.sign_seat(signer, call, scope, actor)
    await compliance.record_read(session, kept.scope, call, what, by=actor.asked_by)
    return Seated(
        server_url=live.settings.browser_livekit_url(kept.scope.env),
        participant_token=seat.token,
        call=call,
        identity=seat.identity,
        org=actor.org,
        subject=seat.subject,
        name=seat.name,
    )


# The body never says who sent it: the credential does. Whichever gateway runs the call's worker
# stream or its session takes the verb (`commands.deliver`), and a call that refuses it says so on its
# log and to whoever sent it, whichever gateway the request landed on.
async def send_verb(live: LiveParts, supervising: Supervising, verb: Verb) -> None:
    """One supervise verb on a live call; the call's log says what it did."""
    wanted = SupervisorVerb(by=supervising.by, verb=verb)
    await commands.send_to_live_call(live, supervising.call, commands.SUPERVISOR_VERB, wanted.dump())


def supervisor_of(actor: Actor | None, visit: tokens.Visit | None) -> Supervisor:
    """Who a verb is sent as: the token's subject, the key's person, or the key's org."""
    if visit is not None:
        if visit.subject is not None:
            return Supervisor(id=visit.subject, name=visit.name)
        return Supervisor(id=visit.identity or "")
    if actor is None:
        return Supervisor(id="")
    if actor.person is not None:
        return Supervisor(id=actor.person.id, name=actor.person.name)
    return Supervisor(id=f"key:{actor.org}")


# A written message goes out on the contact's newest conversation on a channel they write on. It goes
# the way every verb of the desk goes: to whichever gateway runs the conversation. Until 2026-11 the
# contact's newest call of any kind was asked, and a phone call after a thread left the thread
# unanswerable.
async def say_as_agent(
    session_: AsyncSession, live: LiveParts, actor: Actor, slug: str, contact: str, text: str
) -> str:
    """Say something as the agent on the contact's open WhatsApp or SMS conversation; the call it was said on."""
    with_them = await calls.list_calls_with(session_, actor.scope, slug, contact)
    facts = await calls.facts_of_calls(session_, with_them)
    newest = next((call for call in with_them if call in facts and facts[call].channel in THREAD_CHANNELS), None)
    if newest is None:
        raise Conflict(f"a message is written on a WhatsApp or an SMS thread, and {contact} has none with {slug}")
    # The log's own clock, which stamped when the contact last wrote. The window is WhatsApp's alone.
    quiet_for = live.store.clock() - max(facts[newest].heard_at, default=0.0)
    if facts[newest].channel == Channel.whatsapp and quiet_for > WHATSAPP_WINDOW_S:
        raise Conflict(
            f"WhatsApp's window with {contact} closed 24 h after their last message: only a template reaches them now"
        )
    if await live.store.is_sealed(newest):
        raise Conflict(f"{contact}'s conversation went quiet and is sealed: their next message opens a new one")
    by = Supervisor(id=actor.asked_by, name=None if actor.person is None else actor.person.name)
    await send_verb(live, Supervising(newest, by), SayVerb(text=text))
    return newest
