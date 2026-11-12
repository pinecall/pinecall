"""The gateway's app: its endpoints and middleware on a new FastAPI app, and the one answer to a refusal."""

import asyncio
import logging
import re

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.types import Scope

from runtime import api
from runtime.accounts.auth import resolve_actor
from runtime.auth import ActorMiddleware
from runtime.config import Settings
from runtime.exceptions import PinecallError, ServiceUnavailable, TooManyRequests, Unauthorized
from runtime.handles import Handles
from runtime.kit.middleware import AllowedOrigins, BodyCeiling, NamesUnder
from runtime.lifespan import lifespan
from runtime.postgres import STATEMENT_TIMEOUT_MS, busy

logger = logging.getLogger(__name__)

# The second way a database too busy to answer now shows (the first is the pool's, `busy`); a
# worker outlasts a 503 and retries.
TOO_SLOW = "the database took more than {took:g} s to answer; try again"
QUERY_CANCELED = "57014"
INTERNAL = "the gateway failed to answer this request"

# Capacitor's WebView origins: iOS serves from capacitor://localhost, Android from https://localhost.
THE_APPS_WEBVIEWS = ("capacitor://localhost", "https://localhost")
API_PREFIX = "/v1/"
# A bearer, never a cookie: Allow-Credentials is never sent.
ALLOWED_HEADERS = ("authorization", "content-type", "pinecall-env", "pinecall-corner", "last-event-id")
# A token of one call reads its own endpoints from any page: GET only, no credentials. A recorded line
# and a document an agent published are read by any page with no key at all.
A_PAGES_READS = re.compile(
    r"^/v1/(calls/[^/]+/(events|state|recording)|codes/[^/]+|lines/[^/]+|agents/[^/]+/public/[^/]+)$"
)
# And says its own hang-up: the one POST a page makes with a token, as its tab closes.
A_PAGE_HANGS_UP = re.compile(r"^/v1/calls/[^/]+/hangup$")
# The most any request carries, above every endpoint's own cap: a body past it is refused as it
# streams in, never held whole in memory.
LARGEST_BODY = 32 * 1024 * 1024


# Set from the signal handler, through the loop: streams never end on their own, and a stop would
# otherwise wait out the grace period and cut them mid-frame.
def announce_closing(app: FastAPI) -> None:
    """Tell every open stream the process is stopping."""
    closing: asyncio.Event = app.state.closing
    asyncio.get_running_loop().call_soon_threadsafe(closing.set)


async def answer_refusal(_request: Request, error: Exception) -> Response:
    """A refusal answered with its status and its sentence."""
    status = error.status if isinstance(error, PinecallError) else 500
    headers = {"WWW-Authenticate": "Bearer"} if isinstance(error, Unauthorized) else None
    if isinstance(error, TooManyRequests) and error.retry_after_s is not None:
        headers = {"Retry-After": str(error.retry_after_s)}
    return JSONResponse({"detail": str(error)}, status_code=status, headers=headers)


async def answer_busy(request: Request, error: Exception) -> Response:
    """A full pool or a statement past its timeout, answered 503 with its one sentence."""
    if isinstance(error, PoolTimeout):
        return await answer_refusal(request, busy())
    if isinstance(error, DBAPIError) and getattr(error.orig, "sqlstate", None) == QUERY_CANCELED:
        return await answer_refusal(request, ServiceUnavailable(TOO_SLOW.format(took=STATEMENT_TIMEOUT_MS / 1000)))
    logger.error("the database refused a request", exc_info=error)
    return JSONResponse({"detail": INTERNAL}, status_code=500)


def list_allowed_origins(settings: Settings) -> tuple[str, ...]:
    """The app's two WebViews, then PINECALL_APP_ORIGINS, each once."""
    named = (item.strip() for item in settings.app_origins.split(","))
    return tuple(dict.fromkeys((*THE_APPS_WEBVIEWS, *(item for item in named if item))))


# One gateway's app: a test serves two, each with its own state. `closing` is made here and not in
# the lifespan because uvicorn's signal handler reaches it outside any request: it is the one thing
# kept on `app.state`, and the lifespan yields it with the rest.
def create_app() -> FastAPI:
    """The gateway's endpoints and its refusals, on a new app."""
    app = FastAPI(title="Pinecall gateway", lifespan=lifespan, docs_url="/v1/docs", redoc_url="/v1/redoc")
    app.state.closing = asyncio.Event()
    app.add_middleware(ActorMiddleware, resolve=resolve_actor, refuse=answer_refusal)
    app.add_middleware(
        AllowedOrigins,
        prefix=API_PREFIX,
        origins=_origins_of,
        headers=ALLOWED_HEADERS,
        any_page=A_PAGES_READS,
        any_page_says=A_PAGE_HANGS_UP,
    )
    app.add_middleware(BodyCeiling, most=LARGEST_BODY)
    app.add_middleware(NamesUnder, domain=_pages_domain_of, prefix="/v1/pages", own="/pinecall/", files="/files")
    api.mount(app)
    app.add_exception_handler(PinecallError, answer_refusal)
    app.add_exception_handler(PoolTimeout, answer_busy)
    app.add_exception_handler(DBAPIError, answer_busy)
    return app


# Before the lifespan yielded (a preflight during start) there is no state yet: no origin is allowed.
# Read per request: the settings are loaded by the lifespan, after the middleware is built.
def _pages_domain_of(scope: Scope) -> str | None:
    handles: object = scope.get("state", {}).get("handles")
    return handles.settings.pages_domain if isinstance(handles, Handles) else None


def _origins_of(scope: Scope) -> tuple[str, ...]:
    handles: object = scope.get("state", {}).get("handles")
    return list_allowed_origins(handles.settings) if isinstance(handles, Handles) else ()


app = create_app()
