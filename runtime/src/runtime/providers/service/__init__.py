"""The providers' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import Keyring, keys_of, parse_lending, running_on
from runtime.providers.service.pipeline import build_pipeline, stage_on_its_key
from runtime.providers.service.plugins import (
    NOT_REALTIME,
    hears_and_speaks,
    is_installed,
    refuse_realtime_as_llm,
    vendor_doing,
)
from runtime.providers.service.readiness import Runnable, runnable_on
from runtime.providers.service.signatures import refuse_untaken_knobs
from runtime.providers.service.speech import TimedWord, speak
from runtime.providers.service.stages import thinking_outside_a_call
from runtime.providers.service.telemetry import Telemetry, telemetry_of
from runtime.providers.service.trials import try_realtime, try_stage

__all__ = [
    "NOT_REALTIME",
    "Keyring",
    "Runnable",
    "Telemetry",
    "TimedWord",
    "build_pipeline",
    "get_catalog",
    "hears_and_speaks",
    "is_installed",
    "keys_of",
    "parse_lending",
    "refuse_realtime_as_llm",
    "refuse_untaken_knobs",
    "runnable_on",
    "running_on",
    "speak",
    "stage_on_its_key",
    "telemetry_of",
    "thinking_outside_a_call",
    "try_realtime",
    "try_stage",
    "vendor_doing",
]
