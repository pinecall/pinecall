"""A plugin's LLM whose every request carries the operator's fields for its model, and no caller's sampling."""

import asyncio
from collections.abc import Mapping
from typing import Any, Never, override

from livekit.agents import llm
from livekit.agents.llm import Tool, ToolChoice
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import is_given

# How a model samples is the stage's: the row's request fields and the agent's temperature, set
# where the model is named. A caller's own sampling never rides a request: livekit's intent judge
# asks every model for temperature 0 (`run_result.py`), which a vendor's SDK may no longer take
# at all, and the operator chose the model's own.
SAMPLING = frozenset({"temperature", "top_p", "top_k"})


# xAI's Responses API ends a reply with usage that counts no cache writes (`cache_write_tokens: null`),
# and livekit's Responses stream passes that None on where an int is due: the reply is said whole, then
# the stream fails as a "connection error" and the turn with it. A count the vendor does not give is
# read as none written. Only a Responses stream reads such usage; any other is left as it is.
def count_unreported_cache_as_none(stream: llm.LLMStream) -> llm.LLMStream:
    """The stream, its usage's missing cache counts read as 0 before livekit reads them."""
    processed: object = getattr(stream, "_process_event", None)
    if not callable(processed):
        return stream

    def process(event: object) -> object:
        usage = getattr(getattr(event, "response", None), "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        for count in ("cached_tokens", "cache_write_tokens"):
            if details is not None and hasattr(details, count) and getattr(details, count) is None:
                setattr(details, count, 0)
        return processed(event)

    # The stream's own hook, replaced on this instance alone; object.__setattr__ names it as data.
    object.__setattr__(stream, "_process_event", process)
    return stream


# A plugin's constructor takes no field for every request (a model's thinking, its effort), and
# livekit hands each request extra_kwargs: the row's ride every one, a caller's own over them.
class LLMWithRequest(llm.LLM[Never]):
    """A plugin's LLM whose every request carries the operator's fields for its model, and no caller's sampling."""

    def __init__(self, built: llm.LLM[Never], request: Mapping[str, Any]) -> None:
        super().__init__()
        self.built = built
        self.request = dict(request)
        self._label = built.label
        built.on("metrics_collected", self._report_metrics)  # pyright: ignore[reportUnknownMemberType]
        built.on("error", self._report_error)  # pyright: ignore[reportUnknownMemberType]

    @property
    @override
    def model(self) -> str:
        """The built LLM's model, so usage and metrics name it."""
        return self.built.model

    @property
    @override
    def provider(self) -> str:
        """The built LLM's vendor, so usage and metrics name it."""
        return self.built.provider

    @override
    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        """The built LLM's request, with the row's fields and the caller's over them, its sampling aside."""
        given = {
            name: value
            for name, value in (extra_kwargs if is_given(extra_kwargs) else {}).items()
            if name not in SAMPLING
        }
        return count_unreported_cache_as_none(
            self.built.chat(
                chat_ctx=chat_ctx,
                tools=tools,
                conn_options=conn_options,
                parallel_tool_calls=parallel_tool_calls,
                tool_choice=tool_choice,
                extra_kwargs={**self.request, **given},
            )
        )

    @override
    def prewarm(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Open the built LLM's connection before the first request."""
        self.built.prewarm(loop=loop)

    @override
    async def aclose(self) -> None:
        """Stop listening to the built LLM, and close it."""
        self.built.off("metrics_collected", self._report_metrics)  # pyright: ignore[reportUnknownMemberType]
        self.built.off("error", self._report_error)  # pyright: ignore[reportUnknownMemberType]
        await self.built.aclose()

    def _report_metrics(self, *args: object) -> None:
        self.emit("metrics_collected", *args)

    def _report_error(self, *args: object) -> None:
        self.emit("error", *args)
