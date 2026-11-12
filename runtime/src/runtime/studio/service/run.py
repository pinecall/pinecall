"""One call a Studio agent answers from its definition: what it sends as the call opens, on a tool, at the end."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from runtime.studio.service import collect as collecting
from runtime.studio.service import declaring, fetch, prompt
from runtime.studio.service.definition import COLLECT
from runtime.wire.base import Command
from runtime.wire.commands import PromptSet, StateSet, ToolsSet
from runtime.wire.events import ToolCall
from runtime.wire.parts import ToolResult
from runtime.wire.studio import Definition

NO_SUCH_TOOL = "{name}: this agent has no such tool"
# What a failed request says of the body it came back with, at most.
LONGEST_SHOWN = 2000


# What an SDK keeps of a call in its process: nothing here touches a socket, so a call is run in a test
# by calling these and reading the commands they answer.
@dataclass
class Run:
    """A call answered from a definition: the call's values, what it collected, and what its prompt was told."""

    agent: str
    call: str
    definition: Definition
    values: dict[str, Any]
    collected: dict[str, Any] = field(default_factory=dict[str, Any])
    # Each block of the prompt as it was last sent: one that did not change is not sent again.
    sent: dict[str, str] = field(default_factory=dict[str, str])

    # What an SDK sends at a call's start: the state, every block of the prompt, the tools visible.
    def open(self, state: dict[str, Any] | None) -> list[Command]:
        """The call's first commands; `state` is what it opened in, or was handed over with."""
        collect = self.definition.collect
        if collect is None:
            return self.say_definition()
        names = {item.name for item in collect.fields}
        self.collected = {name: value for name, value in (state or {}).items() if name in names}
        return [self._command("state.set", StateSet(state=self.collected)), *self.say_definition()]

    def say_definition(self) -> list[Command]:
        """The prompt's blocks that changed, and the tools visible, as the call's definition says them."""
        definition = self.definition
        specs = declaring.list_tool_specs(definition)
        view = "" if definition.collect is None else collecting.view(definition.collect, self.collected)
        blocks = {
            "identity": prompt.identity(definition, self.values),
            "tools": prompt.tools_block(specs),
            "view": view,
        }
        said = [said for name, text in blocks.items() if (said := self._say(name, text)) is not None]
        return [*said, self._command("tools.set", ToolsSet(tools=specs))]

    # The model handed over what the caller said: the state says it, the view counts it, the model reads
    # what is still missing.
    def collect(self, called: ToolCall, started: float) -> list[Command]:
        """Keep what the tool was called with; the state and the view that changed, then the tool's answer."""
        collect = self.definition.collect
        assert collect is not None
        taken = collecting.take(collect, self.collected, called.arguments)
        said: list[Command] = []
        if taken.saved:
            said.append(self._command("state.set", StateSet(state=self.collected, changed=taken.saved)))
        view = self._say("view", collecting.view(collect, self.collected))
        return [*said, *([] if view is None else [view]), self.answer(called, started, output=taken.dump())]

    async def run_tool(
        self, fetcher: fetch.Fetcher, secrets: dict[str, str], called: ToolCall, started: float
    ) -> list[Command]:
        """Run one tool the model called: data collection here, any other as its request to the business's API."""
        if called.name == COLLECT and self.definition.collect is not None:
            return self.collect(called, started)
        tool = next((item for item in self.definition.tools if item.name == called.name), None)
        if tool is None:
            return [self.answer(called, started, error=NO_SUCH_TOOL.format(name=called.name))]
        request = fetch.fill_request(tool, called.arguments, {**self.values, "secrets": secrets})
        answered = await fetch.send(fetcher, request, name=tool.name, timeout_s=tool.timeout_s)
        error = answered.error
        if error is not None and answered.body is not None:
            error = f"{error}: {_shorten(answered.body)}"
        return [self.answer(called, started, output=answered.body, error=error)]

    def answer(self, called: ToolCall, started: float, *, output: Any = None, error: str | None = None) -> Command:
        """The tool's result as the call's log keeps it."""
        took = round(time.monotonic() - started, 3)
        result = ToolResult(call_id=called.call_id, name=called.name, output=output, error=error, duration_s=took)
        return self._command("tool.result", result)

    def _say(self, name: str, text: str) -> Command | None:
        if self.sent.get(name, "") == text:
            return None
        self.sent[name] = text
        return self._command("prompt.set", PromptSet(name=name, text=text))

    def _command(self, kind: str, body: PromptSet | StateSet | ToolsSet | ToolResult) -> Command:
        data = body.model_dump(mode="json", exclude_none=True)
        return Command(type=kind, agent=self.agent, call=self.call, data=data)


def _shorten(body: Any) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return text[:LONGEST_SHOWN]
