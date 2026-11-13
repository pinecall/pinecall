"""A flow: its function run against the journal the gateway keeps, one stretch at a time."""

import pytest

from pinecall import Agent, Called, DeclarationRefused, Step, _config, flow
from pinecall._app_work import AppDoor
from pinecall.flows import FlowChanged, StepUnwritten, advance, cancelled, seconds_of, started
from pinecall.wire._names import JsonObject
from tests.fakes.kept import KeptApp


class Reminder(Agent):
    """You remind patients of their visit."""


def slug_of(agent: type) -> str | None:
    return "brightside-reminder" if agent is Reminder else None


def test_a_flow_is_a_name_and_an_async_function() -> None:
    with pytest.raises(DeclarationRefused, match="lowercase"):
        flow("Remind Visit")
    with pytest.raises(DeclarationRefused, match="an async def"):
        flow("remind-visit")(lambda visit, step: None)  # type: ignore[arg-type, return-value]


def test_a_length_of_time_is_a_number_and_its_unit() -> None:
    assert [seconds_of(one) for one in ("45s", "30m", "2h", "1d")] == [45, 1800, 7200, 86400]
    with pytest.raises(DeclarationRefused, match="no length of time"):
        seconds_of("soon")


async def test_a_flow_is_started_once_for_one_key(door: AppDoor, kept: KeptApp) -> None:
    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        del visit, step

    first = await started(door, remind, "visit-7", {"id": 7})
    again = await started(door, remind, "visit-7", {"id": 7})
    assert (again.id, len(kept.runs)) == (first.id, 1)


async def test_a_run_is_left_at_a_sleep_and_goes_on_from_it_once_woken(
    door: AppDoor, kept: KeptApp
) -> None:
    said: list[str] = []

    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        said.append("before")
        await step.sleep_until(str(visit["at"]), before="24h")
        said.append("after")

    run = await started(door, remind, "visit-7", {"at": "2026-11-14T09:30:00+00:00"})
    assert (await advance(door, remind, run, slug_of)).status == "parked"
    assert kept.runs[run.id]["status"] == "sleeping"
    assert kept.runs[run.id]["steps"][0]["asked"] == {"until": "2026-11-13T09:30:00+00:00"}  # type: ignore[index]
    kept.wake(run.id, None)
    woken = await started(door, remind, "visit-7", {})
    assert (await advance(door, remind, woken, slug_of)).status == "done"
    # Each stretch runs the function from its top: what is outside a step runs again.
    assert said == ["before", "before", "after"]


async def test_an_effect_runs_once_and_is_read_back_after(door: AppDoor, kept: KeptApp) -> None:
    sent: list[int] = []

    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        del visit
        await step.run(lambda: sent.append(1) or f"sms-{len(sent)}")
        await step.sleep("2h")

    run = await started(door, remind, "visit-7", {})
    await advance(door, remind, run, slug_of)
    kept.wake(run.id, None)
    await advance(door, remind, await started(door, remind, "visit-7", {}), slug_of)
    assert sent == [1]


async def test_a_call_step_dials_as_the_agents_slug_and_reads_how_it_ended(
    door: AppDoor, kept: KeptApp
) -> None:
    ended: list[Called] = []

    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        ended.append(await step.call(str(visit["phone"]), Reminder, instruction="Remind them."))

    kept.refuses = {"answered": False, "refused": "Forbidden", "message": "a stranger"}
    run = await started(door, remind, "visit-7", {"phone": "+59899000001"})
    assert (await advance(door, remind, run, slug_of)).status == "done"
    asked = kept.runs[run.id]["steps"][0]["asked"]  # type: ignore[index]
    assert asked == {
        "agent": "brightside-reminder",
        "to": "+59899000001",
        "instruction": "Remind them.",
    }
    assert ended == [Called(answered=False, refused="Forbidden", message="a stranger")]


async def test_a_call_step_takes_the_agent_by_its_slug_and_refuses_one_nobody_is_served_as(
    door: AppDoor, kept: KeptApp
) -> None:
    _config.keep_served("brightside-reminder", Reminder)

    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        await step.call(str(visit["phone"]), "brightside-reminder")

    @flow("remind-nobody")
    async def nobody(visit: JsonObject, step: Step) -> None:
        await step.call(str(visit["phone"]), "brightside-remainder")

    kept.refuses = {"answered": True}
    run = await started(door, remind, "visit-8", {"phone": "+59899000001"})
    assert (await advance(door, remind, run, slug_of)).status == "done"
    asked = kept.runs[run.id]["steps"][0]["asked"]  # type: ignore[index]
    assert asked == {"agent": "brightside-reminder", "to": "+59899000001"}
    lost = await started(door, nobody, "visit-9", {"phone": "+59899000001"})
    ended = await advance(door, nobody, lost, slug_of)
    assert (ended.status, ended.error) == (
        "failed",
        "DeclarationRefused: remind-nobody: brightside-remainder is no agent this process serves",
    )


async def test_a_flow_whose_code_changed_under_its_run_is_said_so(
    door: AppDoor, kept: KeptApp
) -> None:
    @flow("remind-visit")
    async def sleeps(visit: JsonObject, step: Step) -> None:
        del visit
        await step.sleep("1h")

    @flow("remind-visit")
    async def waits(visit: JsonObject, step: Step) -> None:
        del visit
        await step.wait_for("visit.confirmed", within="1h")

    run = await started(door, sleeps, "visit-7", {})
    await advance(door, sleeps, run, slug_of)
    kept.wake(run.id, None)
    outcome = await advance(door, waits, await started(door, sleeps, "visit-7", {}), slug_of)
    assert outcome.status == "failed"
    assert FlowChanged.__name__ in str(outcome.error)


async def test_a_step_the_gateway_could_not_write_leaves_the_run_as_it_was(
    door: AppDoor, kept: KeptApp
) -> None:
    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        del visit
        await step.sleep("1h")

    run = await started(door, remind, "visit-7", {})
    kept.down = "the database is away"
    with pytest.raises(StepUnwritten, match="the database is away"):
        await advance(door, remind, run, slug_of)
    assert kept.runs[run.id]["status"] == "ready"


async def test_an_event_cancels_the_waiting_runs_it_names(door: AppDoor, kept: KeptApp) -> None:
    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        del visit
        await step.sleep("1h")

    remind.cancel_on("visit.cancelled", lambda gone, visit: gone["id"] == visit["id"])
    seven = await started(door, remind, "visit-7", {"id": 7})
    eight = await started(door, remind, "visit-8", {"id": 8})
    for run in (seven, eight):
        await advance(door, remind, run, slug_of)
    assert await cancelled(door, remind, "visit.cancelled", {"id": 7}) == 1
    assert (kept.runs[seven.id]["status"], kept.runs[eight.id]["status"]) == (
        "cancelled",
        "sleeping",
    )
