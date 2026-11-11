"""Mail's dependencies: the key that opens an org's mailbox, and the gateway's outbox."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.mail.service.outbox import Outbox

TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]


def outbox_of(connection: HTTPConnection) -> Outbox:
    """The outbox the lifespan built."""
    outbox: Outbox = connection.state.outbox
    return outbox


TheOutbox = Annotated[Outbox, Depends(outbox_of)]
