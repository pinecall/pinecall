"""Flows' dependencies: the app a path names, who may read its runs, and the dial of a call step."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.flows.repository import App
from runtime.flows.service import Dial, Holders
from runtime.kit.text import parse_slug
from runtime.live import service as live
from runtime.live.auth import AppKey, TheLive

# An app's runs are read with the key its process serves with, or by who reads the calls.
ReadsRuns = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.calls))]


# ── the app of a path ──


# Until 2026-11 each of the nine routes parsed the path's name itself, and passed it beside the scope.
def the_app(app: str, actor: AppKey) -> App:
    """The path's app as the key that serves it acts: its scope, and its name, a slug."""
    return App(actor.scope, parse_slug(app))


def the_app_read(app: str, actor: ReadsRuns) -> App:
    """The path's app as a key that reads its runs acts: the app's own, or one that reads the calls."""
    return App(actor.scope, parse_slug(app))


TheApp = Annotated[App, Depends(the_app)]
TheAppRead = Annotated[App, Depends(the_app_read)]


# ── what a call step reaches of the live side ──


# A call step dials as the dial endpoint does, on what serves calls on this gateway, and first asks who
# takes the agent's calls. `LiveParts`, which the dial takes, never leaves the live side: it is bound
# here, so flows' service is handed the dial and the holders by name and never the parts.
def dial_of(parts: TheLive) -> Dial:
    """The live side's dial, bound to what serves calls on this gateway."""

    async def dial(session: AsyncSession, placement: live.Placement) -> live.PlacedCall:
        return await live.place_call(session, parts, placement)

    return dial


def holders_of(parts: TheLive) -> Holders:
    """Who holds each agent now, as a call step asks."""
    return parts.holders


TheDial = Annotated[Dial, Depends(dial_of)]
TheHolders = Annotated[Holders, Depends(holders_of)]
