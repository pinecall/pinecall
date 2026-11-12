"""A setting tried once outside a call: a vendor's no is heard where it is set, and a key is kept once it answers."""

import asyncio
import contextlib
import dataclasses
from collections.abc import Mapping
from typing import Any

from livekit.agents import APIConnectOptions
from livekit.agents.llm import ChatContext
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Stage
from runtime.exceptions import PinecallError, UpstreamError, ValidationError
from runtime.kit.crypto import Vault
from runtime.postgres import BoxSession
from runtime.providers.catalog import Catalog
from runtime.providers.service import credentials as held
from runtime.providers.service import plugins, speech, voices
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.pipeline import vendor_on
from runtime.providers.service.plugins import Vendor
from runtime.providers.service.refusals import refusing
from runtime.providers.service.signatures import TurnKnobs
from runtime.providers.service.stages import (
    build_realtime,
    ears_outside_a_call,
    silence,
    thinking_outside_a_call,
)
from runtime.providers.stage import Credentials, Running

# A vendor slower than this to say a word is not refusing the setting, it is not answering.
TRY_S = 12.0
LINE = "OK."
# Ears that keep listening once the input ends took the connection: a refusal comes back sooner.
LISTENED_S = 4.0
# Half a second of silence at the rate every plugin takes, to open the ears and close them.
SILENCE_MS = 500
STAGE_NAMES: dict[Stage, str] = {Stage.llm: "model", Stage.stt: "ears", Stage.tts: "voice"}
# The job a key is tried on, the first the vendor does: a model's answer is the cheapest to ask.
JOBS: tuple[Stage, ...] = (Stage.llm, Stage.tts, Stage.stt)
# Once, at once: a setting is not worth livekit's retries, and a person is waiting on the answer.
ONCE = APIConnectOptions(max_retry=0, timeout=10.0)


async def try_stage(
    stage: Stage,
    running: Running,
    turn: TurnKnobs | None = None,
    *,
    what: str | None = None,
    tried: Mapping[str, object] | None = None,
    catalog: Catalog | None = None,
) -> None:
    """The stage asked one small thing; the vendor's no is ValidationError, its silence UpstreamError.

    `tried` names the knobs this set moved, so a refusal says what was tried beside the vendor's words;
    with the catalog, a voice it moved is one the vendor lists too.
    """
    named = what or f"the {STAGE_NAMES[stage]} this sets"
    if tried:
        named += " (" + ", ".join(f"{knob} {_as_typed(value)}" for knob, value in tried.items()) + ")"

    def say_unanswered(why: str) -> str:
        return f"{running.vendor} did not answer while {named} was tried: {why}; nothing was kept, try again"

    try:
        async with asyncio.timeout(TRY_S):
            with refusing(running.vendor, named, silence=say_unanswered):
                try:
                    await _ask(stage, running, turn, catalog if tried is not None and "voice" in tried else None)
                except ValidationError as said:
                    # The plugin's constructor or the lists turned it down: named after what was tried.
                    raise ValidationError(f"{running.vendor} refused {named}: {said}") from said
    except TimeoutError as slow:
        words = say_unanswered(f"no answer in {TRY_S:.0f} s")
        raise UpstreamError(words, vendor=running.vendor, retryable=True) from slow


# A key is tried as a call would run it, on each job the vendor does, until one answers: a key that
# answers none would fail every call it is kept for, and a key for one of them (a speech-to-text plan
# of a vendor that also speaks) is kept for that one. Refused, it is in the first job's words.
async def try_key(vendor: Vendor, credentials: Credentials, catalog: Catalog) -> None:
    """The vendor asked one small thing on these credentials per job; refused in its words, nothing kept."""
    first: PinecallError | None = None
    for stage in JOBS:
        if stage not in vendor.does:
            continue
        try:
            await try_stage(stage, vendor_on(stage, vendor.name, credentials, catalog), what="this key")
        except (ValidationError, UpstreamError) as refused:
            first = first or refused
            continue
        return
    if first is not None:
        raise first


# A realtime model opens its session with the call: built, its class and its arguments are tried,
# and a vendor's no to them is heard here; its key is the one the org already brought.
async def try_realtime(running: Running) -> None:
    """The realtime model built as a voice call builds it, and closed; refused in our words."""
    talking = build_realtime(running)
    await talking.aclose()


# ── a key brought: checked, tried, and only then kept ──


async def bring_key(
    session: AsyncSession, vault: Vault, org: str, vendor: str, key: str | None, credentials: Mapping[str, Any] | None
) -> None:
    """Keep the org's own credentials for a vendor, once the vendor answered on them; its calls run on them next."""
    named = plugins.parse_vendor(vendor)
    brought = held.read_credentials(key, credentials)
    held.check_credentials(named, brought)
    await try_key(plugins.list_vendors()[named], brought, await get_catalog(session))
    await held.put_own_credentials(session, vault, org, named, brought)


# The operator's own word: an address or a file in the object is theirs to name, so it is not checked.
async def bring_box_key(
    session: BoxSession, vault: Vault, vendor: str, key: str | None, credentials: Mapping[str, Any] | None
) -> None:
    """Keep the box's own credentials for a vendor, once it answered on them; orgs it lends to run on them next."""
    named = plugins.parse_vendor(vendor)
    brought = held.read_credentials(key, credentials)
    await try_key(plugins.list_vendors()[named], brought, await get_catalog(session))
    await held.put_box_credentials(session, vault, named, brought)


# ── private ──


async def _ask(stage: Stage, running: Running, turn: TurnKnobs | None, listing: Catalog | None) -> None:
    match stage:
        case Stage.tts:
            await speech.say(running, LINE, speech.hear_sample)
            if listing is not None:
                await voices.check_listed(running, listing)
        case Stage.llm:
            await _ask_the_model(running)
        case Stage.stt:
            await _open_the_ears(running, turn)


async def _ask_the_model(running: Running) -> None:
    context = ChatContext.empty()
    context.add_message(role="user", content=LINE)
    async with thinking_outside_a_call(running) as model, model.chat(chat_ctx=context, conn_options=ONCE) as stream:
        async for _ in stream:
            break


# Ears that only take a whole utterance have nothing to open: they are tried by the first call.
# The turn's knobs are the call's, so a silence or a bar the vendor does not take is its no here.
async def _open_the_ears(running: Running, turn: TurnKnobs | None) -> None:
    async with ears_outside_a_call(running, turn) as ears:
        if not ears.capabilities.streaming:
            return
        async with ears.stream(conn_options=ONCE) as stream:
            stream.push_frame(silence(SILENCE_MS))
            stream.end_input()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(LISTENED_S):
                    async for _ in stream:
                        continue


# A turn's knobs as they are typed (`endpointing_ms=400`), never the dataclass's repr with every unset one.
def _as_typed(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        given = {name: one for name, one in dataclasses.asdict(value).items() if one is not None}
        return " ".join(f"{name}={one}" for name, one in given.items()) or "none"
    return value
