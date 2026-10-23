# Knowledge and memory

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `docs`

The documents the agent searches: a folder pushed into a base and pulled back from it, attached to the agent, held to its golden; the org's bases and who reads them.

The folder `agents/<agent>/docs/` is a checkout of the base. `docs push` writes its Markdown into the base by path and keeps the base's other files, so a document added in the console survives (a `README.md` at the folder's root is never sent: it describes the folder); push again after every edit. `pull` writes the base back into the folder, file by file — written, unchanged, or the folder's own and kept — so what was added in the console reaches the repository. `attach` makes the agent search the base before every turn; `eval` scores the questions in `agents/<agent>/test/goldens/docs.json` against it (recall@k, nDCG@10, by code). `list` and `attached` are the org's, and name no agent. Dropping a base, or one file of it, is never a tool: `pinecall docs drop` and `pinecall docs rm` in a terminal.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `push` · `pull` · `list` · `eval` · `attach` · `detach` · `attached` | required | push writes the agent's docs folder into its base, the base's other files kept; pull writes the base into the folder; list the org's bases; eval scores the docs golden; attach a base to the agent; detach it; attached says which agents read which base |
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `base` | text |  | the base's name; the agent's own when left out |
| `language` | text |  | `push`: the language the files are written in (en, es, pt, fr, de, it, nl); counted from their words when left out |
| `k` | a whole number 1–50 |  | `attach` and `eval`: how many chunks a turn reads |
| `mode` | `retrieved` · `tool` |  | `attach`: searched before every turn, or a tool the model calls |
| `min_score` | a number 0–1 |  | `attach`: chunks under this share of the best one are dropped |
| `team` | true or false |  | `attach` and `detach`: in the team's settings instead of your own |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "push"
}
```

```json title="answered"
{
  "base": "front-desk",
  "chunks": 9,
  "language": "english",
  "took_ms": 213.4,
  "kept": 1,
  "files": 2,
  "readme_skipped": true
}
```

```json title="called with"
{
  "action": "pull"
}
```

```json title="answered"
{
  "base": "front-desk",
  "dir": "/Users/you/front-desk/agents/front-desk/docs",
  "kept": true,
  "files": [
    {
      "path": "hours.md",
      "file": "/Users/you/front-desk/agents/front-desk/docs/hours.md",
      "status": "unchanged"
    },
    {
      "path": "insurance.md",
      "file": "/Users/you/front-desk/agents/front-desk/docs/insurance.md",
      "status": "written"
    },
    {
      "path": "old-prices.md",
      "file": "/Users/you/front-desk/agents/front-desk/docs/old-prices.md",
      "status": "kept"
    }
  ],
  "said": [
    "agents/front-desk/docs/hours.md       unchanged",
    "agents/front-desk/docs/insurance.md   written",
    "agents/front-desk/docs/old-prices.md  not in the base (kept)"
  ]
}
```

## `memory`

What the agent remembers about a caller, what it is told to keep and never keep, and the recall golden held against it.

`memory policy` says what the agent keeps about a caller (`remember`) and never keeps (`forget`); with neither it reads them, and with no policy the agent remembers nothing. `show` reads what it kept about one caller, and names no agent; `eval` scores `agents/<agent>/test/goldens/memory.json`. Forgetting a caller is never a tool: `pinecall memory forget` in a terminal.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `policy` · `eval` | required | show what memory kept about `contact`; policy reads, or with remember/forget writes, what the agent keeps; eval scores the memory golden |
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `contact` | text |  | `show`: the caller, by number or id |
| `remember` | a list of texts |  | `policy`: what is worth keeping about a caller, in your own words, one phrase each |
| `forget` | a list of texts |  | `policy`: what is never kept |
| `k` | a whole number 1–50 |  | `eval`: how many facts a turn recalls |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "policy",
  "remember": [
    "what they ordered",
    "how they prefer to be called back"
  ],
  "forget": [
    "card numbers"
  ]
}
```

```json title="answered"
{
  "agent": "front-desk",
  "remember": [
    "what they ordered",
    "how they prefer to be called back"
  ],
  "forget": [
    "card numbers"
  ]
}
```

## `remember`

Hold memory's writing to its cases: each written call in agents/<agent>/test/memory/ run through one extraction, and what it kept checked by code.

`remember` runs the extraction cases under `agents/<agent>/test/memory/` — a written call and what memory must and must never keep from it — on the model and policy of the agent wherever it is held (the copy `start` holds when it holds it in the env asked), scored by code. Nothing is started.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `grep` | text |  | only cases whose name holds this |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{}
```

```json title="answered"
{
  "agent": "front-desk",
  "model": "anthropic/claude-haiku-5-5",
  "cases": 1,
  "held": 1,
  "took_ms": 1027.29,
  "results": [
    {
      "name": "keeps the order number and never the card",
      "held": true,
      "wrote": [
        "add · what they ordered · Order 4471 arrived broken.",
        "add · how they prefer to be called back · Prefers to be called Mr Baker."
      ],
      "broke": []
    }
  ]
}
```
