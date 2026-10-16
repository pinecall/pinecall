"""An answer still coming: settled by its entry or its ceiling, awaited or waited on a thread."""

import asyncio

from pinecall._answers import Waiting


async def test_an_answer_is_settled_by_the_entry_and_every_one_waiting_gets_it() -> None:
    waiting: Waiting[str] = Waiting(asyncio.get_running_loop())
    first, second = waiting.answer(5, "lapsed"), waiting.answer(5, "lapsed")
    waiting.settle("landed")
    assert (await first, await second) == ("landed", "landed")


async def test_an_answer_nothing_settled_is_its_lapsed_value_at_its_ceiling() -> None:
    waiting: Waiting[str] = Waiting(asyncio.get_running_loop())
    assert await waiting.answer(0.02, "lapsed") == "lapsed"


async def test_an_answer_asked_for_on_a_thread_is_waited_for_there() -> None:
    waiting: Waiting[str] = Waiting(asyncio.get_running_loop())
    answered = asyncio.ensure_future(
        asyncio.to_thread(lambda: waiting.answer(2, "lapsed").result(2))
    )
    await asyncio.sleep(0.05)
    waiting.settle("landed")
    assert await answered == "landed"


def test_with_no_loop_only_an_entry_settles_an_answer() -> None:
    waiting: Waiting[str] = Waiting(None)
    answer = waiting.answer(0.01, "lapsed")
    assert not answer.done()
    waiting.settle("landed")
    assert answer.result(0) == "landed"
