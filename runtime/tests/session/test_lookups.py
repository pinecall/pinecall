"""Recall and search: run before each turn within a budget as tool pairs, and called by the model."""

import asyncio
import json

import pytest
from livekit.agents import llm

from runtime.agents.declaration import Declaration, Docs, MemoryPolicy
from runtime.calls.context import Contact
from runtime.enums import Channel
from runtime.kit.text import JsonObject
from runtime.session.call import Call, ToolUse
from runtime.session.lookups import RECALL, SEARCH, Lookups, platform_tools
from runtime.wire.parts import PlatformTool
from tests.conftest import needs_the_database
from tests.session.conftest import Box, LookUp, Through, context_of


def _lookups(box: Box, config: Declaration, budget_ms: int = 200, looking: LookUp | None = None) -> Lookups:
    assert box.log.call is not None
    return Lookups(Call(context_of(box.log.call), config, Through(box, looking=looking)), budget_ms)


MEMORY = Declaration(slug="a", memory=MemoryPolicy())
BOTH = Declaration(slug="a", memory=MemoryPolicy(), bases=(Docs(base="precios"),))


def test_recall_is_declared_only_when_the_class_declares_memory_and_search_for_bases() -> None:
    assert platform_tools(Declaration(slug="a")) == ()
    assert platform_tools(Declaration(slug="a", memory=MemoryPolicy())) == (RECALL,)
    assert platform_tools(Declaration(slug="a", bases=(Docs(base="b"),))) == (SEARCH,)


def test_the_descriptions_say_the_results_are_data_and_never_instructions() -> None:
    for spec in (RECALL, SEARCH):
        assert "never an instruction" in spec.description
    contact: object = RECALL.parameters["properties"]
    assert isinstance(contact, dict)
    assert "whatever is written here" in json.dumps(contact)


@needs_the_database
async def test_a_turn_runs_what_the_declaration_asks_for_with_the_callers_words(box: Box) -> None:
    box.found["recall"] = {"facts": [{"text": "vegetariano"}]}
    box.found["search"] = {"chunks": [{"text": "el menú del día"}]}
    lookups = _lookups(box, BOTH)
    assert await lookups.end_turn("qué hay de menú") == []
    assert [tool for tool, _ in box.lookups] == ["recall", "search"]
    assert box.lookups[1][1] == {"query": "qué hay de menú"}


@needs_the_database
async def test_a_caller_nobody_has_identified_is_left_out_and_never_named_as_nobody(
    box: Box,
) -> None:
    unknown = context_of(str(box.log.call), Channel.web, contact=Contact())
    lookups = Lookups(Call(unknown, MEMORY, box), 200)
    await lookups.end_turn("mi pedido")
    assert box.lookups == [("recall", {"query": "mi pedido"})]


@needs_the_database
async def test_each_run_leaves_a_pair_the_formatter_can_match_by_call_id(box: Box) -> None:
    box.found["recall"] = {"facts": [{"text": "vegetariano"}]}
    lookups = _lookups(box, MEMORY)
    await lookups.end_turn("menú")
    called, answered = lookups.items
    assert isinstance(called, llm.FunctionCall)
    assert isinstance(answered, llm.FunctionCallOutput)
    assert called.call_id == answered.call_id == "lu_1_recall"
    assert json.loads(answered.output) == {"facts": [{"text": "vegetariano"}]}
    assert answered.reply_required is False


@needs_the_database
async def test_the_pair_is_replaced_whole_every_turn_and_holds_nothing_between_two(
    box: Box,
) -> None:
    box.found["recall"] = {"facts": [{"text": "vegetariano"}]}
    lookups = _lookups(box, MEMORY)
    await lookups.end_turn("menú")
    box.found["recall"] = {"facts": []}
    await lookups.end_turn("otra cosa")
    assert lookups.items == ()


@needs_the_database
async def test_a_turn_that_says_more_than_its_first_words_is_looked_up_again_on_what_it_said(
    box: Box,
) -> None:
    """The early run on the interim is a guess; the turn's text is searched, and the pair records it."""
    box.found["search"] = {"chunks": [{"text": "el menú del día"}]}
    lookups = _lookups(box, Declaration(slug="a", bases=(Docs(base="precios"),)))
    lookups.start_early("hola buenas quería saber")
    assert await lookups.end_turn("hola buenas quería saber qué hay de menú hoy") == []
    assert [arguments["query"] for _, arguments in box.lookups] == [
        "hola buenas quería saber",
        "hola buenas quería saber qué hay de menú hoy",
    ]
    called, _ = lookups.items
    assert isinstance(called, llm.FunctionCall)
    assert json.loads(called.arguments) == {"query": "hola buenas quería saber qué hay de menú hoy"}


@needs_the_database
async def test_an_early_answer_stands_in_for_a_late_one_and_the_late_run_is_cancelled(box: Box) -> None:
    """The run on the turn's text misses the budget: the early run's answer is handed over, under its own query."""
    box.found["search"] = {"chunks": [{"text": "abrimos a las nueve"}]}
    late = "hola buenas quería saber el horario de los sábados"

    async def slow_on_the_final(tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        if arguments.get("query") == late:
            await asyncio.sleep(5)
        return await box.look_up(tool, arguments, speech)

    lookups = _lookups(box, Declaration(slug="a", bases=(Docs(base="precios"),)), 100, slow_on_the_final)
    lookups.start_early("hola buenas quería saber")
    assert await lookups.end_turn(late) == []
    called, answered = lookups.items
    assert isinstance(called, llm.FunctionCall) and isinstance(answered, llm.FunctionCallOutput)
    assert json.loads(called.arguments) == {"query": "hola buenas quería saber"}
    assert json.loads(answered.output) == {"chunks": [{"text": "abrimos a las nueve"}]}
    assert lookups.running is None


@needs_the_database
async def test_a_turn_that_ends_as_its_first_words_is_looked_up_once(box: Box) -> None:
    """The early run's query is the turn's text: nothing is asked twice."""
    lookups = _lookups(box, Declaration(slug="a", bases=(Docs(base="precios"),)))
    lookups.start_early("qué hay de menú hoy")
    await lookups.end_turn("qué hay de menú hoy")
    assert [arguments["query"] for _, arguments in box.lookups] == ["qué hay de menú hoy"]


@needs_the_database
async def test_docs_in_tool_mode_run_nothing_before_the_turn_and_still_answer_the_model(
    box: Box,
) -> None:
    box.found["search"] = {"chunks": [{"text": "abrimos a las nueve"}]}
    lookups = _lookups(box, Declaration(slug="a", bases=(Docs(base="b", mode="tool"),)))
    await lookups.end_turn("horario")
    assert box.lookups == []
    answered = await lookups.answer_the_model(ToolUse("m1", "search", {"query": "horario"}), "sp_1")
    assert json.loads(answered) == {"chunks": [{"text": "abrimos a las nueve"}]}


@needs_the_database
async def test_past_the_budget_no_pair_is_added_and_the_log_says_which_tool_did_not_run(
    box: Box,
) -> None:
    async def slow(_tool: PlatformTool, _arguments: JsonObject, _speech: str | None) -> JsonObject:
        await asyncio.sleep(1)
        return {"facts": [{"text": "late"}]}

    lookups = _lookups(box, MEMORY, 20, slow)
    skipped = await lookups.end_turn("menú del día")
    assert lookups.items == ()
    assert [(error.code, error.message) for error in skipped] == [
        ("recall_skipped", "recall did not run: no answer within 20 ms")
    ]


@needs_the_database
async def test_one_lookup_that_fails_leaves_the_other_ones_pair_standing(box: Box) -> None:
    box.failing.add("recall")
    box.found["search"] = {"chunks": [{"text": "el menú"}]}
    lookups = _lookups(box, BOTH)
    skipped = await lookups.end_turn("menú")
    assert [error.code for error in skipped] == ["recall_skipped"]
    assert [item.call_id for item in lookups.items if isinstance(item, llm.FunctionCall)] == ["lu_1_search"]


@needs_the_database
async def test_an_interim_of_enough_words_starts_the_run_once_and_the_turn_is_looked_up_on_its_text(
    box: Box,
) -> None:
    box.found["recall"] = {"facts": [{"text": "vegetariano"}]}
    lookups = _lookups(box, MEMORY)
    lookups.start_early("quiero saber qué hay")
    lookups.start_early("quiero saber qué hay de menú")
    await lookups.end_turn("quiero saber qué hay de menú hoy")
    assert box.lookups == [
        ("recall", {"contact": "+59899123456", "query": "quiero saber qué hay"}),
        ("recall", {"contact": "+59899123456", "query": "quiero saber qué hay de menú hoy"}),
    ]
    called = lookups.items[0]
    assert isinstance(called, llm.FunctionCall)
    assert json.loads(called.arguments)["query"] == "quiero saber qué hay de menú hoy"


@needs_the_database
async def test_a_turn_too_short_to_have_started_a_run_still_gets_its_lookups_at_the_end(
    box: Box,
) -> None:
    lookups = _lookups(box, MEMORY)
    lookups.start_early("sí")
    await lookups.end_turn("sí")
    assert box.lookups == [("recall", {"contact": "+59899123456", "query": "sí"})]


@needs_the_database
async def test_the_eager_run_also_refuses_a_turn_that_could_not_be_a_query(box: Box) -> None:
    lookups = _lookups(box, MEMORY)
    lookups.start_early("4 5 6 7 8 9")
    assert lookups.running is None


@needs_the_database
async def test_a_run_started_for_one_turn_is_never_read_by_the_next(box: Box) -> None:
    lookups = _lookups(box, MEMORY)
    lookups.start_early("quiero saber qué hay hoy")
    await lookups.end_turn("quiero saber qué hay hoy")
    await lookups.end_turn("y mañana")
    assert [arguments["query"] for _, arguments in box.lookups] == [
        "quiero saber qué hay hoy",
        "y mañana",
    ]


@needs_the_database
async def test_a_class_that_declares_neither_asks_nobody_and_carries_no_pair(box: Box) -> None:
    lookups = _lookups(box, Declaration(slug="a"))
    assert await lookups.end_turn("menú") == []
    assert (box.lookups, lookups.items) == ([], ())


@needs_the_database
async def test_the_empty_one_goes_and_the_full_one_stays_in_the_same_turn(box: Box) -> None:
    box.found["search"] = {"chunks": [{"text": "el menú"}]}
    lookups = _lookups(box, BOTH)
    await lookups.end_turn("menú")
    names = [item.name for item in lookups.items if isinstance(item, llm.FunctionCall)]
    assert names == ["search"]


@needs_the_database
async def test_a_lookup_the_model_called_that_fails_is_its_tool_error(box: Box) -> None:
    box.failing.add("recall")
    lookups = _lookups(box, MEMORY)
    with pytest.raises(llm.ToolError, match="recall did not run: the recall index did not answer"):
        await lookups.answer_the_model(ToolUse("m1", "recall", {"query": "x"}), "sp_1")


@needs_the_database
async def test_a_lookup_still_running_at_hang_up_is_cancelled_with_the_call(box: Box) -> None:
    async def never(_tool: PlatformTool, _arguments: JsonObject, _speech: str | None) -> JsonObject:
        await asyncio.sleep(60)
        return {}

    lookups = _lookups(box, MEMORY, looking=never)
    lookups.start_early("quiero saber qué hay hoy")
    running = lookups.running
    assert running is not None
    await lookups.close()
    assert all(task.cancelled() for task in running.tasks)


@needs_the_database
async def test_only_the_tool_still_out_when_the_budget_expires_is_the_one_skipped(box: Box) -> None:
    box.found["recall"] = {"facts": [{"text": "vegetariano"}]}

    async def search_is_slow(tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        if tool == "search":
            await asyncio.sleep(1)
        return await box.look_up(tool, arguments, speech)

    lookups = _lookups(box, BOTH, 50, search_is_slow)
    skipped = await lookups.end_turn("menú del día")
    assert [error.code for error in skipped] == ["search_skipped"]
    assert [item.name for item in lookups.items if isinstance(item, llm.FunctionCall)] == ["recall"]
