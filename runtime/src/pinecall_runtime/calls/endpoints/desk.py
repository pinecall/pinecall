"""The supervisor's desk: listening in, taking a seat, the verbs sent to a live call, and its stages taken anew."""

from fastapi import APIRouter

from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import (
    CallReaderDep,
    Reader,
    StagesKey,
    SuperviseKey,
    TheServing,
    check_readable,
)
from pinecall_runtime.calls.service import desk
from pinecall_runtime.enums import KeyScope, ReadKind
from pinecall_runtime.exceptions import Forbidden
from pinecall_runtime.kit.auth import check_scopes
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.commands import Verb

router = APIRouter()

READS_ONLY = "this token reads the call and sends no verb: steering it takes a supervise token"


@router.post("/v1/calls/{call}/listen")
async def listen(call: str, actor: SuperviseKey, serving: TheServing, session: Session) -> schemas.SeatResponse:
    """A hidden seat that hears one live call."""
    return await desk.take_seat(session, serving, actor, call, "observe", ReadKind.listen)


# Not hidden: livekit delivers no track of a hidden seat, and a takeover would be silent.
@router.post("/v1/calls/{call}/supervise")
async def supervise(call: str, actor: SuperviseKey, serving: TheServing, session: Session) -> schemas.SeatResponse:
    """A seat that speaks in one live call; its token also sends the verbs."""
    return await desk.take_seat(session, serving, actor, call, "supervise", ReadKind.supervise)


# The body never says who sent it: the credential does.
@router.post("/v1/calls/{call}/verbs", status_code=202)
async def queue_verb(
    call: str, verb: Verb, reader: CallReaderDep, serving: TheServing, session: Session
) -> schemas.VerbResponse:
    """One supervise verb on a live call; the call's log says what it did."""
    if reader.visit is not None and reader.visit.scope != "supervise":
        raise Forbidden(READS_ONLY)
    if reader.actor is not None:
        check_scopes(reader.actor, (KeyScope.supervise,))
    await check_readable(session, serving, reader, call)
    return await desk.send_verb(serving, call, verb, desk.supervisor_of(reader.actor, reader.visit))


# Asked by whoever changed the settings and is on the call, for that call alone, on the scope that
# writes the vendors: a call nobody asks for keeps the model and the voice it opened on until it ends.
# With `agent`, asked by the app that passed the call to a teammate it holds too.
@router.post("/v1/calls/{call}/stages", status_code=202)
async def restage(
    call: str, actor: StagesKey, serving: TheServing, session: Session, body: schemas.RestageRequest | None = None
) -> schemas.RestageResponse:
    """The live call takes the model and the voice its agent's settings name now, or those of the agent it names."""
    passed_to = None if body is None else body.agent
    # A key that serves apps passes a call to a teammate; taking the settings anew is the pipeline key's.
    if passed_to is None:
        check_scopes(actor, (KeyScope.pipeline,))
    await check_readable(session, serving, Reader(actor=actor), call)
    await desk.restage(serving, actor, call, passed_to)
    return schemas.RestageResponse(call=call)
