"""A tool that stops to ask: its call is answered with the question, and it goes on when given."""

import asyncio
import concurrent.futures
import inspect
import typing
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TypeVar

from pinecall._answers import Answer
from pinecall.errors import DeclarationRefused, PinecallError, ToolFailed
from pinecall.tasks import Task, asking_for, given_with, giving_tool, tasks_of
from pinecall.wire.parts import ToolSpec

_T = TypeVar("_T")

NOT_IN_A_TOOL = "ask is for inside a tool: the tool's call is what the question is answered on"


@dataclass
class Frame:
    """One tool call running: its name, its function, and the question it may stop at."""

    tool: str
    loop: asyncio.AbstractEventLoop
    stopped: asyncio.Future[str]
    running: asyncio.Future[object] | None = None


@dataclass
class Waiting:
    """The task one tool waits for, and where its answer is given."""

    task: Task[object]
    frame: Frame
    answer: concurrent.futures.Future[object] = field(
        default_factory=concurrent.futures.Future[object]
    )


@dataclass(frozen=True)
class Asked:
    """What a tool stopped to ask for, for a screen that draws it as a form."""

    task: str
    asks: str
    fields: Mapping[str, str]
    refused: str | None = None


FRAME: ContextVar[Frame | None] = ContextVar("pinecall_tool_frame", default=None)


def tasks_on(cls: type, team: Sequence[type] = ()) -> list[Task[object]]:
    """The tasks a call may ask for: its class's, and with a team every member's, once each."""
    found: list[Task[object]] = []
    for one in team or [cls]:
        found += [asked for asked in tasks_of(one) if asked not in found]
    return found


def giving_tools(tasks: Sequence[Task[object]], taken: Sequence[str]) -> list[ToolSpec]:
    """The tools a set of tasks is given with; a name an agent's own tool has is refused."""
    for asked in tasks:
        if given_with(asked) in taken:
            raise DeclarationRefused(
                f"the task {asked.name} is given with {given_with(asked)},"
                " and an agent declares a tool of that name"
            )
    return [giving_tool(asked) for asked in tasks]


class Asking:
    """The asking of one call: one tool waits for one task at a time."""

    def __init__(self, tasks: Sequence[Task[object]]) -> None:
        """The tasks this call may ask for."""
        self.tasks = list(tasks)
        self._waiting: Waiting | None = None
        self._refused: str | None = None

    @property
    def open(self) -> ToolSpec | None:
        """The one tool open while something is asked for."""
        return None if self._waiting is None else giving_tool(self._waiting.task)

    @property
    def asked(self) -> Asked | None:
        """What is asked for now."""
        waiting = self._waiting
        if waiting is None:
            return None
        task = waiting.task
        return Asked(task.name, task.asks, dict(task.fields), self._refused)

    def gives(self, tool: str) -> bool:
        """Whether a tool of that name gives one of the call's tasks."""
        return any(given_with(asked) == tool for asked in self.tasks)

    async def run(self, name: str, tool: Callable[[], Awaitable[object]]) -> object:
        """Run the tool: what it returned, or the question it stopped at."""
        loop = asyncio.get_running_loop()
        frame = Frame(name, loop, loop.create_future())
        token = FRAME.set(frame)
        try:
            frame.running = asyncio.ensure_future(tool())
        finally:
            FRAME.reset(token)
        return await _first(frame.running, frame.stopped)

    def ask(self, asked: Task[_T]) -> Answer[_T]:
        """Ask for a task from inside a tool: `await` it, or `.result()` it on a thread."""
        future: concurrent.futures.Future[object] = concurrent.futures.Future()
        frame = FRAME.get()
        if frame is None:
            future.set_exception(PinecallError(NOT_IN_A_TOOL))
        elif asked not in self.tasks:
            future.set_exception(
                PinecallError(f"{asked.name} is not a task of this agent: name it in tasks")
            )
        elif self._waiting is not None:
            future.set_exception(
                PinecallError(f"{self._waiting.task.name} is being asked for: one at a time")
            )
        else:
            self._waiting = Waiting(asked, frame, future)
            question = asking_for(asked)
            frame.loop.call_soon_threadsafe(lambda: _settle(frame.stopped, question))
        # The check of `asked` is what settles it, so what comes back is its `_T`.
        return typing.cast("Answer[_T]", Answer(future))

    async def given(self, tool: str, arguments: Mapping[str, object]) -> object:
        """The model gave the answer: the tool goes on, and this call says how it ended."""
        waiting = self._waiting
        if waiting is None or given_with(waiting.task) != tool:
            raise ToolFailed(f"{tool}: nothing is being asked for with it now")
        missing = [name for name in waiting.task.fields if not isinstance(arguments.get(name), str)]
        if missing:
            raise ToolFailed(f"{tool}: {', '.join(missing)} must be given, in words")
        try:
            value = waiting.task.check({name: str(arguments[name]) for name in waiting.task.fields})
            if inspect.isawaitable(value):
                value = await value
        except Exception as refused:
            raise ToolFailed(str(refused)) from refused
        self._waiting, self._refused = None, None
        frame = waiting.frame
        frame.stopped = frame.loop.create_future()
        waiting.answer.set_result(value)
        running = frame.running
        if running is None:
            raise ToolFailed(f"{tool}: the tool that asked is not running")
        finished = asyncio.ensure_future(_named(frame.tool, running))
        return await _first(finished, frame.stopped)

    async def given_by_page(self, task: object, given: object) -> str | None:
        """The caller's page gave the answer: what the model is to be told, or None."""
        waiting = self._waiting
        if waiting is None or waiting.task.name != task or not isinstance(given, Mapping):
            return None
        try:
            ended = await self.given(given_with(waiting.task), given)  # pyright: ignore[reportUnknownArgumentType]
        except ToolFailed as refused:
            self._refused = str(refused)
            return None
        what = waiting.task.asks
        if isinstance(ended, str):
            return f"The caller gave {what} on their screen. {ended}"
        result = typing.cast("dict[str, object]", ended).get("result")
        return (
            f"The caller gave {what} on their screen, and {waiting.frame.tool} is done with this"
            f" result: {result!r}. Tell them how it went."
        )

    def abandon(self) -> None:
        """The call ended with a question open: the tool that asked is told."""
        waiting, self._waiting = self._waiting, None
        running = None if waiting is None else waiting.frame.running
        if running is not None:
            # The tool's call was answered already: nobody is left to read what it raises now.
            running.add_done_callback(lambda done: done.cancelled() or done.exception())
        if waiting is not None and not waiting.answer.done():
            gone = f"the call ended before the caller gave {waiting.task.asks}"
            waiting.answer.set_exception(PinecallError(gone))


async def _named(tool: str, running: asyncio.Future[object]) -> object:
    # Said as the first tool's result, by its name: read bare, the model calls that tool again.
    return {"finished": tool, "result": await running}


async def _first(running: asyncio.Future[object], stopped: asyncio.Future[str]) -> object:
    done, _ = await asyncio.wait({running, stopped}, return_when=asyncio.FIRST_COMPLETED)
    return running.result() if running in done else stopped.result()


def _settle(future: asyncio.Future[str], question: str) -> None:
    if not future.done():
        future.set_result(question)
