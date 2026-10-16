"""Who is listening for what: by an event's type or to every one, a listener's failure reported."""

import asyncio
import inspect
from collections.abc import Callable
from typing import Generic, TypeVar

from pinecall.wire.frames import WireModel

_C = TypeVar("_C")

Listener = Callable[[WireModel, _C], object]
AnyListener = Callable[[str, WireModel, _C], object]


class Listeners(Generic[_C]):
    """The listeners of one agent, call or client; one that raises never stops the others."""

    def __init__(self, on_error: Callable[[Exception], None]) -> None:
        """Report what a listener raised to `on_error`."""
        self._on_error = on_error
        self._by_type: dict[str, list[Listener[_C]]] = {}
        self._any: list[AnyListener[_C]] = []
        self._running: set[asyncio.Task[object]] = set()

    def on(self, type_: str, listener: Listener[_C]) -> Callable[[], None]:
        """Listen for one type of event; the answer stops it."""
        listeners = self._by_type.setdefault(type_, [])
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    def on_any(self, listener: AnyListener[_C]) -> Callable[[], None]:
        """Listen for every event; the answer stops it."""
        self._any.append(listener)
        return lambda: self._any.remove(listener)

    def emit(self, type_: str, event: WireModel, context: _C) -> None:
        """Hand the event to its type's listeners, then to every-event ones."""
        for listener in list(self._by_type.get(type_, [])):
            self._run(lambda listener=listener: listener(event, context))
        for listener in list(self._any):
            self._run(lambda listener=listener: listener(type_, event, context))

    def _run(self, heard: Callable[[], object]) -> None:
        try:
            result = heard()
        except Exception as error:  # noqa: BLE001 - a listener's failure is reported, never raised
            self._on_error(error)
            return
        if inspect.iscoroutine(result):
            task: asyncio.Task[object] = asyncio.get_running_loop().create_task(result)
            self._running.add(task)
            task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[object]) -> None:
        self._running.discard(task)
        if (
            not task.cancelled()
            and (error := task.exception()) is not None
            and isinstance(error, Exception)
        ):
            self._on_error(error)
