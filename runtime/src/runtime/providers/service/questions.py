"""A question asked of a model outside a call: its lines, the tool it must answer by, and what came back."""

import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, Never

from livekit.agents import APIConnectOptions, llm
from livekit.agents.llm import ChatContext

from runtime.exceptions import UpstreamError
from runtime.kit.text import a_mapping
from runtime.providers.service.prices import completion_usage
from runtime.providers.service.refusals import refusing
from runtime.providers.service.stages import thinking_outside_a_call
from runtime.providers.stage import Running
from runtime.wire.metrics import LLMModelUsage

type Role = Literal["system", "user", "assistant"]

# A vendor that ends a tool call's arguments half-way hands back text that is no JSON: its failure,
# said as one. Until 2026-11 the text was parsed bare, and a judge's cut answer failed the seal of its call.
CUT_SHORT = "{vendor} cut the arguments of {tool} short: they do not read as JSON"
WHAT_IT_WAS_ASKED = "what it was asked"


@dataclass(frozen=True, slots=True)
class Line:
    """One line of what a model is asked: who says it, and the words."""

    role: Role
    text: str


@dataclass(frozen=True, slots=True)
class Patience:
    """How long a model is given to answer, and how many times it is asked again when it does not."""

    within_s: float = 10.0
    retries: int = 3


# What livekit gives a turn of a call.
A_TURNS = Patience()


@dataclass(frozen=True, slots=True)
class Answer:
    """What a model answered: its words, the arguments of the tool it called, and what its requests used."""

    text: str
    # None: it called no tool, asked twice.
    arguments: Mapping[str, object] | None = None
    # The requests behind the answer, summed; None when the vendor said nothing of them.
    usage: LLMModelUsage | None = None


# livekit's errors are translated here, once, where the vendor is asked: a caller reads our errors
# alone, and nothing above this module imports the library to ask a model a question.
class Answerer:
    """A stage's model open outside a call, asked one question at a time; the vendor's no is said in our words."""

    def __init__(self, running: Running, model: llm.LLM[Never]) -> None:
        self.running = running
        self._model = model

    async def ask(
        self, lines: Sequence[Line], *, what: str = WHAT_IT_WAS_ASKED, patience: Patience = A_TURNS
    ) -> Answer:
        """The model's words on the lines, asked once."""
        with refusing(self.running.vendor, what):
            response = await self._model.chat(chat_ctx=_chat_of(lines), conn_options=_options_of(patience)).collect()
        return Answer(text=response.text or "", usage=completion_usage(self._model, response.usage))

    # A model that thinks before it answers cannot be held to a tool (Anthropic's thinking takes
    # `auto` alone), and now and then answers in words: it is asked once more, its words in front of it.
    async def ask_by_tool(
        self,
        lines: Sequence[Line],
        tool: Mapping[str, Any],
        *,
        insist: str,
        what: str = WHAT_IT_WAS_ASKED,
        patience: Patience = A_TURNS,
    ) -> Answer:
        """One request that must answer by calling the tool; asked a second time when it answers in words."""
        chat = _chat_of(lines)
        tools: list[llm.Tool] = [llm.function_tool(_never_run, raw_schema=dict(tool))]
        options = _options_of(patience)
        with refusing(self.running.vendor, what):
            response = await self._model.chat(
                chat_ctx=chat, tools=tools, tool_choice="required", conn_options=options
            ).collect()
            spent = [response.usage]
            said = response.text or ""
            if not response.tool_calls:
                chat.add_message(role="assistant", content=said or "…")
                chat.add_message(role="user", content=insist)
                response = await self._model.chat(
                    chat_ctx=chat, tools=tools, tool_choice="required", conn_options=options
                ).collect()
                spent.append(response.usage)
                said = response.text or said
        usage = completion_usage(self._model, _sum_usage(spent))
        if not response.tool_calls:
            return Answer(text=said, usage=usage)
        return Answer(text=said, arguments=self._arguments_of(tool, response.tool_calls[0].arguments), usage=usage)

    def _arguments_of(self, tool: Mapping[str, Any], raw: str) -> Mapping[str, object]:
        try:
            answered: object = json.loads(raw or "{}")
        except ValueError as cut:
            words = CUT_SHORT.format(vendor=self.running.vendor, tool=tool.get("name"))
            raise UpstreamError(words, vendor=self.running.vendor, retryable=True) from cut
        return answered if a_mapping(answered) else {}


@asynccontextmanager
async def open_answerer(running: Running) -> AsyncGenerator[Answerer]:
    """The stage's model open for as long as the block asks it questions, and closed after."""
    async with thinking_outside_a_call(running) as model:
        yield Answerer(running, model)


async def ask(running: Running, *, system: str, user: str, what: str = WHAT_IT_WAS_ASKED) -> str:
    """One question asked of the stage's model outside a call, and its words."""
    async with open_answerer(running) as model:
        return (await model.ask([Line("system", system), Line("user", user)], what=what)).text


def _chat_of(lines: Sequence[Line]) -> ChatContext:
    chat = ChatContext.empty()
    for line in lines:
        chat.add_message(role=line.role, content=line.text)
    return chat


def _options_of(patience: Patience) -> APIConnectOptions:
    return APIConnectOptions(max_retry=patience.retries, timeout=patience.within_s)


def _sum_usage(spent: Sequence[llm.CompletionUsage | None]) -> llm.CompletionUsage | None:
    used = [one for one in spent if one is not None]
    if not used:
        return None
    return llm.CompletionUsage(
        completion_tokens=sum(one.completion_tokens for one in used),
        prompt_tokens=sum(one.prompt_tokens for one in used),
        prompt_cached_tokens=sum(one.prompt_cached_tokens for one in used),
        cache_creation_tokens=sum(one.cache_creation_tokens for one in used),
        cache_read_tokens=sum(one.cache_read_tokens for one in used),
        total_tokens=sum(one.total_tokens for one in used),
    )


# The answer is read off the call's arguments; the tool itself never runs. livekit hands a tool given
# by its schema its arguments under this name.
async def _never_run(raw_arguments: dict[str, object]) -> str:
    return json.dumps(raw_arguments)
