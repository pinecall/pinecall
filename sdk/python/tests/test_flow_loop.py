"""The app's loop: an event to its handlers and the flows it starts, a run a stretch further."""

from pinecall import Heard, Step, flow, voice_app
from pinecall._app_work import AppDoor
from pinecall._flow_loop import Working, entry_heard, pass_heard, worked_once
from pinecall.wire._names import JsonObject
from pinecall.wire.frames import Entry
from tests.fakes.kept import KeptApp


def entry(type_: str, data: JsonObject, *, ephemeral: bool = False) -> Entry:
    return Entry(
        seq=4, ts=1.0, call="CA_1", agent="front-desk", type=type_, ephemeral=ephemeral, data=data
    )


def working_on(door: AppDoor, reported: list[str]) -> tuple[Working, list[JsonObject]]:
    heard: list[JsonObject] = []

    @flow("remind-visit")
    async def remind(visit: JsonObject, step: Step) -> None:
        await step.sleep("1h")
        heard.append(visit)

    def booked(_: Heard, data: JsonObject) -> None:
        heard.append(data)

    app = voice_app("brightside").on("visit.booked", booked).on("visit.booked", remind)
    return Working(app, door, lambda _: None, reported.append), heard


async def test_an_event_reaches_its_handler_starts_its_flow_once_and_is_heard(
    door: AppDoor, kept: KeptApp
) -> None:
    reported: list[str] = []
    working, heard = working_on(door, reported)
    sent = kept.send("visit.booked", {"id": 7})
    await worked_once(working, 0.1)
    assert heard == [{"id": 7}]
    assert [run["flow"] for run in kept.runs.values()] == ["remind-visit"]
    assert (kept.heard, reported) == ([sent], [])
    # The run started is ready: the next pass advances it to its sleep.
    await worked_once(working, 0.1)
    assert next(iter(kept.runs.values()))["status"] == "sleeping"


async def test_a_logged_line_starts_its_flow_by_its_own_name_and_a_passing_entry_none(
    door: AppDoor, kept: KeptApp
) -> None:
    working, _ = working_on(door, [])
    await entry_heard(working, entry("custom", {"name": "visit.booked", "data": {"id": 7}}))
    await entry_heard(
        working, entry("custom", {"name": "visit.booked", "data": {"id": 8}}, ephemeral=True)
    )
    assert [run["input"] for run in kept.runs.values()] == [{"id": 7}]


async def test_a_pass_heard_on_a_call_has_it_take_the_teammates_voice(
    door: AppDoor, kept: KeptApp
) -> None:
    reported: list[str] = []
    working, _ = working_on(door, reported)
    await pass_heard(
        working,
        entry("custom", {"name": "handoff", "data": {"from": "front-desk", "to": "billing"}}),
    )
    assert kept.asked == ['POST /v1/calls/CA_1/stages {"agent":"billing"}']
    kept.staged = 500
    await pass_heard(working, entry("custom", {"name": "handoff", "data": {"to": "billing"}}))
    assert reported == ["CA_1 keeps the voice it had after its pass to billing: 500"]
