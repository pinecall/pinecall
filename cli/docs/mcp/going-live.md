# Going live, and the docs

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `deploy`

Run the project on Pinecall: a release uploaded and followed until live; the apps, their releases, their logs, a rollback, stop and start.

`deploy` uploads the project as a release — what its `.gitignore` files leave in, never `node_modules`, `.venv`, `.git`, `dist` or any `.env` — and Pinecall installs it and starts its agents; the release before keeps answering until the new one's agents register, so no call is cut. It follows the release for `wait_s` and answers whether it is live or why it failed; `wait` follows it further. `logs` reads the app's last lines. TypeScript and Python projects, one language each. Removing an app is never a tool: `pinecall deploy rm` in a terminal.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `deploy` · `wait` · `list` · `releases` · `logs` · `rollback` · `stop` · `start` | required | deploy uploads the project as a release; wait follows one further; list the org's apps; releases of one app; logs of its process; rollback sends a release's sources again; stop and start its process |
| `name` | text |  | the app's name; the project folder's when left out |
| `note` | text |  | `deploy`: a note kept with the release |
| `release` | a whole number 1 or more |  | `wait`: the release to wait for; `rollback`: the release whose sources are sent again |
| `wait_s` | a whole number 0–50 |  | how long to wait before answering what is known so far, in seconds; 25 when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "list"
}
```

```json title="answered"
{
  "apps": []
}
```

## `docs_search`

Search Pinecall's own docs (docs.pinecall.io) and answer the sections that best match, each with its address and a snippet.

`docs_search` finds the sections of docs.pinecall.io that answer a question — a verb, a decorator, a setting, a judge — each with its address. Read the page whole with `get_doc` before writing code from it: a snippet has no imports and no caveats.

| parameter | takes | | what it is |
|---|---|---|---|
| `question` | text | required | what you want to know, in a few words |
| `limit` | a whole number 1–10 |  | how many sections, the best first; 5 when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "question": "how does a tool confirm with the caller",
  "limit": 2
}
```

```json title="answered"
{
  "found": [
    {
      "title": "Tools",
      "section": "Confirmation",
      "url": "https://docs.pinecall.io/concepts/tools/#confirmation",
      "score": 22.5,
      "snippet": "`confirm` is a receipt. Once the tool has run, Pinecall fills the sentence and says it, word for word, before the model replies. `{{name}}` is filled from an argument, and `{{result.when}}` from the tool's return value: ```ts @tool({ stage:…"
    },
    {
      "title": "Commands",
      "section": "",
      "url": "https://docs.pinecall.io/wire/commands/",
      "score": 19.72,
      "snippet": "…eclare or change what the agent is: voice, models, language, greeting, the full tool list. | | `agent.drain` | agent | `agent.draining` | This socket is leaving: hand it no new call for the agent, move the live calls it holds to the newest…"
    }
  ]
}
```

## `get_doc`

Read one page of docs.pinecall.io whole, by its address or its path (such as concepts/tools).

`get_doc` reads a page of the docs whole, as Markdown, by the address `docs_search` answered or by its path.

| parameter | takes | | what it is |
|---|---|---|---|
| `page` | text | required | the page's address, or its path on the site |
| `offset` | a whole number 0 or more |  | where to start reading a long page, in characters |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "page": "concepts/tools"
}
```

```json title="answered"
{
  "title": "Tools",
  "url": "https://docs.pinecall.io/concepts/tools/",
  "body": "(below)"
}
```

```text title="body"
A method the model may call: its docstring, its arguments, confirmation, masking and timeouts.

A tool is a method the model may call. You write its description as a docstring and its arguments
as the method's parameters; Pinecall builds the schema, runs the call and logs it.

## What is a tool?

A method decorated with `@tool()`. When the model calls it, the method runs in your process with
the arguments the model gave, and what it returns is what the model reads next.

```ts title="agents/clinica-norte/agent.tsx"
/** Free slots on one day, for one specialty. Always call it for a day the patient names. */
@tool({ stage: ["choose", "book"], preview: 2 })
async freeSlots(day: string, specialty: string): Promise<Slot[]> {
  const date = dayNamed(day, this.call.today ?? "");
  if (!date) throw new NotADay(day);
  this.slots = await this.agenda().free(date, specialty);
  this.stage = this.sl
…
```
