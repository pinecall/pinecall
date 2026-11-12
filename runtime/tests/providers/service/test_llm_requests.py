"""A Responses stream reads a usage that counts no cache writes as none written, and goes on."""

from dataclasses import dataclass, field

from livekit.agents import llm

from runtime.providers.service import stages
from runtime.providers.service.llm_requests import LLMWithRequest, count_unreported_cache_as_none
from runtime.providers.stage import Running
from tests.fakes.acme import ACME, AcmeLLM


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
    count_unreported_cache_as_none(stream)  # pyright: ignore[reportArgumentType]
    stream._process_event(Completed())  # pyright: ignore[reportPrivateUsage]
    assert stream.read == [Details(cached_tokens=0, cache_write_tokens=0)]


def test_counts_the_vendor_gives_are_left_as_given() -> None:
    stream = ResponsesStream()
    count_unreported_cache_as_none(stream)  # pyright: ignore[reportArgumentType]
    given = Completed(Response(Usage(Details(cached_tokens=12, cache_write_tokens=3))))
    stream._process_event(given)  # pyright: ignore[reportPrivateUsage]
    assert stream.read == [Details(cached_tokens=12, cache_write_tokens=3)]


def test_a_stream_with_no_such_events_is_left_as_it_is() -> None:
    plain = object()
    assert count_unreported_cache_as_none(plain) is plain  # pyright: ignore[reportArgumentType]


# livekit's own intent judge (`run_result.py`) asks every model for temperature 0; the operator
# chose the model's own, and a vendor's SDK may take no such argument at all.
async def test_a_callers_sampling_never_rides_a_request_and_the_rows_fields_always_do() -> None:
    staged = stages.llm_of(Running(ACME, "k", request={"thinking": {"effort": "low"}}))
    history = llm.ChatContext.empty()
    history.add_message(role="user", content="¿Abren el sábado?")
    async with staged.chat(chat_ctx=history, extra_kwargs={"temperature": 0.0, "top_p": 0.1, "seed": 7}):
        pass
    assert isinstance(staged, LLMWithRequest) and isinstance(staged.built, AcmeLLM)
    assert staged.built.requests[0].extra == {"thinking": {"effort": "low"}, "seed": 7}

    bare = stages.llm_of(Running(ACME, "k"))
    async with bare.chat(chat_ctx=history, extra_kwargs={"temperature": 0.0}):
        pass
    assert isinstance(bare, LLMWithRequest) and isinstance(bare.built, AcmeLLM)
    assert bare.built.requests[0].extra == {}
