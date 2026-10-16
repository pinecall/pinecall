"""Running a method under its author, from no loop or from one, a `def` or an `async def`."""

import asyncio
import threading
from typing import cast

from pinecall._author import current
from pinecall._running import called, run


def who(**_: object) -> tuple[str | None, str]:
    return current(), threading.current_thread().name


async def who_async(**_: object) -> tuple[str | None, str]:
    return current(), threading.current_thread().name


def test_with_no_loop_a_def_runs_here_and_an_async_def_on_a_loop_of_its_own() -> None:
    assert called("book", who) == ("book", threading.current_thread().name)
    assert cast("tuple[str, str]", called("book", who_async))[0] == "book"
    assert current() is None


def test_from_a_loop_a_def_runs_on_another_thread_and_an_async_def_on_the_loop() -> None:
    async def both() -> tuple[object, object, str]:
        here = threading.current_thread().name
        return await run("find", who), await run("find", who_async), here

    ran_a_thread, ran_the_loop, here = asyncio.run(both())
    on_a_thread = cast("tuple[str, str]", ran_a_thread)
    on_the_loop = cast("tuple[str, str]", ran_the_loop)
    assert on_a_thread[0] == on_the_loop[0] == "find"
    assert on_a_thread[1] != here
    assert on_the_loop[1] == here


def test_the_arguments_are_passed_as_given() -> None:
    def echo(day: str, how_many: int) -> str:
        return f"{day}x{how_many}"

    assert called("echo", echo, "lunes", how_many=2) == "lunesx2"
