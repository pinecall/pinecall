"""A stage a setting changes, tried once outside a call: a vendor's no is heard where it is set."""

import asyncio
import contextlib
from typing import Never

from livekit import rtc
from livekit.agents import APIConnectionError, APIConnectOptions, APIError, APITimeoutError, stt
from livekit.agents.llm import ChatContext
from livekit.agents.utils import http_context

from pinecall_runtime.agents.declaration import Modality, Turn
from pinecall_runtime.exceptions import PinecallError, UpstreamError, ValidationError
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service import keyring, voices
from pinecall_runtime.providers.service.plugins import Credentials, Running, Vendor, words_of
from pinecall_runtime.providers.service.stages import build_realtime, llm_of, stt_of

# A vendor slower than this to say a word is not refusing the setting, it is not answering.
TRY_S = 12.0
LINE = "OK."
# Ears that keep listening once the input ends took the connection: a refusal comes back sooner.
LISTENED_S = 4.0
# Half a second of silence at the rate every plugin takes, to open the ears and close them.
RATE = 16_000
STAGE_NAMES: dict[Modality, str] = {"llm": "model", "stt": "ears", "tts": "voice"}
# The job a key is tried on, the first the vendor does: a model's answer is the cheapest to ask.
JOBS: tuple[Modality, ...] = ("llm", "tts", "stt")
# Once, at once: a setting is not worth livekit's retries, and a person is waiting on the answer.
ONCE = APIConnectOptions(max_retry=0, timeout=10.0)
SILENCE = rtc.AudioFrame(data=bytes(RATE), sample_rate=RATE, num_channels=1, samples_per_channel=RATE // 2)


async def try_stage(stage: Modality, running: Running, turn: Turn | None = None, *, what: str | None = None) -> None:
    """The stage asked one small thing; the vendor's no is ValidationError, its silence UpstreamError."""
    named = what or f"the {STAGE_NAMES[stage]} this sets"
    try:
        # Outside a call there is no job to lend the plugins its HTTP session: it is opened here.
        async with asyncio.timeout(TRY_S), http_context.open():
            if stage == "tts":
                await voices.sample(running, LINE)
            elif stage == "llm":
                await _answered(running)
            else:
                await _heard(stt_of(running, turn))
    except TimeoutError as slow:
        raise UpstreamError(_unanswered(running, named, f"no answer in {TRY_S:.0f} s")) from slow
    except (APIConnectionError, APITimeoutError) as silent:
        raise UpstreamError(_unanswered(running, named, silent.message)) from silent
    except APIError as refused:
        raise ValidationError(f"{running.vendor} refused {named}: {words_of(refused)}") from refused
    except ValidationError as said:
        # The voice's sample says its own refusal; here it is named after what was tried.
        cause = said.__cause__
        words = words_of(cause) if isinstance(cause, APIError) else str(said)
        raise ValidationError(f"{running.vendor} refused {named}: {words}") from said
    except UpstreamError as failed:
        cause = failed.__cause__
        if isinstance(cause, APIConnectionError | APITimeoutError):
            raise UpstreamError(_unanswered(running, named, cause.message)) from cause
        raise ValidationError(f"{running.vendor} refused {named}: {failed}") from failed


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
            await try_stage(stage, keyring.vendor_on(stage, vendor.name, credentials, catalog), what="this key")
        except (ValidationError, UpstreamError) as refused:
            first = first or refused
            continue
        return
    if first is not None:
        raise first


def _unanswered(running: Running, named: str, why: str) -> str:
    return f"{running.vendor} did not answer while {named} was tried: {why}; nothing was kept, try again"


# A realtime model opens its session with the call: built, its class and its arguments are tried,
# and a vendor's no to them is heard here; its key is the one the org already brought.
async def try_realtime(running: Running) -> None:
    """The realtime model built as a voice call builds it, and closed; refused in our words."""
    talking = build_realtime(running)
    await talking.aclose()


async def _answered(running: Running) -> None:
    model = llm_of(running)
    context = ChatContext.empty()
    context.add_message(role="user", content=LINE)
    try:
        async with model.chat(chat_ctx=context, conn_options=ONCE) as stream:
            async for _ in stream:
                break
    finally:
        await model.aclose()


# Ears that only take a whole utterance have nothing to open: they are tried by the first call.
# The turn's knobs are the call's, so a silence or a bar the vendor does not take is its no here.
async def _heard(ears: stt.STT[Never]) -> None:
    try:
        if not ears.capabilities.streaming:
            return
        async with ears.stream(conn_options=ONCE) as stream:
            stream.push_frame(SILENCE)
            stream.end_input()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(LISTENED_S):
                    async for _ in stream:
                        continue
    finally:
        await ears.aclose()
