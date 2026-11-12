"""The gateway's lifespan: what the process builds once and yields as its state, and what it closes after."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI

from runtime import builders
from runtime.accounts import tasks as accounts_tasks
from runtime.accounts.service.key_cache import KeyCache
from runtime.alerts import tasks as alerts_tasks
from runtime.alerts.service.alerts import Alerting
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.logs import Logs
from runtime.calls.log.relay import Relay
from runtime.calls.log.store import Store
from runtime.calls.log.writer import Writer
from runtime.calls.recordings import Recordings
from runtime.calls.service.lists import list_ended_calls
from runtime.calls.service.prompts import Prompts
from runtime.config import load_settings
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from runtime.handles import Handles
from runtime.kit.loops import Loops
from runtime.knowledge.service.extraction_golden import EXTRACTION_RUNS_A_MINUTE
from runtime.live import tasks as live_tasks
from runtime.live.holders import Holders
from runtime.live.parts import LiveParts
from runtime.live.service.entries import Appends
from runtime.live.service.whatsapp import Threads
from runtime.mail.service.outbox import Outbox
from runtime.platform.service.attempts import AttemptThrottle
from runtime.providers.service.health import VendorHealth
from runtime.providers.service.speech import SAMPLES_A_MINUTE
from runtime.providers.service.transcription import TRANSCRIPTIONS_A_MINUTE
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
    # Whose an agent is, is whose its own log is: the store answers agents', judging's and alerts' `Owners`.
    agent_owners: Store
    recordings: Recordings
    prompts: Prompts
    # The live side's parts, and what it counted of the appends.
    live: LiveParts
    appends: Appends
    # What the lower domains declared and are handed: who holds each agent (agents' `holders`, telephony's
    # `agents_held`), the WhatsApp threads (whatsapp's `threads`), what raises an alert, the vendors failing.
    holders: Holders
    agents_held: Holders
    threads: Threads
    whatsapp_threads: Threads
    alerting: Alerting
    vendor_health: VendorHealth


# Everything opened goes on the stack: a failed start closes what opened, a stop closes it all.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[State]:
    """Build the process's state once, run its loops, and close all of it after."""
    async with AsyncExitStack() as stack:
        handles = await builders.open_connections(load_settings(), stack)
        writer, log_store, relay, feeds, logs = builders.build_log_engine(handles, stack)
        loops = Loops()
        stack.push_async_callback(loops.stop)
        outbox = Outbox(handles.sessions, handles.vault, builders.read_box_mailbox(handles.settings))
        stack.push_async_callback(outbox.drain)
        key_cache = KeyCache(handles.sessions, handles.signal)
        loops.start(accounts_tasks.hear_revocations.bind(key_cache, handles.signal))
        roster, offering = await builders.build_fleet(handles, feeds, loops, stack)
        sessions, vault = handles.sessions, handles.vault
        prompts = Prompts()
        alerting = Alerting(logs, outbox, handles.settings.address)
        live = await builders.build_live_side(handles, stack, (log_store, logs, feeds, prompts), offering, alerting)
        threads = await builders.build_threads(live, stack)
        loops.start(live_tasks.reap.bind(live))
        loops.start(alerts_tasks.sweep_newborns.bind(sessions, alerting, list_ended_calls))
        sip_names = builders.read_sip_names(handles.settings)
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
            turnstile=builders.build_turnstile(handles),
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
            agent_owners=log_store,
            recordings=builders.build_recordings(handles),
            prompts=prompts,
            live=live,
            appends=Appends(),
            holders=live.holders,
            agents_held=live.holders,
            threads=threads,
            whatsapp_threads=threads,
            alerting=alerting,
            vendor_health=live.health,
        )
