"""What a call's usage cost in US dollars, from the rates of the providers row."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Never

from livekit.agents import llm

from runtime.providers.catalog import Catalog, Rate
from runtime.wire.metrics import LLMModelUsage, ModelUsage, STTModelUsage, TTSModelUsage
from runtime.wire.parts import PLATFORM, Cost, CostRow, UnpricedRow

type Unit = Literal["input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens"]

A_MILLION = 1_000_000
A_MINUTE_S = 60
# The box's own compute, priced by the operator as `pinecall,pinecall-compute,minutes,<usd>` in
# the prices file: a call's seconds on the worker, every one counted, never minutes begun. With no
# such row nothing is priced and nothing is listed: a box that never priced itself is not unpriced.
COMPUTE = "pinecall-compute"


@dataclass(frozen=True, slots=True)
class PhoneLeg:
    """A phone leg as it is priced: whose carrier, which way, the number, how long."""

    carrier: str
    direction: str
    number: str
    seconds: float

    @property
    def name(self) -> str:
        """`twilio-inbound`: how the rates name a leg."""
        return f"{self.carrier}-{self.direction}"


def cost_of(
    usage: Iterable[ModelUsage], catalog: Catalog, *, legs: Sequence[PhoneLeg] = (), seconds: float = 0.0
) -> Cost:
    """Price every usage row, phone leg and the call's seconds of compute; no rate is unpriced."""
    rows: list[CostRow] = []
    unpriced: list[UnpricedRow] = []
    for used in usage:
        priced = _price(used, catalog)
        if priced is None:
            unpriced.append(UnpricedRow(provider=used.provider, model=used.model))
        else:
            rows += priced
    for leg in legs:
        billed = _leg_row(leg, catalog)
        if billed is None:
            unpriced.append(UnpricedRow(provider=leg.carrier, model=leg.name))
        elif billed.quantity > 0:
            rows.append(billed)
    compute = _compute_row(seconds, catalog)
    if compute is not None:
        rows.append(compute)
    return Cost(usd=round(sum(row.usd for row in rows), 6), rows=rows, unpriced=unpriced)


# A model the runtime asks itself, outside a call's session: livekit meters none of it.
def completion_usage(model: llm.LLM[Never], used: llm.CompletionUsage | None) -> LLMModelUsage | None:
    """What one answer of a model cost in tokens, as the call's usage writes it."""
    if used is None:
        return None
    # Frames drop unset fields, so the discriminator is set here or the SDKs reject the entry.
    return LLMModelUsage(
        type="llm_usage",
        provider=model.provider,
        model=model.model,
        input_tokens=used.prompt_tokens,
        input_cached_tokens=used.prompt_cached_tokens,
        input_cache_creation_tokens=used.cache_creation_tokens,
        output_tokens=used.completion_tokens,
    )


# Interruption and end-of-turn models run inside livekit and cost nothing: no row, not unpriced.
def _price(used: ModelUsage, catalog: Catalog) -> list[CostRow] | None:
    rate = catalog.rate_for(used.model)
    match used:
        case LLMModelUsage():
            return None if rate is None or rate.input is None else _tokens(used, rate)
        case TTSModelUsage():
            # A voice is priced as its vendor bills it: by the character read, by the second of audio
            # it made (Gemini's, whose price is per audio token), or by the tokens its plugin counts,
            # text in and audio out (OpenAI's).
            if rate is not None and rate.characters is None and rate.audio_seconds is not None:
                return _count(used, "audio_seconds", quantity=used.audio_duration or 0.0, per=rate.audio_seconds)
            if rate is not None and rate.characters is None and rate.output is not None:
                return _spoken_tokens(used, rate)
            return _count(
                used, "characters", quantity=used.characters_count or 0, per=None if rate is None else rate.characters
            )
        case STTModelUsage():
            return _count(
                used,
                "audio_seconds",
                quantity=used.audio_duration or 0.0,
                per=None if rate is None else rate.audio_seconds,
            )
        case _:
            return []


# Plugins count cached and cache-written tokens inside input_tokens, so both come off the
# fresh input before it is priced.
def _tokens(used: LLMModelUsage, rate: Rate) -> list[CostRow]:
    cached = used.input_cached_tokens or 0
    written = used.input_cache_creation_tokens or 0
    counted: list[tuple[Unit, int, float | None]] = [
        ("input_tokens", max((used.input_tokens or 0) - cached - written, 0), rate.input),
        ("cached_input_tokens", cached, rate.input if rate.cached_input is None else rate.cached_input),
        ("cache_creation_tokens", written, rate.cache_creation),
        ("output_tokens", used.output_tokens or 0, rate.output),
    ]
    return [
        _row(used, unit, quantity=tokens, per=per, usd=tokens / A_MILLION * per)
        for unit, tokens, per in counted
        if tokens > 0 and per is not None
    ]


def _spoken_tokens(used: TTSModelUsage, rate: Rate) -> list[CostRow]:
    counted: list[tuple[Unit, int, float | None]] = [
        ("input_tokens", used.input_tokens or 0, rate.input),
        ("output_tokens", used.output_tokens or 0, rate.output),
    ]
    return [
        _row(used, unit, quantity=tokens, per=per, usd=tokens / A_MILLION * per)
        for unit, tokens, per in counted
        if tokens > 0 and per is not None
    ]


def _count(
    used: TTSModelUsage | STTModelUsage,
    unit: Literal["characters", "audio_seconds"],
    *,
    quantity: float,
    per: float | None,
) -> list[CostRow] | None:
    if per is None:
        return None
    if quantity <= 0:
        return []
    return [_row(used, unit, quantity=quantity, per=per, usd=quantity * per)]


# A token row carries its price per million tokens, as a pricing page prints it.
def _row(
    used: ModelUsage, unit: Unit | Literal["characters", "audio_seconds"], *, quantity: float, per: float, usd: float
) -> CostRow:
    return CostRow(
        provider=used.provider, model=used.model, unit=unit, quantity=quantity, unit_price_usd=per, usd=round(usd, 6)
    )


# The row names the prefix the leg's number matched, never the number.
def _leg_row(leg: PhoneLeg, catalog: Catalog) -> CostRow | None:
    key = catalog.leg_rate_key_for(leg.name, leg.number)
    per = None if key is None else catalog.rates[key].minutes
    if key is None or per is None:
        return None
    minutes = math.ceil(leg.seconds / A_MINUTE_S) if leg.seconds > 0 else 0
    return CostRow(
        provider=leg.carrier,
        model=key,
        unit="minutes",
        quantity=minutes,
        unit_price_usd=per,
        usd=round(minutes * per, 6),
    )


def _compute_row(seconds: float, catalog: Catalog) -> CostRow | None:
    rate = catalog.rates.get(COMPUTE)
    if seconds <= 0 or rate is None or rate.minutes is None:
        return None
    minutes = round(seconds / A_MINUTE_S, 4)
    return CostRow(
        provider=PLATFORM,
        model=COMPUTE,
        unit="minutes",
        quantity=minutes,
        unit_price_usd=rate.minutes,
        usd=round(minutes * rate.minutes, 6),
    )
