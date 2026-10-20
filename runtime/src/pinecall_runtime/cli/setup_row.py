"""The providers row `setup` writes: local stages on the openai plugin with a base_url, vendors bare, all priced."""

import json
from importlib.resources import files
from typing import Any

from pinecall_runtime.cli.setup_models import (
    LOCAL_LLM,
    LOCAL_STT,
    LOCAL_TTS,
    TURN_MODELS,
    Choices,
    is_local,
    model_of,
    vendor_of,
)
from pinecall_runtime.providers import service as providers

# The stages that answer with a model all run on the same plugin and server when local.
THINKING = "llm/openai"


def row_of(choices: Choices) -> providers.Catalog:
    """The providers row for the choices: each stage's default, the tuning, the judge, the caller, the rates."""
    shipped = _shipped(choices)
    # The list prices the package ships, so a call on a vendor's key is priced from the first; open models at nothing.
    rates: dict[str, Any] = {model: rate.model_dump(exclude_none=True) for model, rate in list_prices().items()}
    rates.update(shipped["rates"])
    for model in choices.local_models:
        rates.setdefault(model, dict(shipped["rates"][_llm_model(choices)]))
    row: dict[str, object] = {"rates": rates, "embedding": shipped["embedding"]}
    defaults: dict[str, dict[str, str]] = {}
    tuning: dict[str, dict[str, object]] = {}
    for stage, choice in (("stt", choices.stt), ("llm", choices.llm), ("tts", choices.tts)):
        if is_local(choice):
            defaults[stage] = dict(shipped["defaults"][stage])
            tuning[f"{stage}/openai"] = dict(shipped["tuning"][f"{stage}/openai"])
        else:
            defaults[stage] = _vendors(choice)
    judge, caller = _thinker(choices.judging), _thinker(choices.calling)
    if THINKING not in tuning and any(is_local(choice) for choice in (choices.judging, choices.calling)):
        tuning[THINKING] = dict(shipped["tuning"][THINKING])
    turn_model = TURN_MODELS[choices.turn]
    stt_key = f"stt/{'openai' if is_local(choices.stt) else vendor_of(choices.stt)}"
    turned = {k: v for k, v in tuning.get(stt_key, {}).items() if k != "turn_model"}
    if turn_model is not None:
        turned["turn_model"] = turn_model
    if turned:
        tuning[stt_key] = turned
    elif stt_key in tuning:
        del tuning[stt_key]
    row.update(
        defaults=defaults,
        tuning=tuning,
        voices=shipped["voices"] if is_local(choices.tts) else {},
        judge={"llm": judge, "ceiling_usd": shipped["judge"]["ceiling_usd"]},
        caller={"llm": caller, "ceiling_usd": shipped["caller"]["ceiling_usd"]},
    )
    return providers.Catalog.model_validate(row)


def list_prices() -> dict[str, providers.Rate]:
    """The vendors' list prices the package ships (`local/prices.csv`), by model."""
    text = files("pinecall_runtime.cli").joinpath("local", "prices.csv").read_text(encoding="utf-8")
    return providers.rates_from_csv(text)


# The shipped row names the thinking and the ears by placeholders: the choices' own models go in.
def _shipped(choices: Choices) -> dict[str, Any]:
    text = files("pinecall_runtime.cli").joinpath("local", "providers.local.json").read_text(encoding="utf-8")
    stt = (model_of(choices.stt) or LOCAL_STT) if is_local(choices.stt) else LOCAL_STT
    shipped: dict[str, Any] = json.loads(text.replace("LOCAL_LLM", _llm_model(choices)).replace("LOCAL_STT", stt))
    shipped["defaults"]["tts"] = {"vendor": "openai", "model": LOCAL_TTS}
    return shipped


def _llm_model(choices: Choices) -> str:
    return (model_of(choices.llm) or LOCAL_LLM) if is_local(choices.llm) else LOCAL_LLM


def _thinker(choice: str) -> dict[str, str]:
    if is_local(choice):
        return {"vendor": "openai", "model": model_of(choice) or LOCAL_LLM}
    return _vendors(choice)


def _vendors(choice: str) -> dict[str, str]:
    model = model_of(choice)
    return {"vendor": vendor_of(choice), **({"model": model} if model else {})}
