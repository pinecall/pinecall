"""A definition as a release keeps it: parsed, dumped, and checked for what no call could run."""

import json
import re
from collections.abc import Collection, Iterator, Sequence
from typing import Any, cast, get_args
from urllib.parse import urlsplit

from runtime.agents.declaration import SAY
from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.session import service as session
from runtime.wire.base import WireModel
from runtime.wire.parts import PlatformTool
from runtime.wire.studio import Definition, Header, HttpTool, Param, ParamType

# The tool data collection adds: the model hands it what the caller said, field by field.
COLLECT = "collect"
# The platform's own tools and argument, which a Studio tool may never be called: each by the name the
# domain that owns it keeps.
RESERVED = frozenset({COLLECT, session.END_CALL, session.CLOCK_TOOL, SAY, *get_args(PlatformTool.__value__)})
# `{{secrets.NAME}}`, `{{call.from}}`, `{{metadata.order}}`: a dotted path, nothing else.
A_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
# A URL's own `{id}`: a parameter of the tool's, filled from the model's arguments.
A_PATH_PARAM = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")
SECRETS = "secrets"
JSON_TYPE: dict[ParamType, str] = {"string": "string", "number": "number", "integer": "integer", "boolean": "boolean"}


def parse(data: bytes) -> Definition:
    """The definition a release holds."""
    try:
        raw: object = json.loads(data)
    except ValueError as unreadable:
        raise ValidationError(f"a Studio release is a definition: {unreadable}") from unreadable
    return Definition.parse(raw, "a Studio release is a definition")


def dump(definition: Definition) -> bytes:
    """The definition as a release keeps it."""
    return definition.model_dump_json(exclude_none=True).encode()


# Refused when it is saved, never discovered on a call: what the shapes alone cannot say.
def check(definition: Definition, secrets: Collection[str], env: Env) -> None:
    """Refuse a definition no call could run: names twice, a URL off TLS, a secret out of a header or `env` lacks."""
    _check_secrets_stay_in_headers(definition)
    names: set[str] = set()
    for tool in definition.tools:
        if tool.name in RESERVED:
            raise ValidationError(f"{tool.name} is the platform's own tool: call yours something else")
        if tool.name in names:
            raise ValidationError(f"two tools are called {tool.name}: a model calls a tool by its name, so each is one")
        names.add(tool.name)
        _check_tool(tool, secrets, env)
    collect = definition.collect
    if collect is None:
        return
    fields: set[str] = set()
    for field in collect.fields:
        if field.name in fields:
            raise ValidationError(f"data collection: two fields are called {field.name}")
        fields.add(field.name)
        _check_values(field, "data collection")
    if collect.send_to is not None:
        _check_url("data collection", collect.send_to)
    for header in collect.headers:
        _check_secrets_are_set(f"data collection's header {header.name}", header.value, secrets, env)


def schema_of(params: Sequence[Param]) -> dict[str, Any]:
    """The parameters as the JSON schema a model is offered a tool with."""
    properties = {
        param.name: {
            "type": JSON_TYPE[param.type],
            **({"description": param.description} if param.description else {}),
            **({"enum": param.enum} if param.enum else {}),
        }
        for param in params
    }
    return {"type": "object", "properties": properties, "required": [param.name for param in params if param.required]}


def _check_tool(tool: HttpTool, secrets: Collection[str], env: Env) -> None:
    where = f"tool {tool.name}"
    _check_url(where, tool.url)
    params: set[str] = set()
    for param in tool.params:
        if param.name in params:
            raise ValidationError(f"tool {tool.name}: two parameters are called {param.name}")
        params.add(param.name)
        _check_values(param, where)
    fixed: set[str] = set()
    for item in tool.fixed:
        if item.name in fixed:
            raise ValidationError(f"tool {tool.name}: two fixed fields are called {item.name}")
        if item.name in params:
            raise ValidationError(
                f"tool {tool.name}: {item.name} is a parameter the model fills and a field fixed here: one or the other"
            )
        fixed.add(item.name)
    for named in A_PATH_PARAM.findall(A_PLACEHOLDER.sub("", tool.url)):
        if named not in params:
            raise ValidationError(f"tool {tool.name}: its URL names {{{named}}}, which is none of its parameters")
    for header in tool.headers:
        _check_secrets_are_set(f"{where}'s header {header.name}", header.value, secrets, env)


def _check_values(param: Param, where: str) -> None:
    if param.enum is not None and param.type != "string":
        raise ValidationError(
            f"{where}: {param.name} lists the values it may take, which a {param.type} cannot: a closed list "
            "is a string's"
        )


def _check_url(where: str, url: str) -> None:
    split = urlsplit(A_PATH_PARAM.sub("x", A_PLACEHOLDER.sub("x", url)))
    if split.scheme != "https" or not split.hostname:
        raise ValidationError(
            f"{where}: {url} is not an https:// URL; Studio reaches the public internet over TLS alone"
        )


# A secret is a header's value and nowhere else: the walk reads every string the definition holds, so
# a field added to it later is covered without anyone remembering to say so.
def _check_secrets_stay_in_headers(definition: Definition) -> None:
    for where, text in _strings(definition, ""):
        for path in A_PLACEHOLDER.findall(text):
            head, _, name = path.partition(".")
            if head == SECRETS:
                raise ValidationError(
                    f"`{where}` names {{{{secrets.{name}}}}} outside a header: a secret travels in a header alone"
                )


# Every string of the definition with the path to it, a header's value excepted.
def _strings(item: object, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(item, str):
        yield path, item
    elif isinstance(item, WireModel):
        for field in type(item).model_fields:
            if not (isinstance(item, Header) and field == "value"):
                yield from _strings(getattr(item, field), f"{path}.{field}" if path else field)
    elif isinstance(item, list):
        for index, entry in enumerate(cast("list[object]", item)):
            named = getattr(entry, "name", None)
            yield from _strings(entry, f"{path}.{named if isinstance(named, str) else index}")


def _check_secrets_are_set(where: str, text: str, secrets: Collection[str], env: Env) -> None:
    for path in A_PLACEHOLDER.findall(text):
        head, _, name = path.partition(".")
        if head == SECRETS and name not in secrets:
            raise ValidationError(
                f"{where} names the secret {name}, which {env.value} has none of: set it there, in Settings ▸ Secrets"
            )
