"""The talk key's endpoints and a visitor's own: a room token, a code keyed, a dial, a text, the hang-up."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownAgent
from runtime.compliance import service as compliance
from runtime.enums import ConsentKind
from runtime.fleet.auth import TheRoster
from runtime.kit.time import now
from runtime.live import schemas
from runtime.live.auth import TalkKey, TheCallersCall, TheCodes, TheCodeVisit, TheLive, TheSigner, TheWhatsappThreads
from runtime.live.service import commands, dialing, texting, visitors
from runtime.postgres import Session
from runtime.telephony.schemas.dial import Consent, DialRequest, DialResponse, TextRequest, TextResponse

router = APIRouter()


@router.post("/v1/tokens", status_code=201)
async def mint_room_token(
    body: schemas.MintTokenRequest,
    actor: TalkKey,
    live: TheLive,
    signer: TheSigner,
    roster: TheRoster,
    session: Session,
) -> schemas.MintTokenResponse:
    """A room token for one of the key's agents: a new call, or one resumed."""
    wanted = visitors.Mint(**body.model_dump())
    return schemas.MintTokenResponse.of(await visitors.mint_room_token(session, live, signer, roster, actor, wanted))


@router.post("/v1/codes", status_code=201)
async def issue_code(
    body: schemas.IssueCodeRequest, actor: TalkKey, codes: TheCodes, signer: TheSigner, session: Session
) -> schemas.IssueCodeResponse:
    """Four digits for a caller to key, the number to call, and a token that asks after them."""
    issued = await visitors.issue_code(session, codes, signer, actor, body.agent, body.ttl_s, body.log)
    return schemas.IssueCodeResponse.of(issued)


# No session is asked for: a page that waits for its code holds no connection while it does.
@router.get("/v1/codes/{code}")
async def get_code_status(
    code: str, visit: TheCodeVisit, codes: TheCodes, signer: TheSigner, query: Annotated[schemas.CodeQuery, Query()]
) -> schemas.CodeStatus:
    """How the code stands; with ?wait=1, held up to 25 s for a call to key it."""
    return schemas.CodeStatus.of(await visitors.get_code_status(codes, signer, visit, code, wait=query.wait))


# The same key that seats a visitor sends the agent out to a phone.
@router.post("/v1/agents/{slug}/dial", status_code=202)
async def dial_out(
    slug: KnownAgent, body: DialRequest, actor: TalkKey, live: TheLive, signer: TheSigner, session: Session
) -> DialResponse:
    """Place a call as the agent, after its guards: the call it became, before anything rings."""
    dialled = await dialing.dial_as_agent(session, live, signer, actor, slug, _dial_of(body))
    placed = dialled.placed
    answer = {"call": placed.call, "agent": slug, "to": placed.to, "from": placed.shown, "env": actor.env}
    return DialResponse.model_validate({**answer, "log_token": dialled.log_token})


# The agent writes first, where a dial rings first: the same key, the same guards.
@router.post("/v1/agents/{slug}/text", status_code=202)
async def text_out(
    slug: KnownAgent, body: TextRequest, actor: TalkKey, live: TheLive, threads: TheWhatsappThreads, session: Session
) -> TextResponse:
    """Send a contact one SMS or email as the agent, after its guards: the conversation it was said on."""
    asked = texting.Text(
        to=body.to,
        text=body.text,
        shown=body.from_,
        consent=_consent_of(body.consent),
        subject=body.subject,
        metadata=body.metadata,
        instruction=body.instruction,
    )
    texted = await texting.text_as_agent(session, live, threads, actor, slug, asked, now())
    answer = {"call": texted.call, "agent": slug, "to": texted.to, "from": texted.shown, "env": actor.env}
    return TextResponse.model_validate(answer)


# The page says it before it leaves the room, over HTTP, which a closing tab still completes
# (`keepalive`): said on the room's data channel alone, the hang-up is lost with the seat and the
# call waits five minutes for a caller who is not coming back (tokens.md).
@router.post("/v1/calls/{call}/hangup", status_code=202)
async def hang_up(call: TheCallersCall, live: TheLive) -> schemas.HangupResponse:
    """The caller hung up: the call ends now, as `caller_hung_up`; with the call's own token alone."""
    await commands.hang_up_for_caller(live, call)
    return schemas.HangupResponse(call=call)


def _consent_of(given: Consent | None) -> compliance.Consent | None:
    if given is None:
        return None
    return compliance.Consent(ConsentKind(given.kind), given.source, given.text, given.evidence)


def _dial_of(body: DialRequest) -> dialing.Dial:
    return dialing.Dial(
        to=body.to,
        shown=body.from_,
        consent=_consent_of(body.consent),
        state=body.state,
        metadata=body.metadata,
        greeting=body.greeting,
        instruction=body.instruction,
        log=body.log,
    )
