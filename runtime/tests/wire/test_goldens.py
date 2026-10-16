"""The goldens: a call's log as the SDKs pin it, read entry by entry, and the state it folds to."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from pinecall_runtime.calls import service as calls
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import event_of

GOLDEN = Path(__file__).resolve().parent / "golden"
_ENTRIES: TypeAdapter[list[Entry]] = TypeAdapter(list[Entry])


def test_every_entry_of_the_golden_log_reads() -> None:
    """Each entry's data is the event its type names, as the wire declares it."""
    entries = _ENTRIES.validate_json((GOLDEN / "call-log.json").read_bytes())
    assert entries, "the golden log holds entries"
    for entry in entries:
        event_of(entry)


def test_the_golden_log_folds_to_its_state() -> None:
    """The reducer folds the golden log to the state the SDKs pinned."""
    entries = _ENTRIES.validate_json((GOLDEN / "call-log.json").read_bytes())
    expected = json.loads((GOLDEN / "call-log.state.json").read_text(encoding="utf-8"))
    # As it goes on the wire: by alias, the fields never set left out.
    assert calls.reduce(entries).dump() == expected
