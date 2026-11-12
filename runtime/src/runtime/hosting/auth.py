"""Hosting's dependencies: the env's runner, the app a path names, the page a name reaches, and what they stand on."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.handles import TheSessions, TheSettings
from runtime.hosting.service import pages, releases
from runtime.hosting.service.apps import App, Processes
from runtime.live.auth import AppKey, TheLive
from runtime.platform import service as platform
from runtime.postgres import Session

RunnerKey = Annotated[Actor, Depends(Authenticator(KeyScope.runner))]


# ── the app of a path ──


def the_app(name: str, actor: AppKey) -> App:
    """The path's app as the key acts: its org, its env, and the name, which may be a new app's."""
    return App(org=actor.org, env=actor.env, name=name)


def the_new_app(name: str, actor: AppKey) -> App:
    """The path's app as a deploy names it: a name short enough to be part of a host name."""
    return App(org=actor.org, env=actor.env, name=releases.check_name(name))


def the_runners_app(org: str, name: str, actor: RunnerKey) -> App:
    """Any org's app in the runner's env, as the runner names it."""
    return App(org=org, env=actor.env, name=name)


TheApp = Annotated[App, Depends(the_app)]
TheNewApp = Annotated[App, Depends(the_new_app)]
TheRunnersApp = Annotated[App, Depends(the_runners_app)]


# ── an app's page ──


async def the_page(host: str, request: Request, settings: TheSettings, session: Session) -> pages.Paged:
    """The page a request by an app's own name reaches; 404 for any other name."""
    came_in_by = request.headers.get("host", "")
    return await pages.resolve_page(session, settings.pages_domain, host, came_in_by)


def pages_of(connection: HTTPConnection) -> pages.Pages:
    """The pages this process keeps unpacked."""
    kept: pages.Pages = connection.state.pages
    return kept


def page_tickets_of(sessions: TheSessions) -> platform.AttemptThrottle:
    """What counts the tickets and codes one address asked for this minute."""
    return platform.AttemptThrottle(sessions, pages.TICKETS_A_MINUTE)


ThePage = Annotated[pages.Paged, Depends(the_page)]
ThePages = Annotated[pages.Pages, Depends(pages_of)]
ThePageTickets = Annotated[platform.AttemptThrottle, Depends(page_tickets_of)]


# ── what the live side says of an org's processes ──


# `LiveParts` never leaves the live side: hosting's service is handed the sockets by name.
def processes_of(parts: TheLive) -> Processes:
    """The app sockets open on every gateway: what each of an org's processes says it runs on."""
    return parts.sockets


TheProcesses = Annotated[Processes, Depends(processes_of)]
