"""What the gateway's lifespan builds, by family: its connections, the log's engine, the fleet, the live side."""

import functools
import logging
from contextlib import AsyncExitStack
from pathlib import Path

import httpx

from runtime.accounts.service.members import list_test_phones
from runtime.alerts.service.alerts import Alerting
from runtime.alerts.service.spend import UnusualSpend
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.logs import Logs
from runtime.calls.log.relay import Relay
from runtime.calls.log.store import Store
from runtime.calls.log.writer import LANES, Writer
from runtime.calls.recordings import Bucket, Disk, Recordings
from runtime.calls.service.prompts import Prompts
from runtime.config import Settings
from runtime.enums import Env
from runtime.exceptions import ConfigurationError, PinecallError
from runtime.fleet import tasks as fleet_tasks
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from runtime.handles import Handles
from runtime.kit.crypto import Vault
from runtime.kit.loops import Loops
from runtime.kit.s3 import Credentials, ObjectStore
from runtime.live.holders import Holders
from runtime.live.parts import LiveParts
from runtime.live.peers import Owners
from runtime.live.served import Calls
from runtime.live.service import commands
from runtime.live.service.codes import Codes
from runtime.live.service.handoff import Handoffs
from runtime.live.service.tokens import Signer
from runtime.live.service.whatsapp import Threads
from runtime.live.sockets import Sockets
from runtime.livekit import key_pair, open_servers
from runtime.mail.service.mailboxes import Mailbox, read_environment_mailbox
from runtime.postgres import create_engine, session_maker
from runtime.providers.service.health import VendorHealth
from runtime.redis import open_signal
from runtime.signin.service.turnstile import Turnstile
from runtime.telephony.service.carrier import SipNames

logger = logging.getLogger(__name__)

NO_BOX_MAIL = "PINECALL_SMTP_URL does not read (%s): the box sends no email of its own"
NO_SIGNING = "PINECALL_TOKEN_KEY: the gateway signs its log and code tokens with it"


# Until the live side landed these were private to `lifespan.py`, which then passed the three hundred
# lines an entrypoint keeps to: the lifespan is the state and the order it is built in, and each
# family of what it builds is a function here.


# The writer has a pool of its own, one connection per lane, out of the one PINECALL_DB_POOL (`_connections`
# leaves them): an append never waits for an endpoint, nor an endpoint for an append. Its drain is pushed
# before everything that appends on its way out, so it runs after them and before the engines close:
# every append a request was promised is written.
def build_log_engine(handles: Handles, stack: AsyncExitStack) -> tuple[Writer, Store, Relay, Feeds, Logs]:
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


# Built once, from the settings: until 2026-11 each request of a recording built it again. A bucket
# named with no store beside it never starts (`Settings` refuses it), so one named here has all four.
def build_recordings(handles: Handles) -> Recordings:
    """Where the box keeps its calls' audio: the bucket PINECALL_RECORDINGS_BUCKET names, else the disk."""
    settings = handles.settings
    root = Path(settings.recordings_root)
    secret = settings.s3_secret_access_key
    named = (settings.recordings_bucket, settings.s3_endpoint, settings.s3_region, settings.s3_access_key_id)
    bucket, endpoint, region, key_id = named
    if bucket is None or endpoint is None or region is None or key_id is None or secret is None:
        return Disk(root)
    credentials = Credentials(region, key_id, secret.get_secret_value())
    return Bucket(root, bucket, ObjectStore(endpoint, credentials, handles.http))


# The roster hears the other gateways' workers before the first request; the dispatcher offers on it.
# A worker that changed is said on the box's feed, where the operator's page follows the fleet.
async def build_fleet(handles: Handles, feeds: Feeds, loops: Loops, stack: AsyncExitStack) -> tuple[Roster, Offering]:
    """The roster and the dispatcher, the roster listening and the fleet's two loops started."""
    roster = Roster(handles.signal, on_change=lambda changed: feeds.announce_to_the_box("worker.changed", changed))
    await roster.start()
    stack.push_async_callback(roster.close)
    offering = Offering(handles.sessions, handles.servers, roster)
    loops.start(fleet_tasks.sweep_offers.bind(offering))
    loops.start(fleet_tasks.watch_roster.bind(roster))
    return roster, offering


# What serves a call on this gateway. Each object that tells the others what it holds is started before
# the first request and closed after the last. The phones people said were theirs are rows: a gateway
# starting says them again to the others. The handoffs are heard last, once there are calls to hand.
async def build_live_side(
    handles: Handles,
    stack: AsyncExitStack,
    engine: tuple[Store, Logs, Feeds, Prompts],
    offering: Offering,
    alerting: Alerting,
) -> LiveParts:
    """The live side's parts: the sockets, who holds each agent, the calls served, and what they reach."""
    signal = handles.signal
    store, logs, feeds, prompts = engine
    sockets, owners, holders = Sockets(signal), Owners(signal), Holders(signal, logs, store)
    calls = Calls(signal, sockets, owners, functools.partial(commands.hear, sockets))
    handoffs = Handoffs(calls, holders)
    for part in (sockets, owners, holders, calls, handoffs):
        await part.start()
        stack.push_async_callback(part.close)
    async with handles.sessions() as session:
        for member in await list_test_phones(session):
            if member.test_phone is not None:
                holders.route_phone(Env.sandbox, member.test_phone, member.id)
    return LiveParts(
        settings=handles.settings,
        vault=handles.vault,
        http=handles.http,
        servers=handles.servers,
        signal=signal,
        sessions=handles.sessions,
        store=store,
        logs=logs,
        feeds=feeds,
        prompts=prompts,
        sockets=sockets,
        holders=holders,
        owners=owners,
        calls=calls,
        offering=offering,
        alerting=alerting,
        health=VendorHealth(),
        spending=UnusualSpend(),
    )


# A room's token is signed with LiveKit's pair, which opens the room; every other token of a call (its
# log's, a code's, a resume) with the gateway's own key. A gateway given no key of its own never starts:
# it would hand out tokens nothing could read back.
def build_signer(settings: Settings) -> Signer:
    """What signs and reads the tokens of a call, on the box's LiveKit pair and its own key."""
    if settings.token_key is None:
        raise ConfigurationError(NO_SIGNING)
    api_key, secret = key_pair(settings)
    return Signer(api_key, secret, settings.token_key.get_secret_value())


def build_codes(handles: Handles, logs: Logs) -> Codes:
    """Every agent's caller codes: written on the logs, a waiting page woken on the signal."""
    return Codes(handles.sessions, logs, handles.signal)


# What waited on WhatsApp when this process started is read back off the agents' logs before the first
# app registers, and the messages other gateways hand on are taken from then on.
async def build_threads(live: LiveParts, stack: AsyncExitStack) -> Threads:
    """The WhatsApp threads of this gateway, what waited loaded and the handed-on messages heard."""
    threads = Threads(live)
    await threads.load()
    await threads.start()
    stack.push_async_callback(threads.close)
    return threads


# What the box is to a carrier, read from the settings once: no use case of telephony reads one itself.
def read_sip_names(settings: Settings) -> SipNames:
    """The box's names as a carrier reaches them: its domain, each env's SIP name, and LiveKit's secret."""
    secret = settings.livekit_api_secret
    return SipNames(
        domain=settings.domain,
        sip_domains={env: settings.sip_domain_of(env) for env in Env},
        approve_hooked=settings.approve_hooked,
        livekit_secret=None if secret is None else secret.get_secret_value(),
    )


async def open_connections(settings: Settings, stack: AsyncExitStack) -> Handles:
    """Open the process's connections; the stack closes them in reverse."""
    vault = Vault(None if settings.vault_key is None else settings.vault_key.get_secret_value())
    engine = create_engine(settings, pool_size=settings.db_pool - len(LANES))
    stack.push_async_callback(engine.dispose)
    http = await stack.enter_async_context(httpx.AsyncClient())
    servers = await stack.enter_async_context(open_servers(settings))
    signal = await stack.enter_async_context(open_signal(settings))
    return Handles(settings, vault, http, servers, signal, engine, session_maker(engine))


# With no secret set the verifier passes every token: a box with no Turnstile asks for none.
def build_turnstile(handles: Handles) -> Turnstile:
    """What checks a person's Turnstile token, on the secret the settings name."""
    secret = handles.settings.turnstile_secret
    return Turnstile(handles.http, None if secret is None else secret.get_secret_value(), handles.settings.domain)


# A box without mail still starts: its emails are not sent, and /.well-known says so.
def read_box_mailbox(settings: Settings) -> Mailbox | None:
    """The box's own mailbox as PINECALL_SMTP_URL names it; None, said, where it does not read."""
    url = None if settings.smtp_url is None else settings.smtp_url.get_secret_value()
    try:
        return read_environment_mailbox(url, settings.mail_from)
    except PinecallError as unreadable:
        logger.warning(NO_BOX_MAIL, unreadable)
        return None
