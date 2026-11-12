"""What a verb prints: lines for a person, rows as a table, or everything as JSON for a script."""

import dataclasses
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TextIO, cast

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

type Column[T] = tuple[str, Callable[[T], object]]


class Printer:
    """One verb's output: human lines on stdout, or one JSON document when `--json` was asked."""

    def __init__(self, *, as_json: bool, out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> None:
        """Nothing printed yet."""
        self.as_json = as_json
        self.out = out
        self.err = err
        self.console = Console(file=out, highlight=False, soft_wrap=True)

    # A sentence for the person: under --json it goes to stderr, so stdout stays one document.
    def line(self, text: str = "") -> None:
        """One line."""
        (self.err if self.as_json else self.out).write(f"{text}\n")

    def lines(self, texts: Sequence[str]) -> None:
        """Several lines."""
        for text in texts:
            self.line(text)

    # The verb's answer when it has no table: a model, a dataclass, a mapping.
    def data(self, value: object) -> None:
        """The value as indented JSON, in either mode."""
        self.out.write(json.dumps(plain(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def rows[T](self, items: Sequence[T], columns: Sequence[Column[T]]) -> None:
        """The items as a table with a header; as a JSON list under --json."""
        if self.as_json:
            self.data(list(items))
            return
        table = Table(box=None, pad_edge=False, header_style="bold")
        for name, _ in columns:
            table.add_column(name)
        for item in items:
            table.add_row(*(cell(column(item)) for _, column in columns))
        self.console.print(table)

    def secret(self, value: str) -> None:
        """A value printed once and alone on stdout, so a shell can take it: a minted key."""
        self.out.write(f"{value}\n")

    def warn(self, text: str) -> None:
        """A line for the person on stderr, whatever the mode."""
        self.err.write(f"{text}\n")


def plain(value: object) -> Any:
    """The value as JSON-ready data: models and dataclasses dumped, sets sorted, dates as ISO."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(name): plain(item) for name, item in mapping.items()}
    if isinstance(value, list | tuple | frozenset | set):
        items = [plain(item) for item in cast(Iterable[object], value)]
        return sorted(items, key=str) if isinstance(value, frozenset | set) else items
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def cell(value: object) -> str:
    """A value as one cell of a table."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, list | tuple | frozenset | set):
        return ",".join(str(item) for item in cast(Iterable[object], value)) or "-"
    return str(value)


def when(at: float | None, *, seconds: bool = True) -> str:
    """An epoch as a UTC timestamp a person reads; a dash for none."""
    if at is None:
        return "-"
    shape = "%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d %H:%M"
    return datetime.fromtimestamp(at, UTC).strftime(shape)
