"""A developer's endpoints on the line: whose terminal a ring lands in, and the phone that reaches their copy."""

from fastapi import APIRouter

from runtime.agents.auth import KnownAgent
from runtime.live import schemas
from runtime.live.auth import AppKey, CallsKey, TheLive
from runtime.live.service import line
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/agents/{slug}/line")
async def get_line(slug: KnownAgent, actor: CallsKey, live: TheLive, session: Session) -> schemas.RingTarget:
    """Who holds the agent's line, and who else could take it."""
    return schemas.RingTarget.of(await line.line_of(session, live.holders, actor.scope, slug))


@router.post("/v1/agents/{slug}/line")
async def take_line(slug: KnownAgent, actor: AppKey, live: TheLive, session: Session) -> schemas.RingTarget:
    """Take the agent's line for this scope."""
    return schemas.RingTarget.of(await line.take_line(session, live.holders, actor.scope, slug))


@router.delete("/v1/agents/{slug}/line")
async def drop_line(slug: KnownAgent, actor: AppKey, live: TheLive, session: Session) -> schemas.RingTarget:
    """Let the line go, to the newest other scope that could take it."""
    return schemas.RingTarget.of(await line.drop_line(session, live.holders, actor.scope, slug))


@router.put("/v1/line/from")
async def put_developer_phone(
    body: schemas.DeveloperPhone, actor: AppKey, live: TheLive, session: Session
) -> schemas.TestNumbers:
    """This phone is the person's own: a call from it reaches their copy of the agent named, or of the one held."""
    return schemas.TestNumbers.of(await line.put_phone(session, live.holders, actor, body.number, body.agent))


@router.delete("/v1/line/from")
async def drop_developer_phones(actor: AppKey, live: TheLive, session: Session) -> schemas.ForgottenPhones:
    """Stop sending this person's phones to their scope, and say which were forgotten."""
    return schemas.ForgottenPhones(forgot=await line.forget_phones(session, live.holders, actor))


@router.get("/v1/line/numbers")
async def list_test_numbers(actor: AppKey, session: Session) -> schemas.TestNumbers:
    """The phone that is the person's, the box's test line, and the production numbers it can dial."""
    return schemas.TestNumbers.of(await line.list_test_numbers(session, actor))
