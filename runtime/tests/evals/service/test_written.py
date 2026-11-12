"""Tests for a golden played turn by turn on a written call: what it writes, where it breaks, how it ends."""

import asyncio
import time

from runtime.agents.declaration import Declaration, Greeting
from runtime.calls.log.fanout import Fanout
from runtime.calls.log.log import Log
from runtime.calls.log.store import Store
from runtime.evals.service.turn_checks import TurnRun
from runtime.evals.service.written import AT_MOST_S, Played, drive, wait_until_quiet
from runtime.kit.text import Json
from runtime.wire.base import Entry
from runtime.wire.goldens import Golden
from tests.conftest import needs_the_database
from tests.session.conftest import AGENT, Box, a_session, model_of

A_TICK = Entry(seq=1, ts=1.0, call="c", agent=AGENT, type="user.state", ephemeral=True, data={})


FREED = Declaration(slug=AGENT, events={"slot_freed": frozenset({"app"})})


def a_golden(**written: object) -> Golden:
    return Golden.model_validate({"name": "reserva", "turns": [{"say": "hola"}], **written})


def test_a_golden_that_seeds_nothing_reads_as_seeding_nothing() -> None:
    assert a_golden().memory == []


async def test_a_log_that_stays_quiet_is_settled_at_once_and_a_busy_one_at_most_in_the_cap() -> None:
    fanout = Fanout()
    quiet = fanout.subscribe()
    began = time.monotonic()
    await wait_until_quiet(quiet, quiet_s=0.01)
    assert time.monotonic() - began < 0.5
    busy = fanout.subscribe()

    async def chatter() -> None:
        while True:
            fanout.publish(A_TICK)
            await asyncio.sleep(0.001)

    talking = asyncio.create_task(chatter())
    began = time.monotonic()
    await wait_until_quiet(busy, quiet_s=0.02)
    talking.cancel()
    assert AT_MOST_S <= time.monotonic() - began < AT_MOST_S + 0.5


async def test_a_log_that_ended_is_settled() -> None:
    fanout = Fanout()
    ended = fanout.subscribe()
    fanout.close()
    await wait_until_quiet(ended)


class Turns:
    """What each line's judging was handed, and whether it holds the turn it is asked of."""

    def __init__(self, breaks_at: int | None = None) -> None:
        """No turn judged yet; `breaks_at` is the turn it says broke."""
        self.breaks_at = breaks_at
        self.judged_turns: list[tuple[int, TurnRun]] = []

    async def judged(self, number: int, played: TurnRun) -> bool:
        """The line's run kept; held unless it is the one that breaks."""
        self.judged_turns.append((number, played))
        return number != self.breaks_at


async def played(
    store: Store, call: str, golden: Golden, declaration: Declaration, *replies: list[Json]
) -> tuple[Played, list[str]]:
    box = Box(Log(store, call, AGENT))
    session = a_session(box, declaration, *replies, run="run_1")
    heard = box.log.fanout.subscribe()
    result = await drive(session, golden, heard, Turns().judged, is_held=lambda: True)
    return result, [entry.type for entry in await store.whole_of(call)]


@needs_the_database
async def test_a_golden_run_writes_no_opening_turn_at_all(store: Store, call: str) -> None:
    greets = Declaration(slug=AGENT, greeting=Greeting(say="Clínica Norte, buenos días."))
    _, kinds = await played(store, call, a_golden(), greets, ["hola"])
    assert kinds.index("turn.user") < kinds.index("turn.agent")


# The state rides call.started to the app, which applies it: the runner declares none of its own.
@needs_the_database
async def test_a_golden_with_a_state_is_played_without_the_runner_declaring_one(store: Store, call: str) -> None:
    golden = a_golden(state={"stage": "book", "patient": {"id": "p-1"}})
    _, kinds = await played(store, call, golden, FREED, ["hola"])
    assert "state.changed" not in kinds


@needs_the_database
async def test_a_golden_with_an_event_turn_injects_it_between_the_lines_around_it(store: Store, call: str) -> None:
    golden = a_golden(
        turns=[
            {"say": "hola"},
            {"event": {"name": "slot_freed", "data": {"at": "10:15"}}},
            {"say": "¿hay algo antes?"},
        ]
    )
    result, kinds = await played(store, call, golden, FREED, ["Buenos días."], ["Se liberó a las 10:15."])
    callers = [index for index, kind in enumerate(kinds) if kind == "turn.user"]
    answers = [index for index, kind in enumerate(kinds) if kind == "turn.agent"]
    assert answers[0] < kinds.index("event.received") < callers[1]
    assert result.held
    assert len(result.requests) == 2


@needs_the_database
async def test_a_golden_whose_event_the_agent_never_declared_breaks_at_that_turn_and_ends(
    store: Store, call: str
) -> None:
    golden = a_golden(turns=[{"event": {"name": "meteorite"}}])
    result, kinds = await played(store, call, golden, FREED, ["hola"])
    assert (result.held, result.broke_at) == (True, 1)
    assert result.unplayed is not None and result.unplayed.metric == "t1.event"
    assert "meteorite" in result.unplayed.reason
    ended = [entry for entry in await store.whole_of(call) if entry.type == "call.ended"]
    assert [entry.data["reason"] for entry in ended] == ["error"]
    assert "turn.user" not in kinds


@needs_the_database
async def test_a_golden_whose_app_let_go_ends_as_app_detached_and_not_on_a_timeout(store: Store, call: str) -> None:
    box = Box(Log(store, call, AGENT))
    session = a_session(box, FREED, ["hola"], run="run_1")
    heard = box.log.fanout.subscribe()
    result = await drive(session, a_golden(), heard, Turns().judged, is_held=lambda: False)
    assert not result.held
    ended = [entry for entry in await store.whole_of(call) if entry.type == "call.ended"]
    assert [(entry.data["reason"], entry.data["ended_by"]) for entry in ended] == [("app_detached", "platform")]


@needs_the_database
async def test_a_golden_played_to_its_end_is_a_caller_who_hung_up(store: Store, call: str) -> None:
    _, kinds = await played(store, call, a_golden(), FREED, ["hola"])
    entries = await store.whole_of(call)
    assert kinds[-1] == "call.score"
    ended = next(entry for entry in entries if entry.type == "call.ended")
    assert (ended.data["reason"], ended.data["ended_by"]) == ("caller_hung_up", "caller")


@needs_the_database
async def test_each_line_is_judged_on_its_own_run_and_an_event_turn_is_not_judged(store: Store, call: str) -> None:
    turns = Turns()
    box = Box(Log(store, call, AGENT))
    session = a_session(box, FREED, ["Buenos días."], ["A las diez."], run="run_1")
    golden = a_golden(turns=[{"say": "hola"}, {"event": {"name": "slot_freed"}}, {"say": "¿a qué hora?"}])
    result = await drive(session, golden, box.log.fanout.subscribe(), turns.judged, is_held=lambda: True)
    assert result.broke_at is None
    assert [number for number, _ in turns.judged_turns] == [1, 3]
    messages = [
        [event.item.text_content for event in played.run.events if event.type == "message"]
        for _, played in turns.judged_turns
    ]
    assert messages == [["Buenos días."], ["A las diez."]]


@needs_the_database
async def test_a_turn_that_broke_ends_the_golden_there_and_plays_no_line_after_it(store: Store, call: str) -> None:
    box = Box(Log(store, call, AGENT))
    session = a_session(box, FREED, ["Buenos días."], ["A las diez."], run="run_1")
    golden = a_golden(turns=[{"say": "hola"}, {"say": "¿a qué hora?"}])
    heard = box.log.fanout.subscribe()
    result = await drive(session, golden, heard, Turns(breaks_at=1).judged, is_held=lambda: True)
    assert (result.held, result.broke_at) == (True, 1)
    lines = [entry.data["text"] for entry in await store.whole_of(call) if entry.type == "turn.user"]
    assert lines == ["hola"]


@needs_the_database
async def test_a_turn_the_vendor_refused_breaks_the_golden_there_says_why_and_ends_its_call(
    store: Store, call: str
) -> None:
    box = Box(Log(store, call, AGENT))
    session = a_session(box, FREED, ["Buenos días."], run="run_1")
    model_of(session).refusal = "blocked"
    golden = a_golden(turns=[{"say": "hola"}, {"say": "¿a qué hora?"}])
    result = await drive(session, golden, box.log.fanout.subscribe(), Turns().judged, is_held=lambda: True)
    assert (result.held, result.broke_at) == (True, 1)
    assert result.unplayed is not None and result.unplayed.metric == "t1.model"
    assert "PROHIBITED_CONTENT" in result.unplayed.reason
    entries = await store.whole_of(call)
    assert [entry.data["text"] for entry in entries if entry.type == "turn.user"] == ["hola"]
    ended = [entry for entry in entries if entry.type == "call.ended"]
    assert [(entry.data["reason"], entry.data["ended_by"]) for entry in ended] == [("error", "platform")]


@needs_the_database
async def test_an_event_the_agent_never_declared_breaks_the_golden_there_says_why_and_ends_its_call(
    store: Store, call: str
) -> None:
    box = Box(Log(store, call, AGENT))
    session = a_session(box, FREED, ["Buenos días."], ["A las diez."], run="run_1")
    golden = a_golden(turns=[{"say": "hola"}, {"event": {"name": "nobody_declared"}}, {"say": "¿a qué hora?"}])
    result = await drive(session, golden, box.log.fanout.subscribe(), Turns().judged, is_held=lambda: True)
    assert (result.held, result.broke_at) == (True, 2)
    assert result.unplayed is not None and result.unplayed.metric == "t2.event"
    assert "nobody_declared" in result.unplayed.reason
    entries = await store.whole_of(call)
    assert [entry.data["text"] for entry in entries if entry.type == "turn.user"] == ["hola"]
    ended = [entry for entry in entries if entry.type == "call.ended"]
    assert [(entry.data["reason"], entry.data["ended_by"]) for entry in ended] == [("error", "platform")]
