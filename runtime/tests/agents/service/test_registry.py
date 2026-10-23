"""The registry: a person's own phone, one at a time."""

from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.redis import LocalSignal
from tests.conftest import needs_the_database


# K F2 (2026-10-23): `line from` added a phone beside the one before, and `line forget` then took both.
@needs_the_database
def test_a_persons_phone_said_again_replaces_the_one_before_and_forget_takes_the_one_left(store: Store) -> None:
    registry = AgentRegistry(LocalSignal(), Logs(store))
    registry.calls_from(Env.sandbox, "+34607827824", "m_ana")
    registry.calls_from(Env.sandbox, "+34600000000", "m_ana")
    registry.calls_from(Env.sandbox, "+34611111111", "m_eva")
    assert registry.phones_of(Env.sandbox, "m_ana") == ["+34600000000"]
    assert registry.phone_of(Env.sandbox, "+34607827824") is None
    assert registry.phones_of(Env.sandbox, "m_eva") == ["+34611111111"]
    assert registry.forget_calls_from(Env.sandbox, "m_ana") == ["+34600000000"]
    assert registry.phones_of(Env.sandbox, "m_eva") == ["+34611111111"]
