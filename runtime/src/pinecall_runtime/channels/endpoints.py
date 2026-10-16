"""The channels endpoints: the operator's routes, and Meta's WhatsApp webhook."""

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import schemas
from pinecall_runtime.channels.auth import TheOperator, WorkerKey
from pinecall_runtime.channels.service import routes, whatsapp
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.exceptions import Forbidden, NotFound, PayloadTooLarge, ServiceUnavailable
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.telephony import service as telephony

logger = logging.getLogger(__name__)

router = APIRouter()

# Meta's bodies are a few kilobytes; a webhook is never a file.
LONGEST_WEBHOOK = 1024 * 1024


# ── a worker's ──


# A route the operator adds answers the next job: nothing is cached.
@router.get("/v1/routes")
async def list_routes(
    actor: WorkerKey, session: Session, query: Annotated[schemas.RouteQuery, Query()]
) -> list[schemas.RouteRow]:
    """The routes of a scope; for the fleet's key and a number, the route that number rings."""
    fleet = KeyScope.fleet in actor.scopes
    if fleet and query.number is not None:
        found = await routes.route_at(session, query.channel, query.number)
        return (
            []
            if found is None or found.env != actor.env
            else [schemas.RouteRow.model_validate(found, from_attributes=True)]
        )
    if not fleet or query.org is None or query.env is None:
        return [
            schemas.RouteRow.model_validate(route, from_attributes=True)
            for route in await routes.routes_of_org(session, actor.org, actor.env)
        ]
    # The fleet serves every org of its env: it reads the one its dispatch names.
    named = Scope(query.org, query.env, query.holder or THE_ORGS_OWN)
    with box_wide():
        return [
            schemas.RouteRow.model_validate(route, from_attributes=True)
            for route in await routes.routes_of_org(session, named.org, named.env)
        ]


# ── the operator's routes ──


@router.get("/v1/ops/routes")
async def list_box_routes(
    _actor: TheOperator, session: Session, org: Annotated[str, Query()], env: Annotated[Env, Query()] = Env.production
) -> list[schemas.RouteRow]:
    """Every number the org answers at in the env, oldest first."""
    with box_wide():
        found = await orgs.get_org(session, org)
        return [
            schemas.RouteRow.model_validate(route, from_attributes=True)
            for route in await routes.routes_of_org(session, found.id, env)
        ]


# One row per number per org: a number added again moves. It is admitted on the SFU at once;
# the carrier is never touched, so it rings only where the carrier already points it here.
@router.post("/v1/ops/routes")
async def add_box_route(
    body: schemas.RouteRequest, _actor: TheOperator, handles: TheHandles, session: Session
) -> schemas.RouteRow:
    """A number answered by this org's agent, in this env, on this channel."""
    with box_wide():
        found = await orgs.get_org(session, body.org)
        wanted = telephony.NumberImport(Scope(found.id, body.env), body.agent, body.number, channel=body.channel)
        typed = await telephony.type_route(session, handles, wanted)
    return schemas.RouteRow.model_validate(typed.route, from_attributes=True)


@router.delete("/v1/ops/routes/{number}", status_code=204)
async def drop_box_route(
    number: str, _actor: TheOperator, handles: TheHandles, session: Session, org: Annotated[str, Query()]
) -> None:
    """The org's route at the number forgotten, and its admission; 404 for a number nobody typed."""
    with box_wide():
        found = await orgs.get_org(session, org)
        route = await routes.get_route(session, found.id, number)
        if route is None:
            raise NotFound(f"no route for {number} in org {org}")
        await telephony.release_number(session, handles, found.id, parse_e164(number), route.env)


# ── Meta's webhook ──


@router.get("/v1/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    handles: TheHandles,
    session: Session,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    word: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Meta subscribing: its challenge echoed back when it says this box's word."""
    return whatsapp.handshake(await whatsapp.box_meta_app(session, handles.vault), mode, word, challenge)


# Past the signature the answer is 200: Meta disables a webhook that keeps failing, so what goes
# wrong after it is a line in the log. The one exception is a message another delivery is still
# reading: 503 keeps it on Meta's side until that reading is done or has died.
@router.post("/v1/whatsapp/webhook")
async def receive_webhook(request: Request, handles: TheHandles, session: Session) -> dict[str, int]:
    """Every message of a signed body onto its contact's conversation."""
    app = await whatsapp.box_meta_app(session, handles.vault)
    body = await _webhook_body(request)
    if not whatsapp.is_signed(app.app_secret, body, request.headers.get(whatsapp.SIGNATURE_HEADER)):
        raise Forbidden("the body carries no signature of this box's Meta app")
    messages = whatsapp.messages_in(body)
    threads: calls.Threads = request.app.state.threads
    unread = [inbound for inbound in messages if not await threads.receive(session, inbound)]
    if unread:
        raise ServiceUnavailable(f"{len(unread)} of these messages are being read by another delivery: send it again")
    return {"received": len(messages)}


async def _webhook_body(request: Request) -> bytes:
    read = bytearray()
    async for chunk in request.stream():
        read += chunk
        if len(read) > LONGEST_WEBHOOK:
            raise PayloadTooLarge("a webhook's body is a megabyte at most")
    return bytes(read)
