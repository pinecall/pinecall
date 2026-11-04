"""A vendor that failed a call, read off the sealed log: which stage, whose key, and how many times."""

import re
from collections.abc import Sequence
from typing import Literal

from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import VendorFailed

type Stage = Literal["llm", "stt", "tts"]
STAGES: tuple[Stage, ...] = ("llm", "stt", "tts")

# The error codes a worker writes when a vendor's component failed, or the model said nothing in time.
FAILED_CODES = frozenset({"component_failed", "component_dead_end", "llm_timeout"})
# A component's error names its plugin and its stage: `livekit.plugins.google.llm.LLM`.
STAGE_IN = re.compile(r"plugins\.\w+\.(?P<stage>llm|stt|tts)\b")
# The one error a message cannot place: a model that said nothing within the deadline is the LLM's.
TIMEOUT = "llm_timeout"
SWITCHED = "vendor.switched"
ERROR = "error"
# The alert carries the first line of the error, and no more than this of it.
SAID_AT_MOST = 300


def failure_of(call: str, entries: Sequence[Entry], *, lent: Sequence[str]) -> VendorFailed | None:
    """The vendor failure the log holds, or None: the first error naming a vendor, counted with the rest."""
    found: list[VendorFailed] = []
    for entry in entries:
        if entry.call != call:
            continue
        failed = _failed(call, entry, lent)
        if failed is not None:
            found.append(failed)
    if not found:
        return None
    first = next((failed for failed in found if failed.vendor), found[0])
    return first.model_copy(update={"errors": len(found)})


def _failed(call: str, entry: Entry, lent: Sequence[str]) -> VendorFailed | None:
    if entry.type == ERROR:
        code, message = str(entry.data.get("code") or ""), str(entry.data.get("message") or "")
        if code not in FAILED_CODES:
            return None
        vendor = providers.vendor_named_in(message)
        placed = STAGE_IN.search(message)
        stage = None if placed is None else _stage_named(placed["stage"])
        if stage is None and code == TIMEOUT:
            stage = "llm"
        if stage is None:
            return None
        return VendorFailed(
            call=call,
            stage=stage,
            vendor=vendor,
            model=None,
            code=code,
            message=_first_line(message),
            own_key=_own_key(vendor, lent),
            errors=1,
        )
    if entry.type == SWITCHED and entry.data.get("available") is False:
        vendor, stage = str(entry.data.get("vendor") or ""), _stage_named(str(entry.data.get("stage") or ""))
        if stage is None:
            return None
        serving = str(entry.data.get("serving") or "")
        return VendorFailed(
            call=call,
            stage=stage,
            vendor=vendor,
            model=str(entry.data.get("model") or "") or None,
            code=SWITCHED,
            message=f"the stage switched to {serving}" if serving else "the stage switched away",
            own_key=_own_key(vendor, lent),
            errors=1,
        )
    return None


def _stage_named(text: str) -> Stage | None:
    return next((stage for stage in STAGES if stage == text), None)


def _own_key(vendor: str, lent: Sequence[str]) -> bool:
    return bool(vendor) and vendor not in {item.split("/", 1)[0] for item in lent}


def _first_line(message: str) -> str:
    return message.split("\n", 1)[0][:SAID_AT_MOST]
