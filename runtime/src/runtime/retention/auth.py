"""Retention's dependencies: what serves an erasure, and what an erased call is forgotten from."""

from typing import Annotated

from fastapi import Depends

from runtime.live.auth import TheLive
from runtime.retention.service.erasure import Holders


# `LiveParts` never leaves the live side: an agent's erasure is handed who holds each agent by name.
def holders_of(parts: TheLive) -> Holders:
    """The apps holding each agent now."""
    return parts.holders


TheHolders = Annotated[Holders, Depends(holders_of)]
