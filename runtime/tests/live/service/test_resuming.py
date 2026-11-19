"""Which call a written message goes on: its email thread's own, and what a new call carries on."""

from collections.abc import Mapping

import pytest

from runtime.actor import Scope
from runtime.calls import service as calls
from runtime.enums import Channel, Env
from runtime.live.service import resuming
from runtime.live.service.resuming import Earlier
from runtime.whatsapp.service.webhook import Inbound
from runtime.wire.base import Entry

SCOPE = Scope("org_1", Env.sandbox)
IDLE_S = 7200.0


def a_log(thread: str, *, at: float, over: bool = False) -> list[Entry]:
    """An email call opened on a thread, its last entry at a moment, ended or not."""
    opened = {"metadata": {"email_thread": thread}}
    started = Entry(seq=1, ts=at - 10, call="c", agent="a", type="call.started", ephemeral=False, data=opened)
    kind = "call.ended" if over else "turn.agent"
    last = Entry(seq=2, ts=at, call="c", agent="a", type=kind, ephemeral=False, data={})
    return [started, last]


def an_email(thread: str) -> Inbound:
    """Ana's email on a thread."""
    return Inbound(
        "help@acme.example", "x", "ana@example.org", None, "<m@x>", "text", "…", channel=Channel.email, thread=thread
    )


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Entry]]:
    """The contact's email calls, newest first, and the newest ended one any channel would carry on."""
    kept: dict[str, list[Entry]] = {}

    async def newest(*_: object, limit: int) -> list[str]:
        return list(kept)[:limit]

    async def entries(_session: object, call: str) -> list[Entry]:
        return kept[call]

    async def ended(*_: object, **asked: object) -> str | None:
        return "call_ended_elsewhere" if asked.get("ended") else None

    monkeypatch.setattr(calls, "list_newest_calls_with", newest)
    monkeypatch.setattr(calls, "list_entries", entries)
    monkeypatch.setattr(calls, "find_newest_call_with", ended)
    return kept


async def find(logs: Mapping[str, list[Entry]], thread: str, now: float) -> Earlier:
    """What the email on the thread goes on, at a moment."""
    del logs
    return await resuming.find_earlier(None, SCOPE, "front-desk", an_email(thread), now=now, idle_s=IDLE_S)  # type: ignore[arg-type]


async def test_an_email_goes_on_its_own_threads_call_even_when_another_thread_is_newer(
    logs: dict[str, list[Entry]],
) -> None:
    """The newest call is the other thread's: the one taken up is this thread's."""
    logs["call_b"] = a_log("<b1@x>", at=1000)
    logs["call_a"] = a_log("<a1@x>", at=900)
    assert await find(logs, "<a1@x>", now=1100) == Earlier("call_a", "call_a")


async def test_a_quiet_or_ended_thread_is_carried_on_and_a_new_one_carries_on_the_newest_ended_call(
    logs: dict[str, list[Entry]],
) -> None:
    """Quiet or over, a thread's call is carried on by a new one; a thread with none, the newest ended call."""
    logs["call_a"] = a_log("<a1@x>", at=900)
    assert await find(logs, "<a1@x>", now=900 + IDLE_S + 1) == Earlier(None, "call_a")
    logs["call_a"] = a_log("<a1@x>", at=900, over=True)
    assert await find(logs, "<a1@x>", now=950) == Earlier(None, "call_a")
    assert await find(logs, "<c1@x>", now=950) == Earlier(None, "call_ended_elsewhere")
