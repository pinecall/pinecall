"""The supervisor's desk: a seat to listen or to speak, a verb, a message on a WhatsApp thread, the stages anew."""

from fastapi import APIRouter

from runtime.agents.auth import KnownAgent
from runtime.enums import ReadKind
from runtime.live import schemas
from runtime.live.auth import SuperviseKey, TalkKey, TheLive, TheRestagedCall, TheSigner, TheSupervisedCall
from runtime.live.service import commands, desk, whatsapp
from runtime.postgres import Session
from runtime.wire.commands import Verb

router = APIRouter()


@router.post("/v1/calls/{call}/listen")
async def listen(
    call: str, actor: SuperviseKey, live: TheLive, signer: TheSigner, session: Session
) -> schemas.SeatResponse:
    """A hidden seat that hears one live call."""
    seat = await desk.take_seat(session, live, signer, actor, call, "observe", ReadKind.listen)
    return schemas.SeatResponse.of(seat)


# Not hidden: livekit delivers no track of a hidden seat, and a takeover would be silent.
@router.post("/v1/calls/{call}/supervise")
async def supervise(
    call: str, actor: SuperviseKey, live: TheLive, signer: TheSigner, session: Session
) -> schemas.SeatResponse:
    """A seat that speaks in one live call; its token also sends the verbs."""
    seat = await desk.take_seat(session, live, signer, actor, call, "supervise", ReadKind.supervise)
    return schemas.SeatResponse.of(seat)


# The body never says who sent it: the credential does.
@router.post("/v1/calls/{call}/verbs", status_code=202)
async def send_verb(verb: Verb, supervised: TheSupervisedCall, live: TheLive) -> schemas.VerbResponse:
    """One supervise verb on a live call; the call's log says what it did."""
    await desk.send_verb(live, supervised, verb)
    return schemas.VerbResponse(call=supervised.call, verb=verb.verb, seq=None)


# A supervisor's `say` on the open conversation, sent to the contact by its reply tap. Meta lets
# a business write freely only within 24 h of the contact's last message.
@router.post("/v1/agents/{slug}/threads/{contact}/messages", status_code=202)
async def send_thread_message(
    slug: KnownAgent, contact: str, body: schemas.ThreadMessageRequest, actor: TalkKey, live: TheLive, session: Session
) -> schemas.ThreadMessageResponse:
    """Say something as the agent on the contact's open WhatsApp conversation."""
    call = await whatsapp.say_as_agent(session, live, actor, slug, contact, body.text)
    return schemas.ThreadMessageResponse(contact=contact, call=call)


@router.post("/v1/calls/{call}/stages", status_code=202)
async def restage(restaged: TheRestagedCall, live: TheLive) -> schemas.RestageResponse:
    """The live call takes the model and the voice its agent's settings name now, or those of the agent it names."""
    await commands.restage(live, restaged.scope, restaged.call, restaged.passed_to)
    return schemas.RestageResponse(call=restaged.call)
