"""A definition as an SDK would declare it: the agent's declaration, and its tools as the gateway is told of them."""

from runtime.studio.service import collect as collecting
from runtime.studio.service.definition import schema_of
from runtime.wire.declaration import AgentConfig, GreetingConfig, HangupConfig, StateFieldSpec
from runtime.wire.parts import ToolSpec
from runtime.wire.studio import Definition


def declare(definition: Definition) -> AgentConfig:
    """What agent.configure declares: the tools, the greeting, the collected fields, the hang-up."""
    greeting = definition.greeting
    collect = definition.collect
    return AgentConfig(
        greeting=None if greeting is None else GreetingConfig(say=greeting.say, reply=greeting.reply),
        tools=list_tool_specs(definition),
        state_fields=[]
        if collect is None
        else [StateFieldSpec(name=field.name, visibility="tenant") for field in collect.fields],
        hangup=HangupConfig(when=collecting.HANG_UP_WHEN) if collect is not None and collect.end_when_done else None,
    )


def list_tool_specs(definition: Definition) -> list[ToolSpec]:
    """Every tool as the gateway is told of it: the HTTP ones, and collect when it collects."""
    specs = [
        ToolSpec(
            name=tool.name,
            description=tool.description,
            parameters=schema_of(tool.params),
            side_effect="read" if tool.method == "GET" else "write",
            announce=tool.announce,
            delayed=tool.delayed,
            delayed_after_s=tool.delayed_after_s,
            failed=tool.failed,
            timeout_s=tool.timeout_s,
        )
        for tool in definition.tools
    ]
    if definition.collect is not None:
        specs.append(collecting.tool_spec(definition.collect))
    return specs
