"""The app's doors at the gateway: what it is owed, its runs and steps, and a call's new stages."""

from pinecall import _app_work
from pinecall._app_work import AppDoor
from tests.fakes.kept import KeptApp


async def test_the_app_is_owed_its_events_and_its_ready_runs_until_it_hears_them(
    door: AppDoor, kept: KeptApp
) -> None:
    sent = kept.send("visit.booked", {"id": 7})
    run = await _app_work.start_run(door, "remind-visit", "visit-7", {"id": 7})
    owed = await _app_work.take_work(door, 0.1)
    assert [(event.id, event.name, event.data) for event in owed.events] == [
        (sent, "visit.booked", {"id": 7})
    ]
    assert [one.id for one in owed.runs] == [run.id]
    await _app_work.event_heard(door, sent)
    assert (await _app_work.take_work(door, 0.1)).events == ()


async def test_a_step_written_is_read_back_in_the_runs_journal(door: AppDoor) -> None:
    run = await _app_work.start_run(door, "remind-visit", "visit-7", {})
    after = await _app_work.write_step(
        door, run.id, {"seq": 1, "kind": "sleep", "asked": {"until": "x"}}
    )
    assert after.status == "sleeping"
    read = await _app_work.read_run(door, run.id)
    assert [(step.seq, step.kind, step.over) for step in read.steps] == [(1, "sleep", False)]
    assert [one.id for one in await _app_work.runs_of(door, "remind-visit", "sleeping")] == [run.id]
    await _app_work.cancel_run(door, run.id)
    assert (await _app_work.read_run(door, run.id)).status == "cancelled"


async def test_a_call_is_told_to_take_another_agents_stages_and_the_status_is_said(
    door: AppDoor, kept: KeptApp
) -> None:
    kept.staged = 409
    assert await _app_work.staged_as(door, "CA_1", "billing") == 409
    assert kept.asked == ['POST /v1/calls/CA_1/stages {"agent":"billing"}']
