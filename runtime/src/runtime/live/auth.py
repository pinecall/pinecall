"""The live side's dependencies: the worker's key, the call served here it may reach, what the lifespan built."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from runtime.live.service import openings
from runtime.live.service.entries import Appends
from runtime.live.service.whatsapp import Threads
from runtime.postgres import Session

# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
# An app holds its agents, answers their tools and sends their calls' commands with its key.
AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]


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


TheLive = Annotated[LiveParts, Depends(live_of)]
TheAppends = Annotated[Appends, Depends(appends_of)]
TheWhatsappThreads = Annotated[Threads, Depends(whatsapp_threads_of)]


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
