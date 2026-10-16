"""What the serve entry prints: an entry a line for the CLI, a line for a person, the drain."""

import json
import queue
import threading
from typing import TextIO

from pinecall.client import Client, Drained
from pinecall.wire.frames import Entry


def entry_line(entry: Entry) -> str:
    """One entry as the CLI reads it: `{type, agent, call, data}`, data as the gateway wrote it."""
    return json.dumps(
        {"type": entry.type, "agent": entry.agent, "call": entry.call, "data": entry.data},
        ensure_ascii=False,
    )


class Printer:
    """Lines written and flushed on a thread of their own, in the order they were given.

    A write to a pipe the reader has not emptied blocks; on the loop's thread it would stop the
    socket being read, and every entry after it would arrive seconds late.
    """

    def __init__(self, out: TextIO) -> None:
        """A printer to `out`, its thread started."""
        self._out = out
        self._lines: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._write, daemon=True)
        self._thread.start()

    def line(self, text: str) -> None:
        """Print one line, without waiting for it."""
        self._lines.put(text)

    def close(self, within_s: float = 5.0) -> None:
        """Print what is still waiting, then stop."""
        self._lines.put(None)
        self._thread.join(within_s)

    def _write(self) -> None:
        while (text := self._lines.get()) is not None:
            self._out.write(text + "\n")
            # A pipe's stdout is block-buffered: unflushed, the CLI waiting on a line sees it at
            # exit.
            self._out.flush()


def said(client: Client, out: TextIO, err: TextIO, *, events: bool) -> Printer:
    """Listen before connecting, so `agent.registered` is a pipe's first line; the printer used."""
    printer = Printer(out)

    def heard(entry: Entry) -> None:
        if events:
            printer.line(entry_line(entry))
        elif entry.type == "agent.registered":
            printer.line(f"{entry.agent}  · answering as {entry.data.get('app')}")

    def failed(error: Exception) -> None:
        err.write(f"{type(error).__name__}: {error}\n")
        err.flush()

    client.on_entries(heard)
    client.on_errors(failed)
    return printer


def drain_line(drained: Drained) -> str:
    """Where the calls went, and what became of the tools running: one line."""
    if drained.handed + drained.parked + drained.tools == 0:
        return "draining · no live calls"
    parts = ["draining"]
    if drained.handed:
        parts.append(f"{plural(drained.handed, 'live call')} handed over")
    if drained.parked:
        parts.append(f"{plural(drained.parked, 'live call')} kept for the next process")
    if drained.finished:
        parts.append(f"{plural(drained.finished, 'tool')} finished")
    if drained.tools > drained.finished:
        parts.append(f"{plural(drained.tools - drained.finished, 'tool')} cut")
    return " · ".join(parts)


def plural(count: int, noun: str) -> str:
    """`1 tool`, `2 tools`."""
    return f"{count} {noun}{'' if count == 1 else 's'}"
