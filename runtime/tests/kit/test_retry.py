"""Asking the other side of ours again: the waits between tries, what is asked again and what is an answer."""

import asyncio

import pytest

from runtime.exceptions import UpstreamError
from runtime.kit.retry import FIRST_WAIT_S, JITTER, LONGEST_WAIT_S, Within, delay, keep_asking, retry, until

AWAY = UpstreamError("away", retryable=True)


def test_the_waits_double_to_the_cap_each_a_little_short_of_it() -> None:
    """Half a second, then double, never past the longest; each shortened by its jitter, never lengthened."""
    for attempt, most in enumerate((FIRST_WAIT_S, 1.0, 2.0, 4.0, LONGEST_WAIT_S, LONGEST_WAIT_S)):
        assert most * (1 - JITTER) <= delay(attempt) <= most
    assert delay(9, longest_s=5.0) <= 5.0


async def test_an_attempt_is_asked_again_while_the_other_side_is_away() -> None:
    """A failure that says it may be asked again is, until the answer comes."""
    tries: list[int] = []
    waited: list[float] = []

    async def attempt() -> str:
        tries.append(1)
        if len(tries) < 2:
            raise AWAY
        return "done"

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    assert await keep_asking(attempt, within_s=None, what="x", sleep=sleep) == "done"
    assert (len(tries), len(waited)) == (2, 1)


async def test_an_answer_that_is_a_refusal_is_final_and_not_asked_again() -> None:
    """A refusal is the answer: asking again would get the same."""
    tries: list[int] = []

    async def attempt() -> str:
        tries.append(1)
        raise UpstreamError("no", answered=409)

    with pytest.raises(UpstreamError, match="no"):
        await keep_asking(attempt, within_s=None, what="x")
    with pytest.raises(UpstreamError, match="no"):
        await retry(attempt)
    assert len(tries) == 2


async def test_an_attempt_with_a_deadline_stops_asking_at_it() -> None:
    """The other side away past the deadline ends the asking with its failure."""

    async def attempt() -> str:
        raise AWAY

    with pytest.raises(UpstreamError, match="away"):
        await asyncio.wait_for(keep_asking(attempt, within_s=0.1, what="x"), 2)


async def test_a_retry_tries_so_many_times_and_waits_what_it_was_told_when_told() -> None:
    """Two retries unless said; a failure that names its wait (a 429's Retry-After) is waited for exactly."""
    tries: list[int] = []
    waited: list[float] = []

    async def attempt() -> str:
        tries.append(1)
        raise UpstreamError("slow down", retryable=True, retry_after_s=3.0)

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    with pytest.raises(UpstreamError, match="slow down"):
        await retry(attempt, sleep=sleep)
    assert (len(tries), waited) == (3, [3.0, 3.0])


async def test_a_probe_is_asked_every_so_often_until_it_answers_or_the_time_runs_out() -> None:
    answers = iter([None, None, "there"])

    async def probe() -> str | None:
        return next(answers)

    async def never() -> str | None:
        return None

    assert await until(probe, every_s=0.01, within_s=5.0) == "there"
    assert await until(never, every_s=0.01, within_s=0.0) is None


# A job asks its gateway four things as it arrives. Each given the whole wait, a gateway away would be
# waited for four times as long as the caller on the line can wait.
async def test_asks_that_share_a_wait_are_each_asked_again_within_what_is_left_of_it() -> None:
    """The first ask is asked again until answered; one that starts once the wait is over is asked once."""
    tries: list[str] = []

    async def no_sleep(_seconds: float) -> None:
        return None

    async def away_once() -> str:
        tries.append("first")
        if len(tries) < 2:
            raise AWAY
        return "answered"

    async def away() -> str:
        tries.append("second")
        raise AWAY

    asking = Within(30.0, sleep=no_sleep)
    assert await asking.ask(away_once, "x") == "answered"
    asking.until = 0.0
    with pytest.raises(UpstreamError, match="away"):
        await asking.ask(away, "y")
    assert tries == ["first", "first", "second"]


async def test_an_answer_that_is_a_refusal_ends_an_ask_on_a_shared_wait_at_once() -> None:
    """A refusal is the answer, whatever is left of the wait."""
    tries: list[int] = []

    async def refused() -> str:
        tries.append(1)
        raise UpstreamError("no", answered=404)

    with pytest.raises(UpstreamError, match="no"):
        await Within(30.0).ask(refused, "x")
    assert len(tries) == 1
