"""The gateway process: what it builds once and yields as its state, its app, and the one answer to a refusal."""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TypedDict

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.types import Scope

from runtime import api
from runtime.accounts import tasks as accounts_tasks
from runtime.accounts.auth import resolve_actor
from runtime.accounts.service.key_cache import KeyCache
from runtime.auth import ActorMiddleware
from runtime.config import Settings, load_settings
from runtime.exceptions import PinecallError, ServiceUnavailable, TooManyRequests, Unauthorized
from runtime.handles import Handles
from runtime.kit.crypto import Vault
from runtime.kit.loops import Loops
from runtime.kit.middleware import AllowedOrigins, BodyCeiling
from runtime.livekit import open_servers
from runtime.mail.service.mailboxes import Mailbox, read_environment_mailbox
from runtime.mail.service.outbox import Outbox
from runtime.platform.service.attempts import AttemptThrottle
from runtime.postgres import STATEMENT_TIMEOUT_MS, busy, create_engine, session_maker
from runtime.redis import open_signal
from runtime.signin.service.codes import LoginCodes
from runtime.signin.service.google import Newcomers
from runtime.signin.service.oidc import Oidc
from runtime.signin.service.pairings import Pairings
from runtime.signin.service.passwords import SIGN_IN_TRIES, PasswordThrottle
from runtime.signin.service.signup import SignUps
from runtime.signin.service.turnstile import Turnstile

logger = logging.getLogger(__name__)

# The second way a database too busy to answer now shows (the first is the pool's, `busy`); a
# worker outlasts a 503 and retries.
TOO_SLOW = "the database took more than {took:g} s to answer; try again"
QUERY_CANCELED = "57014"
INTERNAL = "the gateway failed to answer this request"
NO_BOX_MAIL = "PINECALL_SMTP_URL does not read (%s): the box sends no email of its own"

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


# What the lifespan builds, once, and every request reads through a getter: each object has exactly
# one getter, declared beside its type, and nothing else reads this. A domain's long-lived object
# enters here in the commit that builds the domain.
class State(TypedDict):
    """The gateway's process state."""

    handles: Handles
    closing: asyncio.Event
    loops: Loops
    outbox: Outbox
    key_cache: KeyCache
    login_codes: LoginCodes
    pairings: Pairings
    sign_ups: SignUps
    newcomers: Newcomers
    oidc: Oidc
    password_throttle: PasswordThrottle
    sign_in_attempts: AttemptThrottle
    turnstile: Turnstile


# Everything opened goes on the stack: a failed start closes what opened, a stop closes it all.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[State]:
    """Build the process's state once, run its loops, and close all of it after."""
    async with AsyncExitStack() as stack:
        handles = await _connections(load_settings(), stack)
        loops = Loops()
        stack.push_async_callback(loops.stop)
        outbox = Outbox(handles.sessions, handles.vault, _box_mailbox(handles.settings))
        stack.push_async_callback(outbox.drain)
        key_cache = KeyCache(handles.sessions, handles.signal)
        loops.start(accounts_tasks.hear_revocations.bind(key_cache, handles.signal))
        sessions, vault = handles.sessions, handles.vault
        yield State(
            handles=handles,
            closing=app.state.closing,
            loops=loops,
            outbox=outbox,
            key_cache=key_cache,
            login_codes=LoginCodes(sessions, vault),
            pairings=Pairings(sessions, vault, handles.signal),
            sign_ups=SignUps(sessions, vault, accepting=handles.settings.signup),
            newcomers=Newcomers(sessions, vault),
            oidc=Oidc(handles.http, sessions, vault),
            password_throttle=PasswordThrottle(sessions),
            sign_in_attempts=AttemptThrottle(sessions, SIGN_IN_TRIES),
            turnstile=_turnstile(handles),
        )


async def _connections(settings: Settings, stack: AsyncExitStack) -> Handles:
    """Open the process's connections; the stack closes them in reverse."""
    vault = Vault(None if settings.vault_key is None else settings.vault_key.get_secret_value())
    engine = create_engine(settings)
    stack.push_async_callback(engine.dispose)
    http = await stack.enter_async_context(httpx.AsyncClient())
    servers = await stack.enter_async_context(open_servers(settings))
    signal = await stack.enter_async_context(open_signal(settings))
    return Handles(settings, vault, http, servers, signal, engine, session_maker(engine))


# With no secret set the verifier passes every token: a box with no Turnstile asks for none.
def _turnstile(handles: Handles) -> Turnstile:
    secret = handles.settings.turnstile_secret
    return Turnstile(handles.http, None if secret is None else secret.get_secret_value(), handles.settings.domain)


# A box without mail still starts: its emails are not sent, and /.well-known says so.
def _box_mailbox(settings: Settings) -> Mailbox | None:
    url = None if settings.smtp_url is None else settings.smtp_url.get_secret_value()
    try:
        return read_environment_mailbox(url, settings.mail_from)
    except PinecallError as unreadable:
        logger.warning(NO_BOX_MAIL, unreadable)
        return None


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
    api.mount(app)
    app.add_exception_handler(PinecallError, answer_refusal)
    app.add_exception_handler(PoolTimeout, answer_busy)
    app.add_exception_handler(DBAPIError, answer_busy)
    return app


# Before the lifespan yielded (a preflight during start) there is no state yet: no origin is allowed.
def _origins_of(scope: Scope) -> tuple[str, ...]:
    handles: object = scope.get("state", {}).get("handles")
    return list_allowed_origins(handles.settings) if isinstance(handles, Handles) else ()


app = create_app()
