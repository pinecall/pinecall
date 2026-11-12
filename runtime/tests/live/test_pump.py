"""A bound call's pump: an entry it cannot send is said and skipped, a socket that is gone ends it."""

import pytest
from cryptography.fernet import Fernet

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.calls.log.log import Log
from runtime.calls.log.store import Store
from runtime.calls.repository.heads import Claim
from runtime.enums import Env
from runtime.kit.crypto import Vault
from runtime.live.pump import pump
from runtime.wire.base import Entry
from tests.calls.factories import claim_call, logs_on
from tests.conftest import needs_the_database

pytestmark = needs_the_database

VAULT = Vault(Fernet.generate_key().decode())


# Three entries the agent logged, on a call that ended: its stream is its backlog and no more. Read by
# another gateway than the one that wrote it, so what was kept aside is asked of the store.
async def a_call_another_gateway_wrote(store: Store, call: str, agent: str) -> Log:
    """The ended call's log as a gateway that wrote none of it reads it, masking by its declaration."""
    await claim_call(store, call, agent, Claim(Scope("clinica", Env.sandbox)))
    writing = logs_on(store).logs.writing(call, agent)
    for name in ("one", "two", "three"):
        await writing.append("custom", {"name": name, "data": {}})
    await writing.seal()
    reading = logs_on(store).logs.reading(call)
    reading.mask_by(VAULT, Declaration(slug=agent, state_fields={"patient": "pii"}))
    return reading


# A pump that ended on an entry it could not open left the app deaf to its call: its tool calls
# unanswered to their deadline, with nothing said of why.
async def test_an_entry_the_pump_cannot_send_is_said_with_its_call_and_the_next_is_sent(
    store: Store, call: str, agent: str, caplog: pytest.LogCaptureFixture
) -> None:
    log = await a_call_another_gateway_wrote(store, call, agent)
    # What is kept aside for the second entry is no value a writer sealed: it cannot be opened.
    await store.keep_private(call, [(2, VAULT.seal("not what a writer seals"))])
    sent: list[int] = []

    async def send(entry: Entry) -> None:
        sent.append(entry.seq)

    await pump(log, 0, send, [])
    assert sent == [1, 3]
    assert f"sending an entry down its call's socket failed on {call} seq 2" in caplog.text


async def test_a_socket_that_is_gone_ends_the_pump_and_does_not_skip_its_entries(
    store: Store, call: str, agent: str
) -> None:
    log = await a_call_another_gateway_wrote(store, call, agent)
    sent: list[int] = []

    async def send(entry: Entry) -> None:
        if entry.seq == 3:
            raise OSError("the socket closed")
        sent.append(entry.seq)

    await pump(log, 0, send, [])
    assert sent == [1, 2]
