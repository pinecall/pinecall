"""Studio's dependencies: what holds its agents on this gateway, and what it asks of the live side."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.live.auth import TheLive
from runtime.studio.service.agents import Holders
from runtime.studio.service.holder import Holder


def holder_of(connection: HTTPConnection) -> Holder:
    """What holds every Studio agent of the box on this gateway, as the lifespan built it."""
    holder: Holder = connection.state.studio
    return holder


# `LiveParts` never leaves the live side: Studio's service is handed who holds each agent by name.
def holders_of(parts: TheLive) -> Holders:
    """The apps holding each agent now."""
    return parts.holders


TheHolder = Annotated[Holder, Depends(holder_of)]
TheHolders = Annotated[Holders, Depends(holders_of)]
