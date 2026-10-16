"""The socket on its own: the wait before dialling again, and frames in order from any thread."""

import asyncio
import threading

import pytest

from pinecall import NotConnected
from pinecall._connection import Backoff, Connection, Handlers, Outbox
from tests.fakes.gateway import KEY, FakeGateway


async def nothing() -> None:
    return None


def handlers() -> Handlers:
    return Handlers(nothing, lambda entry: None, lambda error: None, lambda: None)


def test_the_wait_grows_with_each_attempt_up_to_its_ceiling_and_is_never_longer() -> None:
    backoff = Backoff(first_s=0.5, cap_s=4.0, factor=2.0)
    for attempt, window in [(0, 0.5), (1, 1.0), (3, 4.0), (10, 4.0)]:
        assert all(0 <= backoff.wait_s(attempt) <= window for _ in range(50))


def test_sending_with_no_socket_is_refused_rather_than_kept() -> None:
    with pytest.raises(NotConnected, match="not connected"):
        Connection("http://127.0.0.1:1", (KEY, None), handlers()).send("{}")


async def test_frames_from_the_loop_and_from_a_thread_leave_in_the_order_they_were_sent(
    gateway: FakeGateway,
) -> None:
    connection = Connection(gateway.url, (KEY, None), handlers())
    await connection.start()

    def ping(n: int) -> str:
        return f'{{"type":"ping","agent":"a{n}","call":null,"id":null,"data":{{}}}}'

    connection.send(ping(1))
    sender = threading.Thread(target=lambda: [connection.send(ping(n)) for n in (2, 3, 4)])
    sender.start()
    await asyncio.to_thread(sender.join)
    connection.send(ping(5))
    await gateway.until(lambda: len(gateway.received) == 5)
    assert [one["agent"] for one in gateway.received] == ["a1", "a2", "a3", "a4", "a5"]
    await connection.close()


async def test_a_gateway_that_is_not_there_is_said_with_where_it_was_looked_for() -> None:
    with pytest.raises(NotConnected, match=r"not reachable at ws://127\.0\.0\.1:1/v1/apps"):
        await Connection("http://127.0.0.1:1", (KEY, None), handlers()).start()


async def test_a_frame_the_loop_puts_never_overtakes_one_a_thread_put_before_it() -> None:
    outbox = Outbox(asyncio.get_running_loop())
    sender = threading.Thread(target=lambda: [outbox.put(text) for text in ("a", "b")])
    sender.start()
    sender.join()  # blocking on purpose: the thread's wake-ups have not run when "c" is put
    outbox.put("c")
    assert [await outbox.get() for _ in range(3)] == ["a", "b", "c"]
