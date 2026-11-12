"""A tool that stops to ask: answered with the question, and finished once the answer is given."""

import asyncio

import pytest

from pinecall import GetEmail, GetPhone, PinecallError, ToolFailed
from pinecall._asking import Asking, giving_tools, tasks_on


async def test_an_async_tool_stops_at_its_question_and_finishes_with_the_answer() -> None:
    asking = Asking([GetEmail])

    async def booking() -> object:
        email = await asking.ask(GetEmail)
        return {"booked_for": email}

    first = await asking.run("book", booking)
    assert isinstance(first, str)
    assert first.endswith("Then call give_email.")
    assert asking.open is not None
    assert asking.open.name == "give_email"
    ended = await asking.given("give_email", {"email": "Ana@Example.com"})
    assert ended == {"finished": "book", "result": {"booked_for": "ana@example.com"}}
    assert (asking.open, asking.asked) == (None, None)


async def test_a_tool_on_a_thread_waits_for_the_answer_the_same_way() -> None:
    asking = Asking([GetPhone])

    def booking() -> object:
        return {"call_back": asking.ask(GetPhone).result(5)}

    first = await asking.run("book", lambda: asyncio.to_thread(booking))
    assert "a phone number to reach the caller at" in str(first)
    ended = await asking.given("give_phone", {"number": "+1 415 555 0142"})
    assert ended == {"finished": "book", "result": {"call_back": "+14155550142"}}


async def test_an_answer_the_check_refuses_is_said_and_the_question_stays_open() -> None:
    asking = Asking([GetEmail])

    async def booking() -> object:
        return await asking.ask(GetEmail)

    await asking.run("book", booking)
    with pytest.raises(ToolFailed, match="not an email address"):
        await asking.given("give_email", {"email": "ana at example"})
    assert asking.asked is not None
    assert asking.asked.task == "email"
    with pytest.raises(ToolFailed, match="email must be given"):
        await asking.given("give_email", {})


async def test_a_question_outside_a_tool_or_of_another_task_is_refused() -> None:
    asking = Asking([GetEmail])
    with pytest.raises(PinecallError, match="inside a tool"):
        await asking.ask(GetEmail)

    async def wrong() -> object:
        return await asking.ask(GetPhone)

    with pytest.raises(PinecallError, match="not a task of this agent"):
        await asking.run("book", wrong)


async def test_the_page_may_give_the_answer_and_the_model_is_told_how_it_ended() -> None:
    asking = Asking([GetEmail])

    async def booking() -> object:
        return {"for": await asking.ask(GetEmail)}

    await asking.run("book", booking)
    assert await asking.given_by_page("phone", {"number": "1"}) is None
    told = await asking.given_by_page("email", {"email": "ana@example.com"})
    assert told is not None
    assert "book is done with this result" in told


async def test_a_call_that_ends_with_a_question_open_tells_the_tool() -> None:
    asking = Asking([GetEmail])
    failed: list[str] = []

    async def booking() -> object:
        try:
            return await asking.ask(GetEmail)
        except PinecallError as gone:
            failed.append(str(gone))
            raise

    await asking.run("book", booking)
    asking.abandon()
    for _ in range(10):
        await asyncio.sleep(0)
    assert failed == ["the call ended before the caller gave the caller's email address"]


def test_a_call_asks_for_its_classs_tasks_and_with_a_team_for_every_members_once() -> None:
    class Desk:
        tasks = (GetEmail,)

    class Billing:
        tasks = (GetEmail, GetPhone)

    assert tasks_on(Desk) == [GetEmail]
    assert tasks_on(Desk, [Desk, Billing]) == [GetEmail, GetPhone]
    with pytest.raises(PinecallError, match="an agent declares a tool of that name"):
        giving_tools([GetEmail], ["give_email"])
