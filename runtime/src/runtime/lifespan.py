"""The gateway's lifespan: what the process builds once and yields as its state, and what it closes after."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TypedDict

import httpx
from fastapi import FastAPI

from runtime.accounts import tasks as accounts_tasks
from runtime.accounts.service.key_cache import KeyCache
from runtime.alerts import tasks as alerts_tasks
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.logs import Logs
from runtime.calls.log.relay import Relay
from runtime.calls.log.store import Store
from runtime.calls.log.writer import LANES, Writer
from runtime.config import Settings, load_settings
from runtime.enums import Env
from runtime.exceptions import PinecallError
from runtime.fleet import tasks as fleet_tasks
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from runtime.handles import Handles
from runtime.kit.crypto import Vault
from runtime.kit.loops import Loops
from runtime.knowledge.service.extraction_golden import EXTRACTION_RUNS_A_MINUTE
from runtime.livekit import open_servers
from runtime.mail.service.mailboxes import Mailbox, read_environment_mailbox
from runtime.mail.service.outbox import Outbox
from runtime.platform.service.attempts import AttemptThrottle
from runtime.postgres import create_engine, session_maker
from runtime.providers.service.speech import SAMPLES_A_MINUTE
from runtime.providers.service.transcription import TRANSCRIPTIONS_A_MINUTE
from runtime.redis import open_signal
from runtime.signin.service.codes import LoginCodes
from runtime.signin.service.google import Newcomers
from runtime.signin.service.oidc import Oidc
from runtime.signin.service.pairings import Pairings
from runtime.signin.service.passwords import SIGN_IN_TRIES, PasswordThrottle
from runtime.signin.service.signup import SignUps
from runtime.signin.service.turnstile import Turnstile
from runtime.telephony import tasks as telephony_tasks
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.rebuild import Owed

logger = logging.getLogger(__name__)

NO_BOX_MAIL = "PINECALL_SMTP_URL does not read (%s): the box sends no email of its own"


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
    samples: AttemptThrottle
    transcriptions: AttemptThrottle
    extraction_runs: AttemptThrottle
    roster: Roster
    offering: Offering
    sip_names: SipNames
    writer: Writer
    log_store: Store
    relay: Relay
    feeds: Feeds
    logs: Logs


# Everything opened goes on the stack: a failed start closes what opened, a stop closes it all.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[State]:
    """Build the process's state once, run its loops, and close all of it after."""
    async with AsyncExitStack() as stack:
        handles = await _connections(load_settings(), stack)
        writer, log_store, relay, feeds, logs = _log_engine(handles, stack)
        loops = Loops()
        stack.push_async_callback(loops.stop)
        outbox = Outbox(handles.sessions, handles.vault, _box_mailbox(handles.settings))
        stack.push_async_callback(outbox.drain)
        key_cache = KeyCache(handles.sessions, handles.signal)
        loops.start(accounts_tasks.hear_revocations.bind(key_cache, handles.signal))
        roster, offering = await _fleet(handles, loops, stack)
        sessions, vault = handles.sessions, handles.vault
        sip_names = _sip_names(handles.settings)
        loops.start(telephony_tasks.rebuild_sip.bind(Owed(), sessions, vault, handles.servers, sip_names))
        loops.start(alerts_tasks.post_alerts.bind(sessions, vault, handles.http))
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
            samples=AttemptThrottle(sessions, SAMPLES_A_MINUTE),
            transcriptions=AttemptThrottle(sessions, TRANSCRIPTIONS_A_MINUTE),
            extraction_runs=AttemptThrottle(sessions, EXTRACTION_RUNS_A_MINUTE),
            roster=roster,
            offering=offering,
            sip_names=sip_names,
            writer=writer,
            log_store=log_store,
            relay=relay,
            feeds=feeds,
            logs=logs,
        )


# The writer has a pool of its own, one connection per lane, out of the one PINECALL_DB_POOL (`_connections`
# leaves them): an append never waits for an endpoint, nor an endpoint for an append. Its drain is pushed
# before everything that appends on its way out, so it runs after them and before the engines close:
# every append a request was promised is written.
def _log_engine(handles: Handles, stack: AsyncExitStack) -> tuple[Writer, Store, Relay, Feeds, Logs]:
    """The log's engine: the writer on its own pool, the store, the relay, the feeds and the logs."""
    writing = create_engine(handles.settings, pool_size=len(LANES))
    stack.push_async_callback(writing.dispose)
    writer = Writer(session_maker(writing))
    stack.push_async_callback(writer.drain)
    store = Store(handles.sessions, writer)
    relay = Relay(handles.signal, store)
    stack.push_async_callback(relay.close)
    feeds = Feeds(relay, store)
    return writer, store, relay, feeds, Logs(store, relay, feeds)


# The roster hears the other gateways' workers before the first request; the dispatcher offers on it.
async def _fleet(handles: Handles, loops: Loops, stack: AsyncExitStack) -> tuple[Roster, Offering]:
    """The roster and the dispatcher, the roster listening and the fleet's two loops started."""
    roster = Roster(handles.signal)
    await roster.start()
    stack.push_async_callback(roster.close)
    offering = Offering(handles.sessions, handles.servers, roster)
    loops.start(fleet_tasks.sweep_offers.bind(offering))
    loops.start(fleet_tasks.watch_roster.bind(roster))
    return roster, offering


# What the box is to a carrier, read from the settings once: no use case of telephony reads one itself.
def _sip_names(settings: Settings) -> SipNames:
    secret = settings.livekit_api_secret
    return SipNames(
        domain=settings.domain,
        sip_domains={env: settings.sip_domain_of(env) for env in Env},
        approve_hooked=settings.approve_hooked,
        livekit_secret=None if secret is None else secret.get_secret_value(),
    )


async def _connections(settings: Settings, stack: AsyncExitStack) -> Handles:
    """Open the process's connections; the stack closes them in reverse."""
    vault = Vault(None if settings.vault_key is None else settings.vault_key.get_secret_value())
    engine = create_engine(settings, pool_size=settings.db_pool - len(LANES))
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
