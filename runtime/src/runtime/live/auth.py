"""The live side's dependencies: its keys, the call each client may reach, and what the lifespan built."""

from typing import Annotated

from fastapi import Depends, Query, Request
from livekit.protocol.webhook import WebhookEvent
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.auth import Authenticator, check_scopes, no_actor
from runtime.calls.auth import reading
from runtime.calls.service.reading import Reader, get_readable
from runtime.enums import Env, KeyScope
from runtime.exceptions import Forbidden, Unauthorized
from runtime.handles import TheSettings
from runtime.kit.http import read_capped_body
from runtime.live import schemas
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from runtime.live.service import desk, openings
from runtime.live.service.codes import Codes
from runtime.live.service.commands import Restaging
from runtime.live.service.entries import Appends
from runtime.live.service.tokens import Signer, Visit
from runtime.live.service.whatsapp import Threads
from runtime.live.service.written import Simulations
from runtime.livekit import verify_event
from runtime.postgres import Session

# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
# An app holds its agents, answers their tools and sends their calls' commands with its key.
AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]
# Whoever may talk to an agent mints a visitor's token, issues a code, places a call.
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
SuperviseKey = Annotated[Actor, Depends(Authenticator(KeyScope.supervise))]
# An app passes a call it serves to a teammate, whose stages the call takes; the settings are the pipeline key's.
StagesKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline, KeyScope.app))]
# The console's dev verbs, each on the scope of what it reaches.
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
KnowledgeKey = Annotated[Actor, Depends(Authenticator(KeyScope.knowledge))]
MemoryKey = Annotated[Actor, Depends(Authenticator(KeyScope.memory))]
EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]

# The most a room event of LiveKit's weighs.
LARGEST_WEBHOOK = 4 * 1024 * 1024


# ── what the lifespan built ──


def live_of(connection: HTTPConnection) -> LiveParts:
    """What serves a call on this gateway, one of each."""
    live: LiveParts = connection.state.live
    return live


def appends_of(connection: HTTPConnection) -> Appends:
    """What this gateway counted of the appends since it started."""
    appends: Appends = connection.state.appends
    return appends


def whatsapp_threads_of(connection: HTTPConnection) -> Threads:
    """The WhatsApp threads this gateway keeps open, as the live side's own endpoints reach them."""
    threads: Threads = connection.state.whatsapp_threads
    return threads


def signer_of(connection: HTTPConnection) -> Signer:
    """What signs the tokens of a call: LiveKit's pair for a room's, the gateway's own key for every other."""
    signer: Signer = connection.state.signer
    return signer


def codes_of(connection: HTTPConnection) -> Codes:
    """Every agent's live caller codes."""
    codes: Codes = connection.state.codes
    return codes


# Evals', handed in (`written.Simulations`): a chat that names a persona is admitted as a simulation.
def simulations_of(connection: HTTPConnection) -> Simulations:
    """What admits a simulated caller before its call opens."""
    simulations: Simulations = connection.state.simulations
    return simulations


TheLive = Annotated[LiveParts, Depends(live_of)]
TheAppends = Annotated[Appends, Depends(appends_of)]
TheWhatsappThreads = Annotated[Threads, Depends(whatsapp_threads_of)]
TheSigner = Annotated[Signer, Depends(signer_of)]
TheCodes = Annotated[Codes, Depends(codes_of)]
TheSimulations = Annotated[Simulations, Depends(simulations_of)]


# ── a socket's key ──


# A socket is no request, so no `Authenticator` answers it: the same two refusals, raised for the
# endpoint to close the socket with (`kit.websockets.refuse_socket`). Until 2026-11 each of three
# socket endpoints read the actor off the socket's state and checked its scopes itself.
def get_socket_actor(websocket: HTTPConnection, *scopes: KeyScope) -> Actor:
    """The actor of a socket, holding one of the scopes; refused as a request would be."""
    actor: Actor | None = getattr(websocket.state, "actor", None)
    if actor is None:
        raise no_actor(websocket)
    check_scopes(actor, scopes)
    return actor


# ── the call a worker reaches ──


# The call as this gateway serves it, for the worker that opened it: one dependency, so an
# endpoint of the worker's is the service call and nothing else.
async def load_served_call(call: str, actor: WorkerKey, live: TheLive, session: Session) -> Served:
    """The call named in the path, served here, as its opener's key may reach it."""
    return await openings.get_served(session, live, actor, call)


# The lookup is any key's of the call's org and env, the fleet's included: an app searches its
# knowledge on a call it serves whoever opened it.
async def load_served_call_of_anyone(call: str, actor: WorkerKey, live: TheLive, session: Session) -> Served:
    """The call named in the path, served here, for a key of its org and env."""
    return await openings.get_served(session, live, actor, call, openers=False)


TheServedCall = Annotated[Served, Depends(load_served_call)]
AnyonesServedCall = Annotated[Served, Depends(load_served_call_of_anyone)]


# ── the call a supervisor steers, a caller hangs up, an app restages ──


# One dependency holds the three rules of a verb: until 2026-11 they stood in the endpoint's body, behind
# a reader that also asked for the `calls` scope, so a key that opened `supervise` alone took a seat
# and could send no verb from it. A verb is a supervisor's: the key that opens `supervise`, or the
# token of a supervise seat, on a call it may read.
async def load_supervised_call(
    call: str, session: Session, reader: Annotated[Reader, Depends(reading(KeyScope.supervise))]
) -> desk.Supervising:
    """The path's call as whoever asks may steer it, and who its verbs are sent as."""
    visit = _visit_of(reader)
    if visit is not None and visit.scope != "supervise":
        raise Forbidden("this token reads the call and sends no verb: steering it takes a supervise token")
    await get_readable(session, reader, call)
    return desk.Supervising(call, desk.supervisor_of(reader.actor, visit))


# With the call's own token alone: a key ends a call with the verb `end`.
async def load_callers_call(
    call: str, session: Session, reader: Annotated[Reader, Depends(reading(KeyScope.calls, KeyScope.fleet))]
) -> str:
    """The path's call, for the caller's own hang-up, said with its token."""
    if reader.visit is None:
        raise Forbidden(
            "a hang-up is the caller's own, said with the call's token: a key ends a call with the verb end"
        )
    await get_readable(session, reader, call)
    return call


# Asked by whoever changed the settings and is on the call, for that call alone, on the scope that
# writes the vendors; with `agent`, by the app that passed the call to a teammate it holds too. A key
# that serves apps passes a call to a teammate; taking the settings anew is the pipeline key's.
async def load_restaged_call(
    call: str, actor: StagesKey, session: Session, body: schemas.RestageRequest | None = None
) -> Restaging:
    """The path's call as this key may have it take its stages anew, and the teammate whose stages it takes."""
    passed_to = None if body is None else body.agent
    if passed_to is None:
        check_scopes(actor, (KeyScope.pipeline,))
    await get_readable(session, Reader(actor=actor), call)
    return Restaging(call, actor.scope, passed_to)


def read_code_visit(reader: Annotated[Reader, Depends(reading(KeyScope.calls))]) -> Visit | None:
    """The token a page asks after its code with; None for a key, which reads no code."""
    return _visit_of(reader)


TheSupervisedCall = Annotated[desk.Supervising, Depends(load_supervised_call)]
TheCallersCall = Annotated[str, Depends(load_callers_call)]
TheRestagedCall = Annotated[Restaging, Depends(load_restaged_call)]
TheCodeVisit = Annotated[Visit | None, Depends(read_code_visit)]


# What reads a token here is what signed it (`Signer.read`), so a reader's visit is a visit of ours.
def _visit_of(reader: Reader) -> Visit | None:
    return reader.visit if isinstance(reader.visit, Visit) else None


# ── LiveKit's own word ──


# livekit sends its token bare in Authorization, and every room event of the box. Each env's LiveKit
# names its env in the URL its config sends to, so the room is asked of the LiveKit it lives on:
# `?world=` names it, as the chart and the operator's page spell it.
async def read_room_event(request: Request, settings: TheSettings) -> WebhookEvent:
    """The room event of a body LiveKit signed with the box's key; 401 for any other."""
    token = request.headers.get("Authorization")
    if not token:
        raise Unauthorized("the event carries no Authorization: LiveKit signs every event it sends")
    body = (await read_capped_body(request, LARGEST_WEBHOOK, "a webhook's body")).decode()
    return verify_event(settings, body, token)


SignedRoomEvent = Annotated[WebhookEvent, Depends(read_room_event)]
EventsEnv = Annotated[Env, Query(alias="world")]
