"""A flow: a function that outlives a call; it runs here, and the gateway keeps its journal."""

import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, TypeVar, cast

import httpx

from pinecall import _app_work
from pinecall._app_work import AppDoor, KeptRun, StepKind
from pinecall.errors import DeclarationRefused, PinecallError
from pinecall.wire._names import JsonObject

_T = TypeVar("_T")

A_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
A_WHILE = re.compile(r"^(\d+)(s|m|h|d)$")
SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
# What a run still waiting is in: the ones an event may cancel.
WAITING = ("ready", "sleeping", "waiting", "calling")

Body = Callable[[JsonObject, "Step"], Awaitable[object]]
"""The body of a flow: `async def`, of what started it and its steps."""


class StepUnwritten(PinecallError):
    """A step could not be written: the run stays as it was, and the gateway hands it out again."""


class FlowChanged(PinecallError):
    """The function asked for another step than its journal holds there: its code changed."""


class _Parked(Exception):
    pass


@dataclass(frozen=True)
class Called:
    """What a call a flow placed came to; `refused` names why nothing rang."""

    answered: bool
    reason: str | None = None
    call: str | None = None
    refused: str | None = None
    message: str | None = None


@dataclass
class Flow:
    """A flow by its name, which is how the gateway knows its runs."""

    name: str
    body: Body
    cancels: list[tuple[str, Callable[[JsonObject, JsonObject], bool]]] = field(
        default_factory=list[tuple[str, Callable[[JsonObject, JsonObject], bool]]]
    )

    def cancel_on(self, event: str, when: Callable[[JsonObject, JsonObject], bool]) -> "Flow":
        """Cancel the runs still waiting when an event says so.

        ```python
        remind.cancel_on("visit.cancelled", lambda gone, visit: gone["id"] == visit["id"])
        ```
        """
        self.cancels.append((event, when))
        return self


def flow(name: str) -> Callable[[Body], Flow]:
    """Name a flow, once.

    ```python
    @flow("remind-visit")
    async def remind_visit(visit, step):
        await step.sleep_until(visit["at"], before="24h")
        await step.call(visit["phone"], Reminders, instruction="Remind them of their visit.")
    ```

    Args:
        name: lowercase letters, digits and dashes: its runs are kept by it.
    """
    if not A_NAME.match(name):
        raise DeclarationRefused(
            "a flow's name is lowercase letters, digits and dashes: its runs are kept by it"
        )

    def named(body: Body) -> Flow:
        if not inspect.iscoroutinefunction(body):
            raise DeclarationRefused(
                f"{name}: a flow is an async def of what started it and its steps"
            )
        return Flow(name, body)

    return named


def seconds_of(how_long: str) -> int:
    """Seconds in `"2h"`, `"30m"`, `"45s"`, `"1d"`."""
    found = A_WHILE.match(how_long.strip())
    if found is None:
        raise DeclarationRefused(
            f'"{how_long}" is no length of time: a number and s, m, h or d, like 2h'
        )
    return int(found[1]) * SECONDS[found[2]]


async def started(door: AppDoor, of: Flow, key: str, given: Mapping[str, object]) -> KeptRun:
    """Start a run of the flow; the same key is the same run."""
    return await _app_work.start_run(door, of.name, key, given)


async def cancelled(door: AppDoor, of: Flow, event: str, data: JsonObject) -> int:
    """Cancel the flow's waiting runs an event names; how many."""
    asking = [when for named, when in of.cancels if named == event]
    if not asking:
        return 0
    stopped = 0
    for status in WAITING:
        for run in await _app_work.runs_of(door, of.name, status):
            if any(when(data, run.input) for when in asking):
                await _app_work.cancel_run(door, run.id)
                stopped += 1
    return stopped


@dataclass(frozen=True)
class Advanced:
    """Where a stretch of a run left it; a failed one says what its function raised."""

    status: Literal["parked", "done", "failed"]
    error: str | None = None


SlugOf = Callable[[type], str | None]


class Step:
    """The steps of a flow. Each is written to the run's journal and read back on the next run."""

    def __init__(self, door: AppDoor, of: Flow, run: KeptRun, slug_of: SlugOf) -> None:
        """The steps of one run, against its journal."""
        self._door, self._of, self._run, self._slug_of = door, of, run, slug_of
        self._journal = {step.seq: step for step in run.steps}
        self._seq = 0

    async def sleep(self, how_long: str) -> None:
        """Sleep for a while: `"2h"`, `"30m"`, `"45s"`, `"1d"`."""
        until = datetime.now(UTC) + timedelta(seconds=seconds_of(how_long))
        await self._waited("sleep", {"until": until.isoformat()})

    async def sleep_until(self, at: datetime | str, *, before: str | None = None) -> None:
        """Sleep until a time, or until `before` it: `step.sleep_until(visit_at, before="24h")`."""
        moment = at if isinstance(at, datetime) else datetime.fromisoformat(at)
        if moment.tzinfo is None:
            raise DeclarationRefused(f"{self._of.name}: sleep_until takes a time with its zone")
        until = moment - timedelta(seconds=0 if before is None else seconds_of(before))
        await self._waited("sleep", {"until": until.astimezone(UTC).isoformat()})

    async def call(  # noqa: PLR0913 - each is a part of what the call opens with
        self,
        to: str,
        agent: type,
        *,
        state: JsonObject | None = None,
        metadata: JsonObject | None = None,
        greeting: str | None = None,
        instruction: str | None = None,
        from_: str | None = None,
    ) -> Called:
        """Have an agent call a number, and wait for how the call ended."""
        slug = self._slug_of(agent)
        if slug is None:
            raise DeclarationRefused(
                f"{self._of.name}: {agent.__name__} is no agent this process serves"
            )
        opening = {"state": state, "metadata": metadata, "greeting": greeting,
                   "instruction": instruction, "from": from_}  # fmt: skip
        asked: JsonObject = {
            "agent": slug,
            "to": to,
            **{k: v for k, v in opening.items() if v is not None},
        }
        said = cast("JsonObject", await self._waited("call", asked) or {})
        known = {name: said.get(name) for name in ("reason", "call", "refused", "message")}
        return Called(answered=bool(said.get("answered")), **cast("dict[str, str | None]", known))

    async def wait_for(
        self, event: str, *, match: JsonObject | None = None, within: str | None = None
    ) -> JsonObject | None:
        """Wait for an event of the app whose data has what `match` names; None when it gave up."""
        asked: JsonObject = {"event": event}
        if match is not None:
            asked["match"] = match
        if within is not None:
            until = datetime.now(UTC) + timedelta(seconds=seconds_of(within))
            asked["until"] = until.isoformat()
        return cast("JsonObject | None", await self._waited("wait", asked))

    async def run(self, effect: Callable[[], _T | Awaitable[_T]]) -> _T:
        """Run something once: what it returned is kept, and read back instead of run again."""
        before = self._written("run")
        if before is not None:
            return cast("_T", before.result)
        result = effect()
        if inspect.isawaitable(result):
            result = await result
        await self._kept(
            _app_work.write_step(
                self._door, self._run.id, {"seq": self._seq, "kind": "run", "result": result}
            )
        )
        return cast("_T", result)

    async def emit(self, name: str, data: JsonObject | None = None) -> None:
        """Send an event to the app."""
        if self._written("emit") is None:
            step: JsonObject = {
                "seq": self._seq,
                "kind": "emit",
                "asked": {"name": name, "data": data or {}},
            }
            await self._kept(_app_work.write_step(self._door, self._run.id, step))

    def _written(self, kind: StepKind) -> _app_work.JournalStep | None:
        self._seq += 1
        before = self._journal.get(self._seq)
        if before is not None and before.kind != kind:
            raise FlowChanged(
                f"{self._of.name}: step {self._seq} was a {before.kind} and is now a {kind}:"
                f" the flow's code changed under run {self._run.id}"
            )
        return before

    async def _waited(self, kind: StepKind, asked: JsonObject) -> object:
        before = self._written(kind)
        if before is not None and before.over:
            return before.result
        if before is not None:
            raise _Parked
        step: JsonObject = {"seq": self._seq, "kind": kind, "asked": asked}
        after = await self._kept(_app_work.write_step(self._door, self._run.id, step))
        if after.status != "ready":
            raise _Parked
        read = await self._kept(_app_work.read_run(self._door, self._run.id))
        return next((one.result for one in read.steps if one.seq == self._seq), None)

    @staticmethod
    async def _kept(writing: Awaitable[KeptRun]) -> KeptRun:
        # A gateway that did not answer is no failure of the flow: the run is not ended over it.
        try:
            return await writing
        except (PinecallError, OSError, httpx.HTTPError) as failed:
            raise StepUnwritten(str(failed)) from failed


async def advance(door: AppDoor, of: Flow, run: KeptRun, slug_of: SlugOf) -> Advanced:
    """Run the flow's function against its journal, one stretch; end the run when it returns."""
    try:
        await of.body(run.input, Step(door, of, run, slug_of))
    except _Parked:
        return Advanced("parked")
    except StepUnwritten:
        raise
    except Exception as thrown:  # noqa: BLE001 - a flow that raises ends its run, never the process
        error = f"{type(thrown).__name__}: {thrown}"
        await _app_work.end_run(door, run.id, "failed", error)
        return Advanced("failed", error)
    await _app_work.end_run(door, run.id, "done")
    return Advanced("done")
