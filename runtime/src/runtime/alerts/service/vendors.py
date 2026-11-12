"""A vendor that failed a call, read off the sealed log: which stage, whose key, and how many times."""

import re
from collections.abc import Sequence

from runtime.enums import Stage
from runtime.providers import service as providers
from runtime.wire.base import Entry
from runtime.wire.events import VendorFailed

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
        failed = _failure_in(call, entry, lent)
        if failed is not None:
            found.append(failed)
    if not found:
        return None
    first = next((failed for failed in found if failed.vendor), found[0])
    return first.model_copy(update={"errors": len(found)})


# The one reading of what an entry says of a vendor: an `error` names the plugin that failed in its
# message, and a `vendor.switched` away from a vendor that is not available is that vendor's failure.
# The gateway's counters read the same two entries as they are appended, and read them with this.
def vendor_of(entry: Entry) -> str | None:
    """The vendor an entry says failed, "" when an error names none; None when the entry says nothing of one."""
    if entry.type == ERROR:
        return providers.vendor_named_in(str(entry.data.get("message") or ""))
    if entry.type == SWITCHED and entry.data.get("available") is False:
        return str(entry.data.get("vendor") or "")
    return None


def _failure_in(call: str, entry: Entry, lent: Sequence[str]) -> VendorFailed | None:
    vendor = vendor_of(entry)
    if vendor is None:
        return None
    if entry.type == ERROR:
        code, message = str(entry.data.get("code") or ""), str(entry.data.get("message") or "")
        if code not in FAILED_CODES:
            return None
        placed = STAGE_IN.search(message)
        stage = None if placed is None else _stage_named(placed["stage"])
        if stage is None and code == TIMEOUT:
            stage = Stage.llm
        if stage is None:
            return None
        return _failure(call, stage, vendor, lent, model=None, code=code, message=_first_line(message))
    stage = _stage_named(str(entry.data.get("stage") or ""))
    if stage is None:
        return None
    serving = str(entry.data.get("serving") or "")
    return _failure(
        call,
        stage,
        vendor,
        lent,
        model=str(entry.data.get("model") or "") or None,
        code=SWITCHED,
        message=f"the stage switched to {serving}" if serving else "the stage switched away",
    )


# Read through the wire model, which takes the stage by its word: the three stages are `enums.Stage`
# here, and written out a second time nowhere.
def _failure(
    call: str, stage: Stage, vendor: str, lent: Sequence[str], *, model: str | None, code: str, message: str
) -> VendorFailed:
    return VendorFailed.model_validate(
        {
            "call": call,
            "stage": stage.value,
            "vendor": vendor,
            "model": model,
            "code": code,
            "message": message,
            "own_key": _own_key(vendor, lent),
            "errors": 1,
        }
    )


def _stage_named(text: str) -> Stage | None:
    return next((stage for stage in Stage if stage == text), None)


def _own_key(vendor: str, lent: Sequence[str]) -> bool:
    return bool(vendor) and vendor not in {item.split("/", 1)[0] for item in lent}


def _first_line(message: str) -> str:
    return message.split("\n", 1)[0][:SAID_AT_MOST]
