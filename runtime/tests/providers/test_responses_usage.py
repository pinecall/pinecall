"""A Responses stream reads a usage that counts no cache writes as none written, and goes on."""

from dataclasses import dataclass, field

from pinecall_runtime.providers.service.stages import counting_unreported_cache_as_none


@dataclass
class Details:
    cached_tokens: int | None = 0
    cache_write_tokens: int | None = None


@dataclass
class Usage:
    input_tokens_details: Details | None = field(default_factory=Details)


@dataclass
class Response:
    usage: Usage | None = field(default_factory=Usage)


@dataclass
class Completed:
    response: Response = field(default_factory=Response)


class ResponsesStream:
    """As livekit's Responses stream: each event goes through `_process_event`."""

    def __init__(self) -> None:
        self.read: list[Details | None] = []

    def _process_event(self, event: Completed) -> None:
        usage = event.response.usage
        self.read.append(None if usage is None else usage.input_tokens_details)


def test_an_unreported_cache_write_count_is_read_as_none_written() -> None:
    stream = ResponsesStream()
    counting_unreported_cache_as_none(stream)  # pyright: ignore[reportArgumentType]
    stream._process_event(Completed())  # pyright: ignore[reportPrivateUsage]
    assert stream.read == [Details(cached_tokens=0, cache_write_tokens=0)]


def test_counts_the_vendor_gives_are_left_as_given() -> None:
    stream = ResponsesStream()
    counting_unreported_cache_as_none(stream)  # pyright: ignore[reportArgumentType]
    given = Completed(Response(Usage(Details(cached_tokens=12, cache_write_tokens=3))))
    stream._process_event(given)  # pyright: ignore[reportPrivateUsage]
    assert stream.read == [Details(cached_tokens=12, cache_write_tokens=3)]


def test_a_stream_with_no_such_events_is_left_as_it_is() -> None:
    plain = object()
    assert counting_unreported_cache_as_none(plain) is plain  # pyright: ignore[reportArgumentType]
