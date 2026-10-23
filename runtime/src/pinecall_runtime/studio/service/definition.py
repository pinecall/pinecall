"""A definition turned into what an SDK would send: the declaration, the tools, and the prompt's blocks."""

import json
import re
from collections.abc import Collection, Iterator, Mapping
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.studio.schemas import CollectedField, Definition, Header, HttpTool, ParamType
from pinecall_runtime.studio.service import rules
from pinecall_runtime.wire.parts import (
    AgentConfig,
    GreetingConfig,
    HangupConfig,
    StateFieldSpec,
    ToolSpec,
)

# The tool data collection adds: the model hands it what the caller said, field by field.
COLLECT = "collect"
# The hang-up tool the session gives a model that may end the call: its call and its result are the session's.
END_CALL = "end_call"
# The platform's own tools and argument, which a Studio tool may never be called.
RESERVED = frozenset({COLLECT, END_CALL, "current_date", "recall", "search", "say"})
# `{{secrets.NAME}}`, `{{call.from}}`, `{{metadata.order}}`: a dotted path, nothing else.
A_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
# A URL's own `{id}`: a parameter of the tool's, filled from the model's arguments.
A_PATH_PARAM = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")
SECRETS = "secrets"
# When the model may end a call that collects: once it has what it came for.
HANG_UP_WHEN = "once every required field of data collection is in and you have said goodbye"
JSON_TYPE: dict[ParamType, str] = {"string": "string", "number": "number", "integer": "integer", "boolean": "boolean"}

NOT_JSON = "a Studio release is a definition: {why}"
TWO_TOOLS = "two tools are called {name}: a model calls a tool by its name, so each is one"
RESERVED_NAME = "{name} is the platform's own tool: call yours something else"
NOT_HTTPS = "{where}: {url} is not an https:// URL; Studio reaches the public internet over TLS alone"
NO_SUCH_SECRET = "{where} names the secret {name}, which this env has none of: set it in Settings ▸ Secrets"
SECRET_OUTSIDE = "{where} names {{{{secrets.{name}}}}} outside a header: a secret travels in a header alone"
PATH_PARAM_UNDECLARED = "tool {tool}: its URL names {{{param}}}, which is none of its parameters"
TWO_PARAMS = "tool {tool}: two parameters are called {name}"
TWO_FIELDS = "data collection: two fields are called {name}"


def parsed(data: bytes) -> Definition:
    """The definition a release holds."""
    try:
        return Definition.model_validate_json(data)
    except PydanticValidationError as error:
        raise ValidationError(NOT_JSON.format(why=error)) from error


def dumped(definition: Definition) -> bytes:
    """The definition as a release keeps it."""
    return definition.model_dump_json(exclude_none=True).encode()


# Refused when it is saved, never discovered on a call: what the shapes alone cannot say.
def check(definition: Definition, secrets: Collection[str]) -> None:
    """Refuse a definition no call could run: names twice, a URL off TLS, a secret out of a header or this env lacks."""
    _check_secrets_stay_in_headers(definition)
    names: set[str] = set()
    for tool in definition.tools:
        if tool.name in RESERVED:
            raise ValidationError(RESERVED_NAME.format(name=tool.name))
        if tool.name in names:
            raise ValidationError(TWO_TOOLS.format(name=tool.name))
        names.add(tool.name)
        _check_tool(tool, secrets)
    collect = definition.collect
    if collect is None:
        return
    fields: set[str] = set()
    for field in collect.fields:
        if field.name in fields:
            raise ValidationError(TWO_FIELDS.format(name=field.name))
        fields.add(field.name)
    if collect.send_to is not None:
        _check_url("data collection", collect.send_to)
    for header in collect.headers:
        _check_secrets_are_set(f"data collection's header {header.name}", header.value, secrets)


def declaration(definition: Definition) -> AgentConfig:
    """What agent.configure declares: the tools, the greeting, the collected fields, the hang-up."""
    greeting = definition.greeting
    collect = definition.collect
    return AgentConfig(
        greeting=None if greeting is None else GreetingConfig(say=greeting.say, reply=greeting.reply),
        tools=tool_specs(definition),
        state_fields=[]
        if collect is None
        else [StateFieldSpec(name=field.name, visibility="tenant") for field in collect.fields],
        hangup=HangupConfig(when=HANG_UP_WHEN) if collect is not None and collect.end_when_done else None,
    )


def tool_specs(definition: Definition) -> list[ToolSpec]:
    """Every tool as the gateway is told of it: the HTTP ones, and collect when it collects."""
    specs = [
        ToolSpec(
            name=tool.name,
            description=tool.description,
            parameters=_schema(tool.params),
            side_effect="read" if tool.method == "GET" else "write",
            announce=tool.announce,
            timeout_s=tool.timeout_s,
        )
        for tool in definition.tools
    ]
    if definition.collect is not None:
        fields = definition.collect.fields
        specs.append(
            ToolSpec(
                name=COLLECT,
                description=(
                    "Saves what the caller told you, field by field. Call it as soon as the caller gives any of "
                    f"these, with only the ones they gave: {', '.join(field.name for field in fields)}."
                ),
                parameters=_schema([field.model_copy(update={"required": False}) for field in fields]),
                side_effect="write",
                timeout_s=5.0,
            )
        )
    return specs


def tools_block(definition: Definition) -> str:
    """The `tools` block: each tool on a line, its name and what it does, as an SDK writes it."""
    return rules.tagged("tools", "\n".join(f"- {spec.name}: {spec.description}" for spec in tool_specs(definition)))


# The call's values are known when it starts and never change, so the block stays in the cached prefix.
def identity(definition: Definition, values: Mapping[str, Any]) -> str:
    """The instructions, the call's values in their placeholders, then the framework's rules and the channel's."""
    call: Mapping[str, Any] = values.get("call") or {}
    said = [
        rendered(definition.instructions, values),
        rules.tagged("rules", rules.RULES),
        rules.tagged("protocols", rules.PROTOCOLS),
        rules.tagged("channel", rules.channel_rules_for(call.get("channel"), call.get("medium"))),
    ]
    return "\n\n".join(part for part in said if part.strip())


# The one block that changes during a call: what is in, what is missing, and when to close.
def view(definition: Definition, collected: Mapping[str, Any]) -> str:
    """What data collection says this turn; nothing for an agent that collects nothing."""
    collect = definition.collect
    if collect is None:
        return ""
    have = [field for field in collect.fields if field.name in collected]
    missing = [field for field in collect.fields if field.name not in collected]
    lines: list[str] = []
    if have:
        lines.append("Collected so far:")
        lines.extend(f"- {field.name}: {json.dumps(collected[field.name], ensure_ascii=False)}" for field in have)
    if missing:
        lines.append("Still to collect, one question at a time:")
        lines.extend(_wanted(field) for field in missing)
    if all(field.name in collected for field in collect.fields if field.required):
        lines.append(f"Every required field is in. {collect.closing}")
    return "\n".join(lines)


def is_complete(definition: Definition, collected: Mapping[str, Any]) -> bool:
    """Whether every required field is in."""
    collect = definition.collect
    return collect is not None and all(field.name in collected for field in collect.fields if field.required)


def rendered(text: str, values: Mapping[str, Any]) -> str:
    """The text with each `{{a.b}}` filled from the values; one that names nothing is left empty."""

    def filled(found: re.Match[str]) -> str:
        value: object = values
        for part in found.group(1).split("."):
            value = cast("Mapping[str, object]", value).get(part) if isinstance(value, Mapping) else None
            if value is None:
                return ""
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return A_PLACEHOLDER.sub(filled, text)


def _schema(params: list[Any]) -> dict[str, Any]:
    properties = {
        param.name: {"type": JSON_TYPE[param.type], **({"description": param.description} if param.description else {})}
        for param in params
    }
    return {"type": "object", "properties": properties, "required": [param.name for param in params if param.required]}


def _wanted(field: CollectedField) -> str:
    about = f": {field.description}" if field.description else ""
    return f"- {field.name} ({field.type}{', required' if field.required else ', optional'}){about}"


def _check_tool(tool: HttpTool, secrets: Collection[str]) -> None:
    where = f"tool {tool.name}"
    _check_url(where, tool.url)
    params: set[str] = set()
    for param in tool.params:
        if param.name in params:
            raise ValidationError(TWO_PARAMS.format(tool=tool.name, name=param.name))
        params.add(param.name)
    for named in A_PATH_PARAM.findall(A_PLACEHOLDER.sub("", tool.url)):
        if named not in params:
            raise ValidationError(PATH_PARAM_UNDECLARED.format(tool=tool.name, param=named))
    for header in tool.headers:
        _check_secrets_are_set(f"{where}'s header {header.name}", header.value, secrets)


def _check_url(where: str, url: str) -> None:
    split = urlsplit(A_PATH_PARAM.sub("x", A_PLACEHOLDER.sub("x", url)))
    if split.scheme != "https" or not split.hostname:
        raise ValidationError(NOT_HTTPS.format(where=where, url=url))


# A secret is a header's value and nowhere else: the walk reads every string the definition holds, so
# a field added to it later is covered without anyone remembering to say so.
def _check_secrets_stay_in_headers(definition: Definition) -> None:
    for where, text in _strings(definition, ""):
        for path in A_PLACEHOLDER.findall(text):
            head, _, name = path.partition(".")
            if head == SECRETS:
                raise ValidationError(SECRET_OUTSIDE.format(where=f"`{where}`", name=name))


# Every string of the model with the path to it, a header's value excepted.
def _strings(item: object, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(item, str):
        yield path, item
    elif isinstance(item, BaseModel):
        for field in type(item).model_fields:
            if not (isinstance(item, Header) and field == "value"):
                yield from _strings(getattr(item, field), f"{path}.{field}" if path else field)
    elif isinstance(item, list):
        for index, entry in enumerate(cast("list[object]", item)):
            named = getattr(entry, "name", None)
            yield from _strings(entry, f"{path}.{named if isinstance(named, str) else index}")


def _check_secrets_are_set(where: str, text: str, secrets: Collection[str]) -> None:
    for path in A_PLACEHOLDER.findall(text):
        head, _, name = path.partition(".")
        if head == SECRETS and name not in secrets:
            raise ValidationError(NO_SUCH_SECRET.format(where=where, name=name))
