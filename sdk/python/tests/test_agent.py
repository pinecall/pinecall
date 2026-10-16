"""The base class: a subclass's own `__init__` keeps the state, and the log is the agent's own."""

import asyncio
from typing import Literal

import pytest
from typing_extensions import override

from pinecall import Agent, CallLine, CallWorld, PinecallError, render
from pinecall.client import Found


class ConAgenda(Agent):
    """Una clínica con su propia agenda."""

    patient: str | None = None

    def __init__(self, agenda: str) -> None:
        """Keep the agenda this clinic books in."""
        self.agenda = agenda


def test_a_subclass_with_an_init_of_its_own_still_opens_its_state() -> None:
    agent = ConAgenda("la de prueba")
    assert (agent.agenda, agent.patient) == ("la de prueba", None)
    assert agent.snapshot() == {"patient": None}


def test_a_logged_line_is_kept_in_order_and_heard_until_the_listener_stops() -> None:
    agent = ConAgenda("x").seal()
    heard: list[str] = []
    stop = agent.on_log(lambda line: heard.append(line.name))
    agent.log("appointment.booked", {"when": "martes 10:00"})
    stop()
    agent.log("sms.sent")
    assert [(line.name, line.data) for line in agent.logged()] == [
        ("appointment.booked", {"when": "martes 10:00"}),
        ("sms.sent", None),
    ]
    assert heard == ["appointment.booked"]


def test_a_class_that_is_not_sealed_says_so() -> None:
    agent = ConAgenda("x")
    assert agent.sealed is False
    assert agent.seal().sealed is True


class Recepcion(Agent):
    """Una recepción con hooks."""

    stage: Literal["identify", "book"] = "identify"
    patient: str | None = None
    ended: bool = False

    @override
    def on_call(self, call: CallWorld) -> None:
        """Know the caller by their number."""
        self.patient = call.from_
        self.stage = "book"

    @override
    async def on_end(self, call: CallWorld) -> None:
        """Note that it ended."""
        self.ended = True


def test_outside_a_call_the_agent_says_there_is_none_rather_than_handing_back_nothing() -> None:
    agent = Recepcion()
    assert not agent.has_call
    with pytest.raises(PinecallError, match="there is no call here"):
        _ = agent.call
    world = CallWorld(CallLine(id="CA_1", from_="+34600"))
    assert agent.serving(world).call is world


def test_a_hook_writes_as_the_hook_whether_a_def_or_an_async_def() -> None:
    agent = Recepcion().seal()
    world = CallWorld(CallLine(id="CA_1", from_="+34600"))
    agent.serving(world).run_hook("on_call", world)
    agent.run_hook("on_end", world)
    assert [(change.author, change.field) for change in agent.changes()] == [
        ("hook:on_call", "patient"),
        ("hook:on_call", "stage"),
        ("hook:on_end", "ended"),
    ]


def test_the_prompt_of_an_agent_in_a_call_is_its_calls_channel() -> None:
    agent = Recepcion().serving(CallWorld(CallLine(id="WA_1", channel="whatsapp")))
    assert "You are on WhatsApp." in render(agent)["identity"]


async def test_a_search_of_the_knowledge_is_the_calls() -> None:
    async def searching(query: str, k: int | None) -> list[Found]:
        return [Found("horario.md", None, f"{query}:{k}")]

    world = CallWorld(CallLine(id="CA_1"), None, searching, asyncio.get_running_loop())
    found = await Recepcion().serving(world).knowledge.search("horario", k=3)
    assert [one.text for one in found] == ["horario:3"]


def test_the_contacts_last_call_is_read_from_the_store_the_mount_gave() -> None:
    agent = Recepcion()
    with pytest.raises(PinecallError, match="needs a store"):
        agent.last("+34600")
    kept = {"+34600": {"stage": "book"}}
    assert agent.reads_last_from(kept.get).last("+34600") == {"stage": "book"}
