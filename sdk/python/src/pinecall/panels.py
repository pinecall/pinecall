"""The console's panel beside a conversation: `@panel`, and the nodes a `Drawing` draws."""

import inspect
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal, TypeVar

from pinecall import _running
from pinecall.errors import DeclarationRefused

_F = TypeVar("_F", bound=Callable[..., object])

# Where `@panel` leaves its title on the method, for the class to read when it is created.
MARK = "__pinecall_panel__"

Tone = Literal["neutral", "good", "warn", "bad"]
TONES: tuple[Tone, ...] = ("neutral", "good", "warn", "bad")

# One node of the console's closed catalogue: the same JSON the TypeScript package's tags give.
Node = dict[str, object]


@dataclass(frozen=True)
class Who:
    """The conversation a panel is drawn for: the agent, the other party, the newest call."""

    agent: str
    contact: str
    call: str


@dataclass(frozen=True)
class Declared:
    """A class's panel: its title, and the method that draws it."""

    name: str
    method: str


def panel(name: str = "View") -> Callable[[_F], _F]:
    """Make a method the panel the console draws beside a conversation with this agent.

    ```python
    @panel("Ficha del cliente")
    def ficha(self, who: Who, draw: Drawing) -> None:
        cliente = self.crm.find(who.contact)
        with draw.panel(cliente.name), draw.rows():
            draw.row("Alta", cliente.since)
    ```

    A panel names a thread, not a live call: it is drawn for an ended call too, on an instance of
    its own, so it reads from your own systems and never from the state. One per class, and a
    subclass inherits none.

    Args:
        name: the panel's title in the console.
    """

    def marked(method: _F) -> _F:
        setattr(method, MARK, name)
        return method

    return marked


def panel_of(cls: type) -> Declared | None:
    """The panel the class itself declares, refused when it declares two or one that draws wrong."""
    found: list[Declared] = []
    for attribute, value in vars(cls).items():
        name: object = getattr(value, MARK, None)
        if not isinstance(name, str):
            continue
        if len(inspect.signature(value).parameters) != len(("self", "who", "draw")):
            raise DeclarationRefused(f"panel {attribute}: a panel draws with (self, who, draw)")
        found.append(Declared(name, attribute))
    if len(found) > 1:
        names = " and ".join(one.name for one in found)
        raise DeclarationRefused(
            f"{cls.__name__} declares two panels ({names}); a class draws one panel"
        )
    return found[0] if found else None


def drawn(cls: type, declared: Declared, who: Who) -> dict[str, object]:
    """Draw the class's panel for one conversation: `{name, nodes}`, what `view.render` answers."""
    drawing = Drawing()
    _running.finished(getattr(cls(), declared.method)(who, drawing))
    return {"name": declared.name, "nodes": drawing.nodes}


def said(value: object) -> str:
    """A value as the console shows it: nothing for None or a boolean; a whole number whole."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class Drawing:
    """What a panel draws on: one method per node of the console's catalogue."""

    def __init__(self) -> None:
        """Start with nothing drawn."""
        self.nodes: list[Node] = []

    @contextmanager
    def panel(self, title: object = None) -> Generator[None, None, None]:
        """A titled section: what is drawn inside the `with` is under it."""
        with self._inside() as children:
            yield
        self.nodes.append(
            {"tag": "panel", "title": None if title is None else said(title), "children": children}
        )

    @contextmanager
    def rows(self) -> Generator[None, None, None]:
        """A list of labelled rows: the `row`s drawn inside the `with`."""
        with self._inside() as children:
            yield
        self.nodes.append({"tag": "rows", "children": children})

    def row(self, label: object, value: object = None) -> None:
        """A labelled line: `row("Alta", "12 Mar 2024")`."""
        self.nodes.append({"tag": "row", "label": said(label), "value": said(value)})

    def stat(self, label: object, value: object) -> None:
        """A prominent labelled number."""
        self.nodes.append({"tag": "stat", "label": said(label), "value": said(value)})

    def table(self, columns: Sequence[object], rows: Sequence[object]) -> None:
        """A table; each row is a sequence in column order, or a mapping keyed by the columns."""
        named = [said(column) for column in columns]
        self.nodes.append(
            {"tag": "table", "columns": named, "rows": [cells(row, named) for row in rows]}
        )

    def badge(self, text: object, tone: str = "neutral") -> None:
        """A status badge: neutral, good, warn or bad; a tone it does not know is neutral."""
        self.nodes.append(
            {"tag": "badge", "tone": tone if tone in TONES else "neutral", "text": said(text)}
        )

    def text(self, line: object) -> None:
        """A line of text; an empty one draws nothing."""
        written = said(line).strip()
        if written:
            self.nodes.append({"tag": "text", "text": written})

    @contextmanager
    def _inside(self) -> Generator[list[Node], None, None]:
        outer, self.nodes = self.nodes, []
        children = self.nodes
        try:
            yield children
        finally:
            self.nodes = outer


def cells(row: object, columns: Sequence[str]) -> list[str]:
    """One row's cells, in the columns' order."""
    if isinstance(row, Mapping):
        keyed: Mapping[object, object] = row  # pyright: ignore[reportUnknownVariableType]
        return [said(keyed.get(column)) for column in columns]
    if isinstance(row, Sequence) and not isinstance(row, str):
        listed: Sequence[object] = row  # pyright: ignore[reportUnknownVariableType]
        return [said(cell) for cell in listed]
    return [said(row)]
