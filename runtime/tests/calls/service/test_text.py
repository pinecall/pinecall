"""A written call taken up again: the context it is rebuilt on is the one it opened with."""

from datetime import date

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service.registry import Registration
from pinecall_runtime.calls.context import Contact
from pinecall_runtime.calls.service.text import _as_it_opened
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from tests.calls.factories import AGENT, CALL, CALLER, LINE, entry

SCOPE = Scope("org_1", Env.sandbox)
REGISTRATION = Registration(slug=AGENT, scope=SCOPE, owner="socket_1", config=AgentConfig(slug=AGENT))
TODAY = date(2026, 10, 23)


def taken_up(caller: object) -> Contact | None:
    """The contact a call is rebuilt with, from a call.started that names this caller."""
    line = {**LINE, "channel": "web", "direction": "inbound", "caller": caller, "started_at": 1_790_000_000.0}
    return _as_it_opened(CALL, REGISTRATION, SCOPE, [entry(1, "call.started", line)], TODAY).contact


def test_a_call_taken_up_again_keeps_the_contact_it_opened_with_so_memory_files_what_it_teaches_there() -> None:
    """`chat --as`: after the gateway that held the call restarts, the next one still knows who is calling."""
    assert taken_up({"id": "ct_9", "name": "Marta"}) == Contact(id="ct_9", name="Marta")
    assert taken_up(CALLER) == Contact(id="ct_9", phone="+34611222333", name="Marta")


def test_a_call_opened_with_nobody_named_is_taken_up_with_nobody() -> None:
    """No caller on the entry, no contact on the context: the visitor id stays the only thing it knows."""
    assert taken_up(None) is None
