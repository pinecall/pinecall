"""The loop a voice app keeps with the gateway: its events heard, its flows' runs advanced."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from pinecall import _app_work
from pinecall._app_work import AppDoor
from pinecall._handoff import PASSED
from pinecall.app import VoiceApp
from pinecall.errors import PinecallError
from pinecall.flows import advance, cancelled, started
from pinecall.wire._names import JsonObject
from pinecall.wire.frames import Entry

WAITS_S = 20.0
"""How long one ask for work waits at the gateway."""

RESTS_S = 5.0
"""How long the loop rests after a gateway that did not answer."""

# A written call has no worker to tell (404), and one that ended has none either (409).
NOTHING_TO_RESTAGE = (202, 404, 409)


@dataclass(frozen=True)
class Working:
    """What the loop needs: the app, the gateway, each class's slug, and where a failure is said."""

    app: VoiceApp
    door: AppDoor
    slug_of: Callable[[type], str | None]
    report: Callable[[str], None]


async def flows_heard(working: Working, name: str, data: JsonObject, key: str) -> None:
    """An entry of that name starts each flow `app.on` gave it, once by `key`, and cancels runs."""
    for one in working.app.started_by(name):
        try:
            await started(working.door, one, key, data)
        except (PinecallError, httpx.HTTPError) as failed:
            working.report(f"{one.name} was not started by {name}: {failed}")
    for one in working.app.flows():
        try:
            await cancelled(working.door, one, name, data)
        except (PinecallError, httpx.HTTPError) as failed:
            working.report(f"{one.name} was not cancelled by {name}: {failed}")


async def entry_heard(working: Working, entry: Entry) -> None:
    """The same for an entry of a call's log; one that is not kept starts nothing."""
    if entry.ephemeral:
        return
    name, data = working.app.named(entry.type, entry.data)
    await flows_heard(working, name, data, f"{entry.call or entry.agent}:{entry.seq}")


async def pass_heard(working: Working, entry: Entry) -> None:
    """A call passed to a teammate takes that agent's model and voice from the gateway."""
    name, data = working.app.named(entry.type, entry.data)
    to = data.get("to")
    if name != PASSED or entry.call is None or not isinstance(to, str):
        return
    try:
        status = await _app_work.staged_as(working.door, entry.call, to)
    except httpx.HTTPError as failed:
        working.report(f"{entry.call} keeps the voice it had after its pass to {to}: {failed}")
        return
    if status not in NOTHING_TO_RESTAGE:
        working.report(f"{entry.call} keeps the voice it had after its pass to {to}: {status}")


async def worked_once(working: Working, wait_s: float) -> None:
    """Take what the app is owed once: each event to its handlers and flows, each run a stretch."""
    app, door, report = working.app, working.door, working.report
    owed = await _app_work.take_work(door, wait_s)
    for event in owed.events:
        await app.heard(
            event.name, None, "", event.data,
            lambda name, error: report(f"the handler of {name} raised: {error}"),
        )  # fmt: skip
        await flows_heard(working, event.name, event.data, f"event:{event.id}")
        await _app_work.event_heard(door, event.id)
    known = {one.name: one for one in app.flows()}

    async def stretched(run: _app_work.KeptRun) -> None:
        flow = known.get(run.flow)
        # Another release of the app may know the flow: the run is left for it.
        if flow is None:
            report(f"run {run.id} is of the flow {run.flow}, which this app does not have")
            return
        try:
            ended = await advance(door, flow, run, working.slug_of)
        except (PinecallError, httpx.HTTPError) as failed:
            report(f"{run.flow} {run.id}: {failed}")
            return
        if ended.status == "failed":
            report(f"{run.flow} {run.id} failed: {ended.error}")

    await asyncio.gather(*(stretched(run) for run in owed.runs))


async def work(working: Working) -> None:
    """Keep taking work until cancelled; a gateway away is one line per outage."""
    said = False
    while True:
        try:
            await worked_once(working, WAITS_S)
            said = False
        except (PinecallError, httpx.HTTPError) as failed:
            if not said:
                working.report(f"flows: {failed}")
            said = True
            await asyncio.sleep(RESTS_S)
