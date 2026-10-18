# Getting started

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `whoami`

Which org, gateway and environment the open project's key acts in, and whether production is allowed.

`whoami` first, in any session: it proves the project's key and names the org. Refused with a sentence naming `login` when this machine is signed in nowhere; with `prod`, it says whether the key may act in production.

| parameter | takes | | what it is |
|---|---|---|---|
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{}
```

```json title="answered"
{
  "org": "acme",
  "gateway": "https://cloud.pinecall.io",
  "environment": "sandbox",
  "key_from": ".env",
  "person": "Ana",
  "production_allowed_for_this_key": true
}
```

## `login`

Sign this machine in to a gateway: `start` returns a link for the person to open; `status` waits for their approval.

`login` signs this machine in, once per gateway: `start` answers a link — show it to the person, who signs in there, in a browser, where a password belongs — then call `status` until it says signed in. Every tool runs on that sign-in, in the org the project's pinecall.json names; the person may belong to several. No password and no key ever passes through you. A runtime on this machine (`runtime` up) signs it in by itself.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `start` · `status` | required | start opens a sign-in and answers its link; status waits for the person to approve it |
| `gateway` | text |  | the gateway to sign in to; Pinecall Cloud when left out |
| `wait_s` | a whole number 0–50 |  | how long to wait before answering what is known so far, in seconds; 25 when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "status",
  "wait_s": 0
}
```

```json title="answered"
{
  "signed_in": false,
  "says": "nothing in flight: call login with action start"
}
```

## `project`

The project the tools act on (`show`), another folder opened (`open`), a new project written (`new`), or an agent or a golden added to it (`generate`).

`project show` says which folder every tool acts on: its agents, their language, and whether it has a key. The host's declared root, or the server's folder, is used when it holds `agents/`; `open` points at another, with nothing held. `new` writes a project — the business, named by `name` — and opens it, and its pinecall.json names the gateway this machine is signed in to and the org it runs in: the person's only one, or the `org` they name (with several and none named, `new` answers their slugs and writes nothing — ask the person); with `agent` it writes its first agent too, under `agents/<agent>/` (a receptionist that takes a message, its test and one golden); a TypeScript one runs at once on the framework this server lends it until `npm install` pins its own, a Ruby one after `bundle install`, a Python one after `uv sync`. `generate` adds to the open project, never over a file: `agent` an agent's folder under `agents/<name>/` (its class, its test, one golden), `golden` a conversation in `agents/<agent>/test/goldens/`: a turn for each of the caller's lines (`say`) and the tools the call must make (`tools`, its `expect`). What must follow each turn — its `then`: a tool with its arguments, a reply and its intent, the end — is added to the file by hand (docs.pinecall.io/concepts/golden-expectations); then `test run` holds the agent to it.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `open` · `new` · `generate` | required | show the project the tools act on; open another folder; new writes a project, and its first agent with `agent`; generate adds an agent or a golden to it |
| `path` | text |  | `open`: the project's folder; `new`: the folder to write it in, beside the open project when left out |
| `name` | text |  | `new`: the project's name; `generate`: the agent's or the golden's: lowercase letters, digits and dashes |
| `language` | `typescript` · `ruby` · `python` |  | `new` and `generate agent`: the agent's language; TypeScript for `new`, the project's for `generate` |
| `kind` | `agent` · `golden` |  | `generate`: one more agent, or one more golden of an agent |
| `say` | a list of texts |  | `generate golden`: what the caller says, one line a turn, in order |
| `tools` | a list of texts |  | `generate golden`: the tools that must be called |
| `agent` | text |  | `new`: the first agent, under agents/<agent>/; `generate golden`: whose golden, the project's only agent when left out |
| `org` | text |  | `new`: the org it runs in, when the person belongs to several; asked of the person, never guessed |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "show"
}
```

```json title="answered"
{
  "root": "/Users/you/front-desk",
  "agents": [
    {
      "name": "front-desk",
      "language": "typescript"
    }
  ],
  "key": "from your sign-in (/Users/you/.pinecall/session.json)",
  "gateway": "https://cloud.pinecall.io",
  "org": "acme",
  "installed": true
}
```

```json title="called with"
{
  "action": "new",
  "name": "front-desk",
  "language": "python"
}
```

```json title="answered"
{
  "root": "/Users/you/front-desk",
  "agents": [
    {
      "name": "front-desk",
      "language": "python"
    }
  ],
  "key": "from your sign-in (/Users/you/.pinecall/session.json)",
  "gateway": "https://cloud.pinecall.io",
  "org": "acme",
  "installed": false,
  "runs": {
    "gateway": "https://cloud.pinecall.io",
    "org": "acme"
  },
  "next": "uv sync in /Users/you/front-desk, then `start`"
}
```

## `runtime`

The runtime on this machine: `up` runs `pinecall-runtime setup` (Docker, the schema, a key the CLI finds by itself, open models), `status` says what it printed and whether it answers, `down` stops it.

`runtime` is for a person with no Pinecall account who wants the runtime on their own machine: `up` runs `pinecall-runtime setup --yes`, which brings Postgres, Redis and LiveKit up in Docker, writes the schema, signs this machine in to it as its admin, in `~/.pinecall/session.json` (so `whoami`, `chat`, `test` and `start` work with no `login`) and, with local models, pulls Ollama, Whisper and Kokoro once — minutes, the first time. It answers within `wait_s` with the lines printed so far; call `status` until a line says ready, then `whoami`. `down` stops the gateway and the worker and the services; the database and the key are kept. A project runs where its pinecall.json says: a project made while the runtime runs here names it.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `status` · `up` · `down` | required | status reads the runtime this server started, or the one `pinecall-runtime setup` left; up runs it and keeps it running; down stops it |
| `models` | `local` · `keys` · `none` |  | up: local runs open models on this machine, no account (the default); keys reads the vendors' keys from the environment; none leaves the providers row |
| `chat_only` | true or false |  | up: written calls alone — no LiveKit, no worker, no ears, no voice; the cheapest first run |
| `llm` | text |  | up, with local models: the Ollama model to think with |
| `wait_s` | a whole number 0–50 |  | how long to wait before answering what is known so far, in seconds; 25 when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

## `team`

The org's people (`list`), or a one-use link that lets one of them choose a new password (`reset`).

`team` lists the org's people, and for `reset` answers a one-use link the person opens to choose their own password: no password ever passes through you. Show the link to that person alone. Setting a password directly is `pinecall team password <email>` in a terminal, where it is typed without echo.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `list` · `reset` | required | list the org's people; reset makes a one-use link for one of them to choose their password |
| `email` | text |  | reset: the person's address |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |
