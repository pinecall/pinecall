"""The gateway process: wired once at start, its endpoints, the one answer to a refusal, its pages."""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Protocol

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import Scope

from pinecall_runtime import api
from pinecall_runtime.accounts.auth import resolve_actor
from pinecall_runtime.accounts.service import attempts, keys, mail, signin, tokens
from pinecall_runtime.agents.service.prompts import PromptCache
from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.tasks import reap_forever
from pinecall_runtime.config import Settings, load_settings
from pinecall_runtime.evals import service as evals
from pinecall_runtime.exceptions import (
    ConfigurationError,
    PinecallError,
    ServiceUnavailable,
    TooManyRequests,
    Unauthorized,
)
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.fleet.tasks import sweep_offers, watch_roster
from pinecall_runtime.kit.auth import ENV_HEADER, HOLDER_HEADER, ActorMiddleware
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.middleware import AllowedOrigins, BodyCeiling
from pinecall_runtime.knowledge import service as knowledge
from pinecall_runtime.livekit import key_pair, open_servers
from pinecall_runtime.postgres import POOL_WAIT_S, STATEMENT_TIMEOUT_MS, box_task, create_engine, session_maker
from pinecall_runtime.providers import service as providers
from pinecall_runtime.redis import open_signal
from pinecall_runtime.telephony import service as telephony

logger = logging.getLogger(__name__)

NO_SIGNING = "PINECALL_TOKEN_KEY: the gateway signs its log and code tokens with it"
NO_EMBEDDER = "the gateway starts with no embedder: %s"
NO_BOX_MAIL = "PINECALL_SMTP_URL does not read (%s): the box sends no email of its own"
# The two ways a database too busy to answer now shows; a worker outlasts a 503 and retries.
NO_CONNECTION = "the database is busy: no connection came free within {wait:g} s; try again"
TOO_SLOW = "the database took more than {took:g} s to answer; try again"
QUERY_CANCELED = "57014"
INTERNAL = "the gateway failed to answer this request"

# Capacitor's WebView origins: iOS serves from capacitor://localhost, Android from https://localhost.
THE_APPS_WEBVIEWS = ("capacitor://localhost", "https://localhost")
API_PREFIX = "/v1/"
# A bearer, never a cookie: Allow-Credentials is never sent.
ALLOWED_HEADERS = ("authorization", "content-type", ENV_HEADER, HOLDER_HEADER, "last-event-id")
# A token of one call reads its own endpoints from any page: GET only, no credentials.
A_PAGES_READS = re.compile(r"^/v1/(calls/[^/]+/(events|state|recording)|codes/[^/]+)$")
# The most any request carries, above every endpoint's own cap (a hold melody 20 MiB, a hosted
# app's source 10 MiB): a body past it is refused as it streams in, never held whole in memory.
LARGEST_BODY = 32 * 1024 * 1024


# Everything opened goes on the stack: a failed start closes what opened, a stop closes it all.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Wire the box once, run its loops, and close all of it after."""
    settings = load_settings()
    async with AsyncExitStack() as stack:
        state = await _wire(settings, stack)
        for name, value in state.items():
            setattr(app.state, name, value)
        yield


async def _wire(settings: Settings, stack: AsyncExitStack) -> dict[str, Any]:
    """Open the connections, then what the gateway keeps in memory; the reverse at the end."""
    if settings.token_key is None:
        raise ConfigurationError(NO_SIGNING)
    livekit_key, livekit_secret = key_pair(settings)
    vault = Vault(None if settings.vault_key is None else settings.vault_key.get_secret_value())
    engine = create_engine(settings)
    stack.push_async_callback(engine.dispose)
    sessions = session_maker(engine)
    http = await stack.enter_async_context(httpx.AsyncClient())
    servers = await stack.enter_async_context(open_servers(settings))
    signal = await stack.enter_async_context(open_signal(settings))
    handles = Handles(settings, vault, http, servers, signal, sessions)
    logs = calls.Logs(calls.Store(sessions), signal)
    # Pushed before everything that appends on its way out, so it runs after them and before the
    # engine closes: every append a request was promised is written.
    stack.push_async_callback(logs.store.writer.drain)
    stack.push_async_callback(logs.close)
    live = calls.Live(signal)
    await _started(stack, live)
    registry = AgentRegistry(signal, logs)
    await _started(stack, registry)
    roster = fleet.Roster(signal, on_change=lambda event: logs.announce_to_the_box("worker.changed", event))
    await _started(stack, roster)
    offering = fleet.Offering(sessions, servers, roster)
    serving = calls.Serving(
        handles=handles,
        logs=logs,
        live=live,
        registry=registry,
        signer=tokens.Signer(livekit_key, livekit_secret, settings.token_key.get_secret_value()),
        codes=calls.Codes(logs),
        embedder=await _embedder(sessions, vault, http),
        prompts=PromptCache(),
        counters=calls.VendorCounters(),
        roster=roster,
        offering=offering,
    )
    threads = calls.Threads(serving, registry)
    await threads.load()
    await _started(stack, threads)
    key_cache = keys.KeyCache(sessions, signal)
    await _started(stack, key_cache)
    outbox = mail.Outbox(sessions, vault, _box_mailbox(settings))
    stack.push_async_callback(outbox.drain)
    # Pushed after the wiring, so the calls stop before the logs and the engine close under them.
    simulations = evals.Simulations()
    stack.push_async_callback(simulations.stop)
    runner = evals.Runner(sessions)
    stack.push_async_callback(runner.stop)
    # The loops that never end, which /metrics reports dead if one does.
    loops = {
        "reaper": box_task(reap_forever(serving)),
        "sweep": box_task(sweep_offers(offering)),
        "roster": box_task(watch_roster(roster)),
    }
    # After the start, so a slow SFU never keeps the gateway from answering; again until whole.
    trunks = box_task(telephony.rebuilt_until_whole(handles))
    for task in (*loops.values(), trunks):
        stack.push_async_callback(_cancel, task)
    return {
        "handles": handles,
        "engine": engine,
        "sessions": sessions,
        "logs": logs,
        "registry": registry,
        "roster": roster,
        "offering": offering,
        "serving": serving,
        "threads": threads,
        "counters": serving.counters,
        "key_cache": key_cache,
        "sign_ins": signin.SignIns(sessions, vault, signal),
        "outbox": outbox,
        "samples": attempts.AttemptThrottle(sessions, providers.SAMPLES_A_MINUTE),
        "runner": runner,
        "simulations": simulations,
        "closing": asyncio.Event(),
        "loops": loops,
    }


# Set from the signal handler, through the loop: streams never end on their own, and a stop would
# otherwise wait out the grace period and cut them mid-frame.
def announce_closing(app: FastAPI) -> None:
    """Tell every open stream the process is stopping."""
    closing: object = getattr(app.state, "closing", None)
    if isinstance(closing, asyncio.Event):
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
        return await answer_refusal(request, ServiceUnavailable(NO_CONNECTION.format(wait=POOL_WAIT_S)))
    if isinstance(error, DBAPIError) and getattr(error.orig, "sqlstate", None) == QUERY_CANCELED:
        return await answer_refusal(request, ServiceUnavailable(TOO_SLOW.format(took=STATEMENT_TIMEOUT_MS / 1000)))
    logger.error("the database refused a request", exc_info=error)
    return JSONResponse({"detail": INTERNAL}, status_code=500)


def origins_allowed(settings: Settings) -> tuple[str, ...]:
    """The app's two WebViews, then PINECALL_APP_ORIGINS, each once."""
    named = (item.strip() for item in settings.app_origins.split(","))
    return tuple(dict.fromkeys((*THE_APPS_WEBVIEWS, *(item for item in named if item))))


# One gateway's app: a test serves two, each with its own state. Swagger under /v1: the console
# has a /docs screen of its own. The console is the last route: a built file is itself, any other
# path is the page.
def create_app() -> FastAPI:
    """The gateway's endpoints, its refusals, the widget and the console, on a new app."""
    app = FastAPI(title="Pinecall gateway", lifespan=lifespan, docs_url="/v1/docs", redoc_url="/v1/redoc")
    app.add_middleware(ActorMiddleware, resolve=resolve_actor)
    app.add_middleware(
        AllowedOrigins, prefix=API_PREFIX, origins=_origins_of, headers=ALLOWED_HEADERS, any_page=A_PAGES_READS
    )
    app.add_middleware(BodyCeiling, most=LARGEST_BODY)
    api.mount(app)
    app.add_exception_handler(PinecallError, answer_refusal)
    app.add_exception_handler(PoolTimeout, answer_busy)
    app.add_exception_handler(DBAPIError, answer_busy)
    return app


def _origins_of(scope: Scope) -> tuple[str, ...]:
    handles: object = getattr(scope["app"].state, "handles", None)
    return origins_allowed(handles.settings) if isinstance(handles, Handles) else ()


# A box with no embedder still starts: every endpoint that embeds says what the operator must set.
async def _embedder(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, http: httpx.AsyncClient
) -> knowledge.Embedder | None:
    async with sessions() as session:
        try:
            catalog = await providers.get_catalog(session)
            return knowledge.embedder_for(catalog, await providers.box_credentials(session, vault), http)
        except ServiceUnavailable as missing:
            logger.warning(NO_EMBEDDER, missing)
            return None


# A box without mail still starts: its emails are not sent, and /.well-known says so.
def _box_mailbox(settings: Settings) -> mail.Mailbox | None:
    if settings.smtp_url is None:
        return None
    try:
        return mail.parse_mailbox_url(settings.smtp_url.get_secret_value(), settings.mail_from or "")
    except PinecallError as unreadable:
        logger.warning(NO_BOX_MAIL, unreadable)
        return None


class _Running(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...


async def _started(stack: AsyncExitStack, running: _Running) -> None:
    await running.start()
    stack.push_async_callback(running.close)


async def _cancel[T](task: asyncio.Task[T]) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = create_app()
