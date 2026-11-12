"""A Studio agent written out as a TypeScript project of the framework's: the class `pinecall deploy` runs."""

import io
import json
import re
import zipfile
from importlib import resources
from string import Template

from runtime.studio.service import collect as collecting
from runtime.studio.service.definition import A_PATH_PARAM, A_PLACEHOLDER, COLLECT
from runtime.wire.studio import Definition, Header, HttpTool, Param, ParamType, Scalar

TS_TYPE: dict[ParamType, str] = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean"}
# What `{{…}}` becomes in the class: the call's own fields, the secrets as the process's environment.
# Only what the framework's `this.call` carries; a value Studio fills that it does not is left empty,
# and the class says where (`_say_left_empty`).
IN_THE_CLASS = {
    "call.from": "this.call.from",
    "call.to": "this.call.to",
    "call.channel": "this.call.channel",
    "call.direction": "this.call.direction",
    "call.today": "this.call.today",
    "caller.name": "this.call.caller?.name",
    "caller.phone": "this.call.caller?.phone",
    "caller.email": "this.call.caller?.email",
}
# `{{metadata.order}}`: a key of what the call was opened with, which `this.call.metadata` holds.
A_METADATA_KEY = re.compile(r"metadata\.(\w+)")
# The project's files that are the same for every agent, beside this module: read once a process.
STATIC = resources.files("runtime.studio") / "export"
# One template literal's pieces: a `{{…}}`, or a URL's own `{id}`.
A_PIECE = re.compile(rf"{A_PLACEHOLDER.pattern}|{A_PATH_PARAM.pattern}")


def zip_project(name: str, release: int, definition: Definition, framework: str) -> bytes:
    """The project zipped: package.json, tsconfig.json, the agent's class, AGENTS.md and a README."""
    files = {
        "package.json": _fill("package.json", name=name, framework=framework),
        "tsconfig.json": _read("tsconfig.json"),
        f"agents/{name}/agent.tsx": write_class(name, release, definition),
        "AGENTS.md": _write_agents_md(name, release, definition),
        "README.md": _fill("README.md", name=name),
        ".gitignore": _read("gitignore"),
    }
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path, text in files.items():
            zipped.writestr(f"{name}/{path}", text)
    return packed.getvalue()


# The class is the same agent: what data collection says, when it hangs up and what it posts at the end
# are written from the words and the fields the gateway itself runs on (`collect`), never typed again.
def write_class(name: str, release: int, definition: Definition) -> str:
    """The agent's class: its instructions, its greeting, a method per tool, and data collection."""
    title = _name_class(name)
    collect = definition.collect
    dynamic = A_PLACEHOLDER.search(definition.instructions) is not None
    above = _list_above_class(definition)
    improvises = definition.greeting is not None and definition.greeting.reply is not None
    names = ["Agent", *(["agent"] if above else []), *(["improvise"] if improvises else []), "tool"]
    lines = [
        f"// {name}: exported from Pinecall Studio, release {release}. The class is the agent now: edit it here.",
        *_say_left_empty(definition),
        "",
        f'import {{ {", ".join(names)} }} from "@pinecall/agents";',
        "",
        _write_docstring(
            "The agent's instructions are its view below: they name the call's own values."
            if dynamic
            else definition.instructions
        ),
        *(["@agent({", *(f"  {field}," for field in above), "})"] if above else []),
        f"export default class {title} extends Agent {{",
    ]
    if collect is not None:
        lines += ["  /** What the caller gave, field by field. */", "  collected: Record<string, unknown> = {};"]
    for http_tool in definition.tools:
        lines += ["", *_write_method(http_tool)]
    if collect is not None:
        lines += ["", *_write_collect(definition)]
        if collect.send_to is not None:
            lines += ["", *_write_on_end(name, definition)]
    lines += ["", *_write_render(definition, dynamic), "}", "", _read("http.ts").rstrip("\n")]
    return "\n".join(lines) + "\n"


# What the agent is goes above its class, in the framework's one declaration: how it opens, and when it hangs up.
def _list_above_class(definition: Definition) -> list[str]:
    above: list[str] = []
    greeting, collect = definition.greeting, definition.collect
    if greeting is not None and greeting.say is not None:
        above.append(f"greeting: {json.dumps(greeting.say, ensure_ascii=False)}")
    elif greeting is not None and greeting.reply is not None:
        above.append(f"greeting: improvise({json.dumps(greeting.reply, ensure_ascii=False)})")
    if collect is not None and collect.end_when_done:
        above.append(f"hangup: {json.dumps(collecting.HANG_UP_WHEN)}")
    return above


# The `{{…}}` Studio filled that `this.call` cannot say: each is empty in the class, and the class says which.
def _say_left_empty(definition: Definition) -> list[str]:
    collect = definition.collect
    templated = [definition.instructions]
    for http_tool in definition.tools:
        templated += [http_tool.url, *(header.value for header in http_tool.headers)]
    if collect is not None:
        templated += [*([] if collect.send_to is None else [collect.send_to]), *(h.value for h in collect.headers)]
    paths = {path for text in templated for path in A_PLACEHOLDER.findall(text)}
    named = sorted(path for path in paths if _read_in_class(path) is None and not path.startswith("secrets."))
    if not named:
        return []
    said = ", ".join("{{" + path + "}}" for path in named)
    return [f"// Studio filled {said} from the call; the class reads no such value, so each is empty below."]


def _read_in_class(placeholder: str) -> str | None:
    if placeholder in IN_THE_CLASS:
        return IN_THE_CLASS[placeholder]
    key = A_METADATA_KEY.fullmatch(placeholder)
    return None if key is None else f"this.call.metadata[{json.dumps(key.group(1))}]"


def _write_method(http_tool: HttpTool) -> list[str]:
    ordered = sorted(http_tool.params, key=lambda param: not param.required)
    signature = ", ".join(f"{param.name}{'' if param.required else '?'}: {_type_of(param)}" for param in ordered)
    options: list[str] = []
    if http_tool.announce:
        options.append(f"announce: {json.dumps(http_tool.announce, ensure_ascii=False)}")
    options.append(f"timeout: {http_tool.timeout_s:g}")
    path_params = set(A_PATH_PARAM.findall(A_PLACEHOLDER.sub("", http_tool.url)))
    rest = [param.name for param in http_tool.params if param.name not in path_params]
    rest += [f"{item.name}: {_write_literal(item.value)}" for item in http_tool.fixed]
    url = _write_template(http_tool.url, paths=True)
    carried = "query" if http_tool.method in ("GET", "DELETE") else "body"
    params_doc = [f"   * @param {param.name} {param.description}".rstrip() for param in http_tool.params]
    return [
        "  /**",
        *_wrap(http_tool.description, "   * "),
        *params_doc,
        "   */",
        *_say_what_has_no_option(http_tool),
        f"  @tool({{ {', '.join(options)} }})",
        f"  async {http_tool.name}({signature}): Promise<unknown> {{",
        f"    return http({json.dumps(http_tool.method)}, {url}, {{",
        f"      {carried}: {{ {', '.join(rest)} }},",
        f"      headers: {_write_headers(http_tool.headers)},",
        f"      timeoutMs: {round(http_tool.timeout_s * 1000)},",
        "    });",
        "  }",
    ]


# A closed list of values is the union of them: the model is offered the same words the class accepts.
def _type_of(param: Param) -> str:
    if not param.enum:
        return TS_TYPE[param.type]
    return " | ".join(json.dumps(value, ensure_ascii=False) for value in param.enum)


# A fixed field as the class writes it: a string is a template (it may name the call's values), the rest JSON.
def _write_literal(value: Scalar) -> str:
    return _write_template(value) if isinstance(value, str) else json.dumps(value)


# The framework's @tool announces a start alone: what Studio said on a long wait or a failure is kept
# as a comment, so whoever edits the class knows what the caller used to hear.
def _say_what_has_no_option(http_tool: HttpTool) -> list[str]:
    said: list[str] = []
    if http_tool.delayed:
        said.append(f"after {http_tool.delayed_after_s:g}s: {json.dumps(http_tool.delayed, ensure_ascii=False)}")
    if http_tool.failed:
        said.append(f"when it failed: {json.dumps(http_tool.failed, ensure_ascii=False)}")
    if not said:
        return []
    return [f"  // Studio said {', and '.join(said)}; the framework has no such option: the model says what it reads."]


def _write_collect(definition: Definition) -> list[str]:
    collect = definition.collect
    assert collect is not None
    signature = ", ".join(f"{field.name}?: {TS_TYPE[field.type]}" for field in collect.fields)
    given = ", ".join(field.name for field in collect.fields)
    required = json.dumps([field.name for field in collect.fields if field.required])
    every = json.dumps([field.name for field in collect.fields])
    return [
        "  /**",
        *_wrap(collecting.describe(collect), "   * "),
        "   */",
        f"  @tool({{ timeout: {collecting.TOOL_TIMEOUT_S:g} }})",
        f"  async {COLLECT}({signature}): Promise<{{ saved: string[]; missing: string[]; complete: boolean }}> {{",
        f"    const given: Record<string, unknown> = {{ {given} }};",
        '    const saved = Object.keys(given).filter((key) => given[key] != null && given[key] !== "").sort();',
        "    this.collected = { ...this.collected, ...Object.fromEntries(saved.map((key) => [key, given[key]])) };",
        f"    const missing = ({every} as string[]).filter((key) => !(key in this.collected));",
        f"    const complete = ({required} as string[]).every((key) => key in this.collected);",
        "    return { saved, missing, complete };",
        "  }",
    ]


# The body the gateway posts (`collect.results`), field for field. The framework hands `onEnd` no
# reason the call ended for, so that one is null here.
def _write_on_end(name: str, definition: Definition) -> list[str]:
    collect = definition.collect
    assert collect is not None and collect.send_to is not None
    required = json.dumps([field.name for field in collect.fields if field.required])
    return [
        "  /** The call's results posted where Studio posted them, once the call is over. */",
        "  override async onEnd() {",
        f"    const complete = ({required} as string[]).every((key) => key in this.collected);",
        f'    await http("POST", {_write_template(collect.send_to)}, {{',
        "      body: {",
        f"        agent: {json.dumps(name)},",
        "        call: this.call.id,",
        "        env: process.env.PINECALL_ENV ?? null,",
        "        from: this.call.from ?? null,",
        "        to: this.call.to ?? null,",
        "        channel: this.call.channel ?? null,",
        "        fields: this.collected,",
        "        complete,",
        "        reason: null,",
        "        transcript: this.call.history.turns.map(({ role, text }) => ({ role, text })),",
        "      },",
        f"      headers: {_write_headers(collect.headers)},",
        f"      timeoutMs: {round(collecting.RESULTS_TIMEOUT_S * 1000)},",
        "    });",
        "  }",
    ]


# The view the gateway writes each turn (`collect.view`), line for line: what is in, what is missing
# with its type, whether it is required, the values it may take and what it is, and when to close.
def _write_render(definition: Definition, dynamic: bool) -> list[str]:
    lines = ["  /** The view: the one block of the prompt that changes between two turns. */", "  override render() {"]
    collect = definition.collect
    if not dynamic and collect is None:
        return [*lines, '    return "";', "  }"]
    parts: list[str] = []
    if dynamic:
        parts.append(f"<p>{{{_write_template(definition.instructions)}}}</p>")
    if collect is not None:
        fields = [{"name": field.name, "wanted": collecting.describe_field(field)} for field in collect.fields]
        required = json.dumps([field.name for field in collect.fields if field.required])
        lines += [
            f"    const fields = {json.dumps(fields, ensure_ascii=False)};",
            "    const have = fields.filter((field) => field.name in this.collected);",
            "    const missing = fields.filter((field) => !(field.name in this.collected));",
            f"    const done = ({required} as string[]).every((key) => key in this.collected);",
            "    const said = (field: { name: string }) =>",
            "      `- ${field.name}: ${JSON.stringify(this.collected[field.name])}`;",
        ]
        have = json.dumps(collecting.HAVE + "\n", ensure_ascii=False)
        still = json.dumps(collecting.MISSING + "\n", ensure_ascii=False)
        closing = json.dumps(collecting.close_with(collect), ensure_ascii=False)
        parts += [
            f'{{have.length > 0 && <p>{{{have} + have.map(said).join("\\n")}}</p>}}',
            f'{{missing.length > 0 && <p>{{{still} + missing.map((field) => field.wanted).join("\\n")}}</p>}}',
            f"{{done && <p>{{{closing}}}</p>}}",
        ]
    return [*lines, "    return (", "      <>", *(f"        {part}" for part in parts), "      </>", "    );", "  }"]


def _write_headers(headers: list[Header]) -> str:
    if not headers:
        return "{}"
    pairs = ", ".join(f"{json.dumps(header.name)}: {_write_template(header.value)}" for header in headers)
    return f"{{ {pairs} }}"


# One template literal: the text escaped, `{{secrets.X}}` the process's environment, `{{call.from}}`
# the call, any other `{{…}}` nothing, and with `paths` a URL's `{id}` the argument, encoded.
def _write_template(text: str, *, paths: bool = False) -> str:
    out: list[str] = []
    at = 0
    for found in A_PIECE.finditer(text):
        placeholder, path_param = found.group(1), found.group(2)
        if path_param is not None and not paths:
            continue
        out.append(_escape(text[at : found.start()]))
        at = found.end()
        if path_param is not None:
            out.append("${encodeURIComponent(String(" + path_param + ' ?? ""))}')
        elif placeholder.startswith("secrets."):
            out.append("${process.env." + placeholder.removeprefix("secrets.") + ' ?? ""}')
        elif (expression := _read_in_class(placeholder)) is not None:
            out.append("${" + expression + ' ?? ""}')
    out.append(_escape(text[at:]))
    return "`" + "".join(out) + "`"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def _write_docstring(text: str) -> str:
    return "\n".join(["/**", *_wrap(text.replace("*/", "* /"), " * "), " */"])


def _wrap(text: str, prefix: str) -> list[str]:
    return [f"{prefix}{line}".rstrip() for line in text.replace("*/", "* /").splitlines() or [""]]


def _name_class(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", name) if part) or "Agent"


def _write_agents_md(name: str, release: int, definition: Definition) -> str:
    collect = definition.collect
    headers = [header for tool in definition.tools for header in tool.headers]
    headers += [] if collect is None else collect.headers
    paths = {path for header in headers for path in A_PLACEHOLDER.findall(header.value)}
    secrets = sorted(path.removeprefix("secrets.") for path in paths if path.startswith("secrets."))
    tools = [f"- `{tool.name}`: {tool.method} {tool.url}. {tool.description}" for tool in definition.tools]
    if collect is not None:
        tools.append(f"- `{COLLECT}`: data collection, the fields kept in `this.collected`")
    return _fill(
        "AGENTS.md",
        name=name,
        release=str(release),
        tools="\n".join(tools) or "- none",
        secrets=", ".join(f"`{secret}`" for secret in secrets) or "none",
    )


def _read(file: str) -> str:
    return (STATIC / file).read_text(encoding="utf-8")


def _fill(file: str, **named: str) -> str:
    return Template(_read(file)).substitute(named)
