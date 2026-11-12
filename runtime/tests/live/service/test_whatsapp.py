"""The WhatsApp threads' ear for what another gateway hands on: a message it cannot read is said, the next heard."""

import asyncio
import time

import pytest

from runtime.live.peers import THREADS
from tests.conftest import needs_the_database, until
from tests.live.conftest import Side

HEARD_WITHIN_S = 5.0


# A message another gateway handed on that could not be read raised out of the loop that heard it, and
# no thread held here was told anything from then on. That a turn which cannot be answered is said with
# its call, and the contact's next one answered, is the same `survive` around each message of a thread:
# only a database that does not answer plays it, and `kit/test_loops.py` holds `survive` to it.
@needs_the_database
async def test_a_message_another_gateway_handed_on_that_cannot_be_read_is_said_and_the_next_is_heard(
    side: Side, caplog: pytest.LogCaptureFixture
) -> None:
    handed_on = THREADS.name.format(gateway=side.parts.owners.id)
    said = f"a message between gateways failed on {handed_on}"
    # Told until it is heard: the threads listen from a moment after they start, and the signal keeps nothing.
    deadline = time.monotonic() + HEARD_WITHIN_S
    while said not in caplog.text:
        assert time.monotonic() < deadline, "the threads never heard what was handed on"
        side.parts.signal.publish(handed_on, b"this is not a message")
        await asyncio.sleep(0.02)
    before = caplog.text.count(said)
    side.parts.signal.publish(handed_on, b'{"number": 7}')
    await until(lambda: caplog.text.count(said) > before)
