"""The providers' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.providers.service.catalog import get_catalog, judge_ceiling
from runtime.providers.service.credentials import box_credentials, put_box_credentials
from runtime.providers.service.health import VendorHealth
from runtime.providers.service.keyring import Keyring, keys_of, parse_lending, running_on
from runtime.providers.service.pipeline import build_pipeline, refuse_what_cannot_run, stage_on_its_key, thinking_of
from runtime.providers.service.plugins import (
    NOT_REALTIME,
    hears_and_speaks,
    is_installed,
    refuse_realtime_as_llm,
    vendor_doing,
)
from runtime.providers.service.prices import completion_usage, cost_of
from runtime.providers.service.questions import Answerer, Line, Patience, ask, open_answerer
from runtime.providers.service.readiness import Runnable, runnable_on
from runtime.providers.service.refusals import sentence_of, vendor_named_in
from runtime.providers.service.signatures import default_voice, refuse_untaken_settings
from runtime.providers.service.speech import TimedWord, speak
from runtime.providers.service.stages import (
    build_ears,
    build_realtime,
    build_thinking,
    build_voice,
    thinking_outside_a_call,
    voice_outside_a_call,
)
from runtime.providers.service.telemetry import Telemetry, telemetry_of
from runtime.providers.service.trials import try_realtime, try_stage
from runtime.providers.service.voices import list_by_vendor, list_in_catalog

__all__ = [
    "NOT_REALTIME",
    "Answerer",
    "Keyring",
    "Line",
    "Patience",
    "Runnable",
    "Telemetry",
    "TimedWord",
    "VendorHealth",
    "ask",
    "box_credentials",
    "build_ears",
    "build_pipeline",
    "build_realtime",
    "build_thinking",
    "build_voice",
    "completion_usage",
    "cost_of",
    "default_voice",
    "get_catalog",
    "hears_and_speaks",
    "is_installed",
    "judge_ceiling",
    "keys_of",
    "list_by_vendor",
    "list_in_catalog",
    "open_answerer",
    "parse_lending",
    "put_box_credentials",
    "refuse_realtime_as_llm",
    "refuse_untaken_settings",
    "refuse_what_cannot_run",
    "runnable_on",
    "running_on",
    "sentence_of",
    "speak",
    "stage_on_its_key",
    "telemetry_of",
    "thinking_of",
    "thinking_outside_a_call",
    "try_realtime",
    "try_stage",
    "vendor_doing",
    "vendor_named_in",
    "voice_outside_a_call",
]
