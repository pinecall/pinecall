"""Tests for a golden's turn held to its steps on livekit's own test run of the line."""

import time

import pinecall_runtime.session.text as text
from pinecall_runtime.agents.declaration import AgentConfig, ToolSpec
from pinecall_runtime.calls.context import new_call_id
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.store import Store
from pinecall_runtime.judging.schemas import JudgeScore
from pinecall_runtime.judging.service.turn_checks import TurnRun, turn_scores
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.goldens import Turn
from pinecall_runtime.wire.parts import EndedBy, ToolResult
from tests.conftest import needs_the_database
from tests.fakes.acme import AcmeLLM
from tests.judging.factories import answering
from tests.session.conftest import AGENT, Box, a_session

FIND = ToolSpec(
    "find_slots",
    "The free slots of a day.",
    {"type": "object", "properties": {"day": {"type": "string"}, "hour": {"type": "integer"}}},
)


CLINIC = AgentConfig(slug=AGENT, tools=(FIND,))


FOUND: list[Json] = [{"name": "find_slots", "arguments": {"day": "martes", "hour": 16}, "call_id": "t1"}]


# A reply step with nothing asked of its words: the agent's next message came.
ANY_REPLY: JsonObject = {"reply": {}}


async def scored(
    store: Store,
    call: str,
    then: list[Json],
    *replies: list[Json],
    judge: AcmeLLM | None = None,
    ended_by: EndedBy | None = None,
) -> dict[str, JudgeScore]:
    """The line run on a written session answering with the replies, held to these steps."""
    box = Box(Log(store, call, AGENT))
    box.answers["find_slots"] = ToolResult(call_id="t1", name="find_slots", output={"16:00": True})
    session = a_session(box, CLINIC, *replies, run="run_1")
    await session.start()
    began = time.time()
    run = await text.run_text(session, "¿Tienen algo el martes?")
    await text.end_text(session, "caller_hung_up", "caller")
    turn = Turn.model_validate({"say": "¿Tienen algo el martes?", "then": then})
    scores = await turn_scores(turn.then, 1, TurnRun(run, began, ended_by), judge)
    return {score.metric: score for score in scores}


@needs_the_database
async def test_a_tool_called_with_the_arguments_named_holds_whatever_else_it_carried(store: Store, call: str) -> None:
    steps: list[Json] = [{"tool": "find_slots", "args": {"day": "martes"}}, ANY_REPLY]
    scores = await scored(store, call, steps, FOUND, ["A las cuatro."])
    assert [(name, score.passed) for name, score in scores.items()] == [
        ("t1.tool:find_slots", True),
        ("t1.reply", True),
    ]


@needs_the_database
async def test_a_tool_called_with_another_value_breaks_and_names_what_it_was_given(store: Store, call: str) -> None:
    steps: list[Json] = [{"tool": "find_slots", "args": {"day": "jueves"}}]
    scores = await scored(store, call, steps, FOUND, ["A las cuatro."])
    broke = scores["t1.tool:find_slots"]
    assert not broke.passed
    assert "'day': 'martes'" in broke.reason


@needs_the_database
async def test_a_turn_that_called_no_tool_breaks_on_livekits_own_words(store: Store, call: str) -> None:
    scores = await scored(store, call, [{"tool": "find_slots"}], ["No tengo agenda."])
    assert not scores["t1.tool:find_slots"].passed


@needs_the_database
async def test_the_first_step_that_broke_ends_the_turn_and_the_rest_are_not_asked(store: Store, call: str) -> None:
    steps: list[Json] = [{"tool": "book"}, ANY_REPLY]
    scores = await scored(store, call, steps, FOUND, ["A las cuatro."])
    assert list(scores) == ["t1.tool:book"]
    assert "the next tool call is find_slots, not book" in scores["t1.tool:book"].reason


@needs_the_database
async def test_a_forbidden_tool_breaks_when_it_ran_and_holds_when_it_did_not(store: Store, call: str) -> None:
    ran = await scored(store, call, [{"no_tool": "find_slots"}], FOUND, ["A las cuatro."])
    kept = await scored(store, new_call_id(), [{"no_tool": "book"}], FOUND, ["A las cuatro."])
    assert not ran["t1.no_tool:find_slots"].passed
    assert kept["t1.no_tool:book"].passed


@needs_the_database
async def test_a_reply_is_read_for_its_phrases_by_code(store: Store, call: str) -> None:
    kept_to = await scored(store, call, [{"reply": {"says_any": ["cuatro", "16:00"]}}], ["A las cuatro."])
    broke = await scored(store, new_call_id(), [{"reply": {"says": ["16:00"]}}], ["A las cuatro."])
    assert kept_to["t1.reply"].passed
    assert "it never said '16:00'" in broke["t1.reply"].reason


@needs_the_database
async def test_an_intent_is_asked_of_livekits_judge_and_counted_as_one_judge_call(store: Store, call: str) -> None:
    judge = answering({"name": "check_intent", "arguments": {"success": True, "reason": "it offers four"}})
    steps: list[Json] = [{"reply": {"intent": "offers a slot on Tuesday"}}]
    scores = await scored(store, call, steps, ["A las cuatro."], judge=judge)
    assert scores["t1.intent"].passed
    assert scores["t1.intent"].judge_calls == 1
    assert len(judge.requests) == 1


@needs_the_database
async def test_an_intent_with_no_judge_model_breaks_rather_than_pass_unread(store: Store, call: str) -> None:
    steps: list[Json] = [{"reply": {"intent": "offers a slot"}}]
    scores = await scored(store, call, steps, ["A las cuatro."])
    assert not scores["t1.intent"].passed


@needs_the_database
async def test_nothing_else_breaks_when_the_turn_held_more_than_its_steps_named(store: Store, call: str) -> None:
    steps: list[Json] = [{"tool": "find_slots"}, {"nothing_else": True}]
    scores = await scored(store, call, steps, FOUND, ["A las cuatro."])
    assert not scores["t1.nothing_else"].passed


@needs_the_database
async def test_an_end_holds_on_the_side_that_ended_the_call_in_the_turn(store: Store, call: str) -> None:
    kept_to = await scored(store, call, [{"end": "agent"}], ["Adiós."], ended_by="agent")
    open_ = await scored(store, new_call_id(), [{"end": "agent"}], ["Adiós."])
    assert kept_to["t1.end"].passed
    assert open_["t1.end"].reason == "the call did not end in this turn"


@needs_the_database
async def test_the_same_step_twice_in_a_turn_is_numbered(store: Store, call: str) -> None:
    steps: list[Json] = [{"tool": "find_slots"}, ANY_REPLY, {"no_tool": "book"}, {"no_tool": "x"}]
    scores = await scored(store, call, steps, FOUND, ["A las cuatro."])
    assert list(scores) == [
        "t1.tool:find_slots",
        "t1.reply",
        "t1.no_tool:book",
        "t1.no_tool:x",
    ]


@needs_the_database
async def test_a_reply_reads_past_the_line_said_while_the_tool_ran(store: Store, call: str) -> None:
    announced: list[Json] = [
        {"name": "find_slots", "arguments": {"day": "martes", "say": "Miro la agenda."}, "call_id": "t1"}
    ]
    steps: list[Json] = [{"tool": "find_slots"}, {"reply": {"says": ["cuatro"]}}]
    scores = await scored(store, call, steps, announced, ["A las cuatro."])
    assert scores["t1.reply"].passed, scores["t1.reply"].reason


@needs_the_database
async def test_a_reply_reads_past_the_line_that_led_into_the_tool(store: Store, call: str) -> None:
    led: list[Json] = ["Ya te busco algo.", *FOUND]
    scores = await scored(store, call, [{"reply": {"says": ["cuatro"]}}], led, ["A las cuatro."])
    assert scores["t1.reply"].passed, scores["t1.reply"].reason


@needs_the_database
async def test_a_turn_whose_only_line_led_into_a_tool_has_no_reply(store: Store, call: str) -> None:
    led: list[Json] = ["Ya te busco algo.", *FOUND]
    scores = await scored(store, call, [ANY_REPLY], led)
    assert not scores["t1.reply"].passed
