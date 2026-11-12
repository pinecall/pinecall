"""A server-sent event stream read by a process of ours: each message with the id it was sent under."""

from collections.abc import AsyncIterator

from runtime.kit.sse import read_sse


async def test_a_message_of_a_stream_comes_with_the_id_it_was_sent_under() -> None:
    """A command comes under its id, an entry under none, and a ping is no message."""

    async def lines() -> AsyncIterator[str]:
        for line in ("id: c1", "event: say", 'data: {"type": "say"}', "", ": ping", "", 'data: {"seq": 3}', ""):
            yield line

    assert [(sent.id, sent.data) async for sent in read_sse(lines())] == [
        ("c1", {"type": "say"}),
        (None, {"seq": 3}),
    ]
