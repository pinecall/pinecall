"""The supervisor's desk: listening in, taking a seat, and the verbs sent to a live call."""

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys, tokens
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.schemas import SeatResponse, VerbResponse
from pinecall_runtime.calls.service.peers import SUPERVISOR_VERB, send_command
from pinecall_runtime.calls.service.serving import NO_SUCH_CALL, Serving
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import ReadKind
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.wire.base import Command
from pinecall_runtime.wire.commands import SupervisorVerb, Verb
from pinecall_runtime.wire.parts import Supervisor

IS_OVER = "call {call} is over: read its log or its recording instead"


# A seat hears the call live: it is recorded as a read of the call, once it is handed out.
async def take_seat(
    session: AsyncSession, serving: Serving, actor: Actor, call: str, scope: tokens.RoomScope, what: ReadKind
) -> SeatResponse:
    """A seat in the live call for the person behind the key: hidden to listen, heard to supervise."""
    kept = await HeadRepository(session).head_of_call(call)
    if kept is None or kept.scope is None or kept.scope.org != actor.org:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    keys.check_agent(actor, kept.agent)
    if await serving.logs.store.is_sealed(call):
        raise Conflict(IS_OVER.format(call=call))
    seat = tokens.seat_token(serving.signer, call, scope, actor)
    await compliance.record_read(session, kept.scope, call, what, by=asked_by(actor))
    return SeatResponse(
        server_url=serving.handles.settings.browser_livekit_url(kept.scope.env),
        participant_token=seat.token,
        call=call,
        identity=seat.identity,
        org=actor.org,
        subject=seat.subject,
        name=seat.name,
    )


# The body never says who sent it: the credential does.
async def send_verb(serving: Serving, call: str, verb: Verb, by: Supervisor) -> VerbResponse:
    """One supervise verb on a live call; the call's log says what it did."""
    state = await serving.logs.reading(call).snapshot()
    if state.seq == 0:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    if await serving.logs.store.is_sealed(call):
        raise Conflict(IS_OVER.format(call=call))
    wanted = SupervisorVerb(by=by, verb=verb)
    served = serving.live.calls.get(call)
    if served is not None and served.running is not None:
        await served.running.supervise(wanted)
        return VerbResponse(call=call, verb=verb.verb, seq=None)
    # Whichever gateway runs the call's worker stream or its session takes it.
    sent = Command(type=SUPERVISOR_VERB, agent=state.agent, call=call, data=wanted.dump())
    if not await send_command(serving.handles.signal, sent):
        raise NotFound(NO_SUCH_CALL.format(call=call))
    return VerbResponse(call=call, verb=verb.verb, seq=None)


# The one record of who asked, which is what audits a dial and an erasure.
def asked_by(actor: Actor) -> str:
    """The person behind the key, or the key itself for a server's."""
    return actor.person.id if actor.person is not None else actor.key_id


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
