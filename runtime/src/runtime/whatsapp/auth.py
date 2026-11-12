"""WhatsApp's dependencies: the box's Meta app, the messages of a body it signed, and the conversations they go to."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from runtime.exceptions import Forbidden
from runtime.handles import TheSessions, TheVault
from runtime.kit.http import read_capped_body
from runtime.whatsapp import service


# Read in a transaction of its own, over before a message is read: each claim of a message is a
# transaction too, and a request that held one connection while it waited for another is how a pool
# runs dry under load.
async def the_meta_app(sessions: TheSessions, vault: TheVault) -> service.MetaApp:
    """The box's Meta app; 503 on a box that has none."""
    async with sessions.begin() as session:
        return await service.box_meta_app(session, vault)


TheMetaApp = Annotated[service.MetaApp, Depends(the_meta_app)]


# The signature is checked on the bytes as they came, and nothing is parsed before it holds.
async def read_signed_messages(request: Request, app: TheMetaApp) -> list[service.Inbound]:
    """The messages of a body Meta signed with the box's app; 403 for a body it did not sign."""
    body = await read_capped_body(request, service.LONGEST_WEBHOOK, "a webhook's body")
    if not service.is_signed(app.app_secret, body, request.headers.get(service.SIGNATURE_HEADER)):
        raise Forbidden("the body carries no signature of this box's Meta app")
    return service.messages_in(body)


SignedMessages = Annotated[list[service.Inbound], Depends(read_signed_messages)]


def threads_of(connection: HTTPConnection) -> service.Threads:
    """The contacts' conversations, as the lifespan handed them in."""
    threads: service.Threads = connection.state.threads
    return threads


TheThreads = Annotated[service.Threads, Depends(threads_of)]
