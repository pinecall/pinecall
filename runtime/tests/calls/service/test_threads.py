"""A WhatsApp thread's loops go on after a message that raised: the ear for handoffs, and the thread itself."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.service import threads
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.threads import OpenThread, Threads
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Env
from pinecall_runtime.session import service as session

THE_NUMBER = "+59829001199"


@asynccontextmanager
async def broken() -> AsyncGenerator[None]:
    """The database a message was heard against, which did not answer."""
    raise RuntimeError("the database did not answer")
    yield


@asynccontextmanager
async def begun() -> AsyncGenerator[None]:
    """A transaction that goes through."""
    yield None


def a_message(text: str) -> channels.Inbound:
    """A text WhatsApp sent to the box's number."""
    return channels.Inbound(
        number=THE_NUMBER,
        phone_number_id="pn_1",
        wa_id="59899123456",
        name="Marta",
        message_id=text,
        kind="text",
        text=text,
    )


def threads_of(serving: object) -> Threads:
    """The threads of a gateway that holds none."""
    return Threads(cast(Serving, serving), cast(AgentRegistry, None))


async def test_a_message_another_gateway_handed_on_that_cannot_be_read_or_heard_is_said_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    held = threads_of(SimpleNamespace(handles=SimpleNamespace(sessions=SimpleNamespace(begin=broken))))
    await held._take_on(b"this is not a message")
    await held._take_on(threads._INBOUND.dump_json(a_message("hola")))
    assert f"hearing a WhatsApp message handed on by another gateway failed on {THE_NUMBER}" in caplog.text


# A turn whose admission raised (a database that did not answer) ended the thread's loop: the contact's
# next message found no thread, and the one that raised was lost with nothing said of its call.
async def test_a_message_that_cannot_be_answered_is_said_with_its_call_and_the_contacts_next_is(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    answered: list[str] = []
    admitted = 0

    async def admit(*_args: object, **_kwargs: object) -> None:
        nonlocal admitted
        admitted += 1
        if admitted == 1:
            raise RuntimeError("the database did not answer")

    async def hear(_running: object, text: str) -> None:
        answered.append(text)

    async def close() -> None:
        return None

    def nothing(*_args: object, **_kwargs: object) -> None:
        return None

    route = SimpleNamespace(org="org_1", env=Env.sandbox)
    running = SimpleNamespace(
        call=SimpleNamespace(
            context=SimpleNamespace(call="call_1", route=route), turns=0, config=SimpleNamespace(slug="clinica-norte")
        ),
        usage=[],
        close=close,
    )
    held = threads_of(
        SimpleNamespace(
            handles=SimpleNamespace(sessions=SimpleNamespace(begin=begun)),
            logs=SimpleNamespace(store=SimpleNamespace(clock=lambda: 0.0), forget=nothing),
            live=SimpleNamespace(owners=SimpleNamespace(holding=nothing), close_call=nothing),
        )
    )
    monkeypatch.setattr(billing, "admit_turn", admit)
    monkeypatch.setattr(session, "hear_text", hear)
    thread = OpenThread(
        session=cast(session.Session, running), inbound=a_message("x"), http=cast(httpx.AsyncClient, None), token="t"
    )
    for line in ("uno", "dos"):
        thread.heard.put_nowait(line)
    thread.heard.put_nowait(None)
    await asyncio.wait_for(held._serve(("org_1", "sandbox", THE_NUMBER, "59899123456"), thread), 5)
    assert answered == ["dos"]
    assert "answering a WhatsApp message failed on call_1" in caplog.text
