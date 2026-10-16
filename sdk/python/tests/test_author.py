"""Who is writing: per task, restored on the way out, and never seen by a task running beside it."""

import asyncio

from pinecall._author import current, writing_as


def test_outside_every_tool_and_hook_nobody_is_writing() -> None:
    assert current() is None


def test_the_author_is_the_blocks_and_the_one_before_comes_back_after_it() -> None:
    with writing_as("outer"):
        with writing_as("inner"):
            assert current() == "inner"
        assert current() == "outer"
    assert current() is None


def test_two_tasks_writing_at_once_never_read_each_others_author() -> None:
    async def as_(name: str) -> tuple[str, str | None]:
        with writing_as(name):
            await asyncio.sleep(0.01)
            return name, current()

    async def both() -> list[tuple[str, str | None]]:
        return list(await asyncio.gather(as_("one"), as_("two")))

    assert asyncio.run(both()) == [("one", "one"), ("two", "two")]


def test_a_thread_started_from_the_loop_writes_as_the_task_that_started_it() -> None:
    async def from_a_thread() -> str | None:
        with writing_as("book"):
            return await asyncio.to_thread(current)

    assert asyncio.run(from_a_thread()) == "book"
