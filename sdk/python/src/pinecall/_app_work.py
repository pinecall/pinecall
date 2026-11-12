"""A voice app's side of its flows: the events and runs the gateway keeps for it, over HTTP."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import quote

import httpx

from pinecall._endpoints import door_at, signed
from pinecall.client import detail_of
from pinecall.errors import PinecallError
from pinecall.wire._names import Env, JsonObject

StepKind = Literal["sleep", "call", "wait", "run", "emit"]


@dataclass(frozen=True)
class AppDoor:
    """The gateway, the key and the app the work is asked for."""

    url: str
    api_key: str
    env: Env | None
    app: str


@dataclass(frozen=True)
class JournalStep:
    """One step of a run's journal; `result` is what it came to once `over`."""

    seq: int
    kind: StepKind
    asked: JsonObject
    over: bool
    result: object


@dataclass(frozen=True)
class KeptRun:
    """A run as the gateway keeps it."""

    id: str
    flow: str
    input: JsonObject
    status: str
    steps: tuple[JournalStep, ...]


@dataclass(frozen=True)
class OwedEvent:
    """An event the app is owed."""

    id: int
    name: str
    data: JsonObject


@dataclass(frozen=True)
class Work:
    """What the app's process is owed now."""

    events: tuple[OwedEvent, ...]
    runs: tuple[KeptRun, ...]


async def _asked(
    door: AppDoor, method: str, path: str, body: object = None, wait_s: float | None = None
) -> object:
    url = door_at(door.url, f"/v1/apps/{quote(door.app, safe='')}{path}")
    timeout = 30.0 if wait_s is None else wait_s + 30.0
    async with httpx.AsyncClient(timeout=timeout) as http:
        answered = await http.request(
            method, url, json=body, headers=signed(door.api_key, door.env)
        )
    if answered.is_error:
        detail = detail_of(answered)
        raise PinecallError(
            f"{door.app}{path}: the gateway answered {answered.status_code}: {detail}"
        )
    return answered.json() if answered.content else None


def run_of(said: object) -> KeptRun:
    """A run from what the gateway wrote."""
    run = cast("JsonObject", said)
    steps = cast("list[JsonObject]", run.get("steps") or [])
    return KeptRun(
        id=str(run["id"]),
        flow=str(run["flow"]),
        input=cast("JsonObject", run.get("input") or {}),
        status=str(run["status"]),
        steps=tuple(
            JournalStep(
                seq=int(cast("int", step["seq"])),
                kind=cast("StepKind", step["kind"]),
                asked=cast("JsonObject", step.get("asked") or {}),
                over=bool(step.get("over")),
                result=step.get("result"),
            )
            for step in steps
        ),
    )


async def take_work(door: AppDoor, wait_s: float) -> Work:
    """What the app is owed, waited for up to `wait_s`: the gateway holds it for this process."""
    said = cast("JsonObject", await _asked(door, "POST", "/work", {"wait_s": wait_s}, wait_s))
    events = cast("list[JsonObject]", said.get("events") or [])
    runs = cast("list[object]", said.get("runs") or [])
    return Work(
        events=tuple(
            OwedEvent(
                int(cast("int", one["id"])),
                str(one["name"]),
                cast("JsonObject", one.get("data") or {}),
            )
            for one in events
        ),
        runs=tuple(run_of(one) for one in runs),
    )


async def event_heard(door: AppDoor, event: int) -> None:
    """The event was handled."""
    await _asked(door, "POST", f"/events/{event}/heard")


async def start_run(door: AppDoor, flow: str, key: str, given: Mapping[str, object]) -> KeptRun:
    """Start a flow with an input; the same key is the same run."""
    return run_of(
        await _asked(door, "POST", "/runs", {"flow": flow, "key": key, "input": dict(given)})
    )


async def write_step(door: AppDoor, run: str, step: Mapping[str, object]) -> KeptRun:
    """Write the run's next step, and read the run as it stands after it."""
    return run_of(await _asked(door, "POST", f"/runs/{quote(run, safe='')}/steps", dict(step)))


async def read_run(door: AppDoor, run: str) -> KeptRun:
    """One run with its journal."""
    return run_of(await _asked(door, "GET", f"/runs/{quote(run, safe='')}"))


async def runs_of(door: AppDoor, flow: str, status: str) -> list[KeptRun]:
    """The app's runs of one flow in one status, newest first."""
    path = f"/runs?flow={quote(flow, safe='')}&status={quote(status, safe='')}"
    said = cast("JsonObject", await _asked(door, "GET", path))
    return [run_of(one) for one in cast("list[object]", said.get("runs") or [])]


async def end_run(
    door: AppDoor, run: str, status: Literal["done", "failed"], error: str | None = None
) -> None:
    """The flow returned or raised."""
    body: JsonObject = {"status": status} if error is None else {"status": status, "error": error}
    await _asked(door, "POST", f"/runs/{quote(run, safe='')}/end", body)


async def cancel_run(door: AppDoor, run: str) -> None:
    """Stop a run where it stands."""
    await _asked(door, "POST", f"/runs/{quote(run, safe='')}/cancel")


async def staged_as(door: AppDoor, call: str, agent: str) -> int:
    """Have a live call run on `agent`'s model and voice from here on; the gateway's status."""
    url = door_at(door.url, f"/v1/calls/{quote(call, safe='')}/stages")
    async with httpx.AsyncClient(timeout=30.0) as http:
        answered = await http.post(
            url, json={"agent": agent}, headers=signed(door.api_key, door.env)
        )
    return answered.status_code
