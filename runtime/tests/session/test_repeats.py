"""Tests for a tool chain's rounds: a sentence said since the caller last spoke is never said again."""

from collections.abc import AsyncIterator

from livekit.agents import llm

from pinecall_runtime.session.repeats import Piece, SaidThisTurn, text_of, unrepeated

NOTED = "Let me note that down."


def calling(tool: str, words: str | None = None) -> llm.ChatChunk:
    call = llm.FunctionToolCall(name=tool, arguments="{}", call_id=f"call_{tool}")
    return llm.ChatChunk(id="c", delta=llm.ChoiceDelta(role="assistant", content=words, tool_calls=[call]))


async def pieces(*said: Piece) -> AsyncIterator[Piece]:
    for piece in said:
        yield piece


async def played(said: SaidThisTurn, *answer: Piece) -> list[Piece]:
    return [piece async for piece in unrepeated(pieces(*answer), said)]


def having_said(*lines: str) -> SaidThisTurn:
    said = SaidThisTurn()
    for line in lines:
        said.say(line)
    return said


async def test_the_line_a_second_round_opens_with_again_is_dropped_and_its_tool_still_called() -> None:
    answer = await played(having_said(NOTED), "Let me note ", "that down.", calling("who"))
    assert [text_of(piece) for piece in answer] == [""]
    assert isinstance(answer[0], llm.ChatChunk)
    assert answer[0].delta is not None
    assert answer[0].delta.tool_calls[0].name == "who"


async def test_a_line_said_again_in_the_same_piece_as_its_tool_call_loses_its_words_alone() -> None:
    answer = await played(having_said(NOTED), calling("propose", NOTED))
    assert [text_of(piece) for piece in answer] == [""]
    assert isinstance(answer[0], llm.ChatChunk)
    assert answer[0].delta is not None
    assert answer[0].delta.tool_calls[0].name == "propose"


async def test_a_line_said_again_is_dropped_whatever_its_case_and_spacing() -> None:
    assert await played(having_said(NOTED), "let me  note that down.") == []


async def test_the_reply_after_a_repeated_line_is_said_whole() -> None:
    answer = await played(having_said(NOTED), NOTED, " That is Tuesday at nine.")
    assert "".join(text_of(piece) for piece in answer) == " That is Tuesday at nine."


async def test_words_that_start_like_a_line_said_but_go_elsewhere_are_all_said() -> None:
    answer = await played(having_said(NOTED), "Let me ", "check the calendar.")
    assert "".join(text_of(piece) for piece in answer) == "Let me check the calendar."


async def test_a_turn_with_nothing_said_yet_passes_every_word() -> None:
    answer = await played(SaidThisTurn(), NOTED, calling("propose"))
    assert text_of(answer[0]) == NOTED


async def test_once_the_caller_speaks_a_line_may_be_said_again() -> None:
    said = having_said(NOTED)
    said.clear()
    answer = await played(said, NOTED)
    assert [text_of(piece) for piece in answer] == [NOTED]


async def test_each_sentence_of_what_was_said_is_kept_on_its_own() -> None:
    said = having_said("Sure. Let me note that down.")
    assert said.said(NOTED)
    assert said.said("sure.")
    assert not said.said("Sure. Let me")
