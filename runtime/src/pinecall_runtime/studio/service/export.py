"""A Studio agent written out as a TypeScript project of the framework's: the class `pinecall deploy` runs."""

import io
import json
import re
import zipfile
from typing import Any

from pinecall_runtime.studio.schemas import Definition, Header, HttpTool, ParamType
from pinecall_runtime.studio.service.definition import A_PLACEHOLDER, COLLECT

TS_TYPE: dict[ParamType, str] = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean"}
# What `{{…}}` becomes in the class: the call's own fields, the secrets as the process's environment.
IN_THE_CLASS = {"call.from": "this.call.from", "call.channel": "this.call.channel", "call.today": "this.call.today"}
GITIGNORE = "node_modules/\n.env\n"


def project_of(name: str, release: int, definition: Definition, framework: str) -> bytes:
    """The project zipped: package.json, tsconfig.json, the agent's class, AGENTS.md and a README."""
    files = {
        "package.json": _package(name, framework),
        "tsconfig.json": _tsconfig(),
        f"agents/{name}/agent.tsx": class_of(name, release, definition),
        "AGENTS.md": _agents_md(name, release, definition),
        "README.md": _readme(name),
        ".gitignore": GITIGNORE,
    }
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path, text in files.items():
            zipped.writestr(f"{name}/{path}", text)
    return packed.getvalue()


def class_of(name: str, release: int, definition: Definition) -> str:
    """The agent's class: its instructions, its greeting, a method per tool, and data collection."""
    title = _class_name(name)
    collect = definition.collect
    dynamic = A_PLACEHOLDER.search(definition.instructions) is not None
    lines = [
        f"// {name}: exported from Pinecall Studio, release {release}. The class is the agent now: edit it here.",
        "",
        f'import {{ Agent, {"improvise, " if _improvised(definition) else ""}tool }} from "@pinecall/agents";',
        "",
        _docstring(
            "The agent's instructions are its view below: they name the call's own values."
            if dynamic
            else definition.instructions,
            indent="",
        ),
        f"export default class {title} extends Agent {{",
    ]
    greeting = definition.greeting
    if greeting is not None and greeting.say is not None:
        lines.append(f"  static override greeting = {json.dumps(greeting.say, ensure_ascii=False)};")
    elif greeting is not None and greeting.reply is not None:
        lines.append(f"  static override greeting = improvise({json.dumps(greeting.reply, ensure_ascii=False)});")
    if collect is not None:
        if collect.end_when_done:
            lines.append(
                '  static override hangup = "once every required field is collected and you have said goodbye";'
            )
        lines += ["", "  /** What the caller gave, field by field. */", "  collected: Record<string, unknown> = {};"]
    for http_tool in definition.tools:
        lines += ["", *_method(http_tool)]
    if collect is not None:
        lines += ["", *_collect_method(definition)]
        if collect.send_to is not None:
            lines += ["", *_on_end(definition)]
    lines += ["", *_render(definition, dynamic), "}", "", *_http_helper()]
    return "\n".join(lines) + "\n"


def _method(http_tool: HttpTool) -> list[str]:
    ordered = sorted(http_tool.params, key=lambda param: not param.required)
    signature = ", ".join(f"{param.name}{'' if param.required else '?'}: {TS_TYPE[param.type]}" for param in ordered)
    options: list[str] = []
    if http_tool.announce:
        options.append(f"announce: {json.dumps(http_tool.announce, ensure_ascii=False)}")
    options.append(f"timeout: {http_tool.timeout_s:g}")
    path_params = set(re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", A_PLACEHOLDER.sub("", http_tool.url)))
    rest = [param.name for param in http_tool.params if param.name not in path_params]
    url = _template(http_tool.url, paths=True)
    carried = "query" if http_tool.method in ("GET", "DELETE") else "body"
    params_doc = [f"   * @param {param.name} {param.description}".rstrip() for param in http_tool.params]
    return [
        "  /**",
        *_wrapped(http_tool.description, "   * "),
        *params_doc,
        "   */",
        f"  @tool({{ {', '.join(options)} }})",
        f"  async {http_tool.name}({signature}): Promise<unknown> {{",
        f"    return http({json.dumps(http_tool.method)}, {url}, {{",
        f"      {carried}: {{ {', '.join(rest)} }},",
        f"      headers: {_headers(http_tool.headers)},",
        f"      timeoutMs: {round(http_tool.timeout_s * 1000)},",
        "    });",
        "  }",
    ]


def _collect_method(definition: Definition) -> list[str]:
    collect = definition.collect
    assert collect is not None
    signature = ", ".join(f"{field.name}?: {TS_TYPE[field.type]}" for field in collect.fields)
    given = ", ".join(field.name for field in collect.fields)
    required = json.dumps([field.name for field in collect.fields if field.required])
    every = json.dumps([field.name for field in collect.fields])
    return [
        "  /**",
        *_wrapped(
            "Saves what the caller told you, field by field. Call it as soon as the caller gives any of these, "
            f"with only the ones they gave: {', '.join(field.name for field in collect.fields)}.",
            "   * ",
        ),
        "   */",
        "  @tool({ timeout: 5 })",
        f"  async {COLLECT}({signature}): Promise<{{ saved: string[]; missing: string[]; complete: boolean }}> {{",
        f"    const given: Record<string, unknown> = {{ {given} }};",
        '    const saved = Object.keys(given).filter((key) => given[key] !== undefined && given[key] !== "");',
        "    this.collected = { ...this.collected, ...Object.fromEntries(saved.map((key) => [key, given[key]])) };",
        f"    const missing = ({every} as string[]).filter((key) => !(key in this.collected));",
        f"    const complete = ({required} as string[]).every((key) => key in this.collected);",
        "    return { saved, missing, complete };",
        "  }",
    ]


def _on_end(definition: Definition) -> list[str]:
    collect = definition.collect
    assert collect is not None and collect.send_to is not None
    return [
        "  /** The fields posted where Studio posted them, once the call is over. */",
        "  override async onEnd() {",
        f'    await http("POST", {_template(collect.send_to)}, {{',
        "      body: { call: this.call.id, from: this.call.from, fields: this.collected },",
        f"      headers: {_headers(collect.headers)},",
        "      timeoutMs: 10000,",
        "    });",
        "  }",
    ]


def _render(definition: Definition, dynamic: bool) -> list[str]:
    lines = ["  /** The view: the one block of the prompt that changes between two turns. */", "  override render() {"]
    collect = definition.collect
    if not dynamic and collect is None:
        return [*lines, '    return "";', "  }"]
    parts: list[str] = []
    if dynamic:
        parts.append(f"<p>{{{_template(definition.instructions)}}}</p>")
    if collect is not None:
        fields = json.dumps([field.name for field in collect.fields])
        required = json.dumps([field.name for field in collect.fields if field.required])
        closing = json.dumps(f"Every required field is in. {collect.closing}", ensure_ascii=False)
        lines += [
            f"    const missing = ({fields} as string[]).filter((key) => !(key in this.collected));",
            f"    const done = ({required} as string[]).every((key) => key in this.collected);",
        ]
        parts += [
            "<p>Collected so far: {JSON.stringify(this.collected)}</p>",
            '{missing.length > 0 && <p>Still to collect, one question at a time: {missing.join(", ")}</p>}',
            f"{{done && <p>{{{closing}}}</p>}}",
        ]
    return [*lines, "    return (", "      <>", *(f"        {part}" for part in parts), "      </>", "    );", "  }"]


def _http_helper() -> list[str]:
    return [
        "/** One request to the business's API: the query or the JSON body, its answer as JSON when it is JSON. */",
        "async function http(",
        "  method: string,",
        "  url: string,",
        "  { query, body, headers, timeoutMs }: {",
        "    query?: Record<string, unknown>;",
        "    body?: Record<string, unknown>;",
        "    headers: Record<string, string>;",
        "    timeoutMs: number;",
        "  },",
        "): Promise<unknown> {",
        "  const target = new URL(url);",
        "  for (const [key, value] of Object.entries(query ?? {})) {",
        "    if (value !== undefined) target.searchParams.set(key, String(value));",
        "  }",
        "  const sent = body === undefined ? undefined : JSON.stringify(body);",
        "  const answer = await fetch(target, {",
        "    method,",
        '    headers: sent === undefined ? headers : { ...headers, "content-type": "application/json" },',
        "    body: sent,",
        '    redirect: "manual",',
        "    signal: AbortSignal.timeout(timeoutMs),",
        "  });",
        "  const text = await answer.text();",
        "  let read: unknown = text;",
        "  try {",
        '    read = text === "" ? null : JSON.parse(text);',
        "  } catch {",
        "    // Not JSON: the model reads the text as it came.",
        "  }",
        "  if (!answer.ok) throw new Error(`answered ${answer.status}: ${text.slice(0, 2000)}`);",
        "  return read;",
        "}",
    ]


def _headers(headers: list[Header]) -> str:
    if not headers:
        return "{}"
    pairs = ", ".join(f"{json.dumps(header.name)}: {_template(header.value)}" for header in headers)
    return f"{{ {pairs} }}"


# One template literal: the text escaped, `{{secrets.X}}` the process's environment, `{{call.from}}`
# the call, any other `{{…}}` nothing, and with `paths` a URL's `{id}` the argument, encoded.
A_PIECE = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}|\{([A-Za-z][A-Za-z0-9_]*)\}")


def _template(text: str, *, paths: bool = False) -> str:
    out: list[str] = []
    at = 0
    for found in A_PIECE.finditer(text):
        placeholder, path_param = found.group(1), found.group(2)
        if path_param is not None and not paths:
            continue
        out.append(_escaped(text[at : found.start()]))
        at = found.end()
        if path_param is not None:
            out.append("${encodeURIComponent(String(" + path_param + ' ?? ""))}')
        elif placeholder.startswith("secrets."):
            out.append("${process.env." + placeholder.removeprefix("secrets.") + ' ?? ""}')
        elif placeholder in IN_THE_CLASS:
            out.append("${" + IN_THE_CLASS[placeholder] + ' ?? ""}')
    out.append(_escaped(text[at:]))
    return "`" + "".join(out) + "`"


def _escaped(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def _docstring(text: str, *, indent: str) -> str:
    return "\n".join([f"{indent}/**", *_wrapped(text.replace("*/", "* /"), f"{indent} * "), f"{indent} */"])


def _wrapped(text: str, prefix: str) -> list[str]:
    return [f"{prefix}{line}".rstrip() for line in text.replace("*/", "* /").splitlines() or [""]]


def _improvised(definition: Definition) -> bool:
    return definition.greeting is not None and definition.greeting.reply is not None


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", name) if part) or "Agent"


def _package(name: str, framework: str) -> str:
    body: dict[str, Any] = {
        "name": name,
        "version": "0.0.0",
        "private": True,
        "type": "module",
        "scripts": {"lint": "tsc -p tsconfig.json"},
        "dependencies": {"@pinecall/agents": framework},
        "devDependencies": {"@types/node": "^26.4.1", "typescript": "^7.0.2"},
    }
    return json.dumps(body, indent=2) + "\n"


def _tsconfig() -> str:
    body = {
        "extends": "@pinecall/agents/tsconfig.tenant.json",
        "compilerOptions": {"noEmit": True, "types": ["node"]},
        "include": ["agents"],
    }
    return json.dumps(body, indent=2) + "\n"


def _agents_md(name: str, release: int, definition: Definition) -> str:
    secrets = sorted(
        {
            path.removeprefix("secrets.")
            for text in [
                *(header.value for tool in definition.tools for header in tool.headers),
                *(header.value for header in (definition.collect.headers if definition.collect else [])),
            ]
            for path in A_PLACEHOLDER.findall(text)
            if path.startswith("secrets.")
        }
    )
    tools = "\n".join(f"- `{tool.name}`: {tool.method} {tool.url}. {tool.description}" for tool in definition.tools)
    return f"""# {name}

A Pinecall agent exported from Studio (release {release}). `agents/{name}/agent.tsx` is the whole agent:
its docstring and `render()` are the prompt, each `@tool` method a request to the business's API.

## Tools

{tools or "- none"}
{"- `collect`: data collection, the fields kept in `this.collected`" if definition.collect else ""}

## Secrets

The process reads them from its environment: {", ".join(f"`{s}`" for s in secrets) or "none"}. On Pinecall
they are the org's secrets (`pinecall secrets set`), the same Studio used.

## Run it

- `npm install`, then `pinecall start` holds it from this machine; `pinecall chat` talks to it.
- `pinecall deploy` runs it on Pinecall. Once it answers, remove the Studio agent of the same name in the
  console: a slug is one agent.

Read https://docs.pinecall.io before changing the class: tools, state, the view and goldens are there.
"""


def _readme(name: str) -> str:
    return f"""# {name}

Exported from Pinecall Studio. `npm install`, then `pinecall start` to run it here or `pinecall deploy`
to run it on Pinecall. `AGENTS.md` says what the agent is, for you and for a coding assistant.
"""
