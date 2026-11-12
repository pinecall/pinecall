"""The supervisor's desk: a seat in a live call, to listen or to speak, and the verbs sent to it."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.calls import service as calls
from runtime.compliance import service as compliance
from runtime.enums import ReadKind
from runtime.exceptions import Conflict, NotFound
from runtime.live.parts import LiveParts
from runtime.live.service import commands, tokens
from runtime.wire.commands import SupervisorVerb, Verb
from runtime.wire.parts import Supervisor
from runtime.wire.room import RoomScope


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
