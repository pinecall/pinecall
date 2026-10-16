# Architecture — `pinecall`, the CLI

What this package is, file by file: every module of `src/` with the line it opens with. The
convention every file follows is [CONTRIBUTING.md](CONTRIBUTING.md); every verb, from the user's
side, is [docs/the-cli.md](docs/the-cli.md). Reply to the human in Spanish; everything here in English.

## 1. Where it sits

The CLI is a client of the gateway's endpoints and of nothing else, and it never loads an agent's
class: it starts the class's language's serve entry in a child process and drives it through the
gateway. So one CLI serves a TypeScript project, a Ruby one and a Python one alike. It reaches the
framework two ways only: it **imports** `@pinecall/agents/client` (the socket, signed requests, the
feed) and `@pinecall/agents/wire` (the runtime's shapes) — never `@pinecall/agents` bare, never
`/serve`; and `start` (and `prompt`, which prints and leaves) **starts** a serve entry, its door in
`PINECALL_URL`, `PINECALL_KEY` and `PINECALL_ENV`, never in its argv.

## 2. The shape

```
main.ts ─► program.ts ─► <domain>/commands.ts ─► <domain>/service.ts ─► api/<domain>.ts ─► the gateway
                               │                        │
                               └─► <domain>/render.ts    └─► project/, kit/, lower domains' service
mcp/tools/<domain>.ts ─────────────────────────────────┘
```

A verb parses its flags into a zod input, calls one service function with the `Context`, and hands
the data to `ctx.io.result(data, render)`: the object under `--json`, the lines otherwise. An MCP
tool calls the same service with the same input schema. The `Context` (`context.ts`) resolves the
project's credentials and gateway once, on first use; `main.ts` is the one place an error becomes an
exit code (0 did it · 1 refused or failed · 2 the arguments or the settings · 130 stopped).

The domains, bottom up, each importing only the domains below it (their `service`, or their `render`
for a mark two terminals write the same way):

```
billing · accounts · providers · agents · knowledge · telephony · judging · calls · evals · hosting · alerts · scaffold · dev · mcp
```

## 3. The tree

### The entry and the foundations

| file | lines | what it is |
|---|---|---|
| `context.ts` | 94 | What a verb runs with: its IO, its env, and the project and gateway it asks for, resolved once on first use. |
| `errors.ts` | 42 | Every error the CLI throws, each carrying the exit code `main.ts` answers with. |
| `main.ts` | 82 | The entry: the program is run, and every error becomes one sentence and an exit code. |
| `program.ts` | 56 | The command tree on one screen: the global flags, and one `register` call per domain. |
| `version.ts` | 9 | The version this CLI was published as: its own package.json's. |

### `kit/` — the toolkit, no business noun

| file | lines | what it is |
|---|---|---|
| `kit/browser.ts` | 24 | Open a URL in the platform's default browser, best effort. |
| `kit/confirm.ts` | 10 | A yes-or-no question asked of the person at the terminal, before something that cannot be undone. |
| `kit/dotenv.ts` | 54 | Find, read and write a project's `.env` file. |
| `kit/ear.ts` | 56 | A program that joins a LiveKit room, mixes its audio tracks and writes raw PCM to fd 3; spawned by the listening service. |
| `kit/editor.ts` | 30 | The person's own editor, opened on a text and waited for: the one place the CLI starts $EDITOR. |
| `kit/flags.ts` | 20 | A flag's text as commander hands it, read into the value a service takes; a bad one is a usage error naming the flag. |
| `kit/format.ts` | 55 | The one way a date, an amount, a duration, a count or a verdict's mark is written for a terminal. |
| `kit/git.ts` | 14 | What git says about a file: the one place the CLI asks it. |
| `kit/hostname.ts` | 12 | The machine label shown on keys minted for this terminal. |
| `kit/io.ts` | 124 | Where a verb writes: results on stdout, everything a person reads while waiting on stderr. |
| `kit/json-file.ts` | 21 | A JSON file named on the command line, read with errors that name the flag and the file. |
| `kit/keyvalue.ts` | 23 | `key=value` pairs as a repeated flag names them, each value read as JSON when it parses and as text otherwise. |
| `kit/player.ts` | 54 | The audio players a machine might have, the first one on the PATH, and a file played on it: the one place audio is played. |
| `kit/stdin.ts` | 53 | Terminal input: a secret without echo, or the lines of a pipe. A key never lands in argv or the scrollback. |
| `kit/table.ts` | 28 | Rows as aligned columns: the one table a verb prints. |
| `kit/tarball.ts` | 93 | A project as a release: its files, never its secrets or its dependencies, as a gzipped tarball. |

### `api/` — the gateway, the only place `fetch` and `/v1/` appear

| file | lines | what it is |
|---|---|---|
| `api/accounts.ts` | 88 | The accounts endpoints: who a key is, the sign-in pairing, the person's orgs, the console's login codes, the org's secrets. |
| `api/agents.ts` | 159 | The agents endpoints: an agent's settings and their versions, its lexicon, its pipeline, the apps holding it, and a vendor's voices. |
| `api/alerts.ts` | 90 | The alerts endpoints: monitors, the org's webhook, its telemetry collector. |
| `api/billing.ts` | 32 | The billing endpoint: what the org may use in an env and what it used. |
| `api/calls.ts` | 119 | The calls endpoints: an agent's calls, one call's state, its log paged or followed, the supervisor's verbs, a listen seat, the chat socket. |
| `api/cases.ts` | 224 | The dataset endpoints: the org's cases, the groups they fall into, the golden a call makes, and an agent's personas. |
| `api/client.ts` | 115 | The gateway client: one URL, one key, one env header; every `/v1/` request of the CLI goes through it. |
| `api/compliance.ts` | 60 | The compliance endpoints: erasures and their trail, who read what, the org's policy, consent, the do-not-call list, export. |
| `api/docs-site.ts` | 12 | docs.pinecall.io's llms-full.txt: every page of Pinecall's own docs in one file, read as the MCP server reads them. |
| `api/evals.ts` | 195 | The evals endpoints: a suite run and the runs kept, the simulated caller's next line, a spoken call, a call replayed by code. |
| `api/hosting.ts` | 76 | The hosting endpoints: the org's hosted apps, their releases, an app's logs, and the feed's release changes. |
| `api/judging.ts` | 55 | The judging endpoints: the judges of the org or of one agent, one tried on calls, and whether the org's calls are judged. |
| `api/knowledge.ts` | 74 | The knowledge endpoints: the bases, a contact's memory, the recall and extraction goldens, and the settings an attachment lives in. |
| `api/providers.ts` | 41 | The providers endpoints: the vendor catalog, and the org's own provider keys, written and named but never read. |
| `api/telephony.ts` | 192 | The telephony endpoints: the org's numbers and routes, its carrier accounts, an agent's line, the callbacks waiting. |

### `project/` — the tenant's folder

| file | lines | what it is |
|---|---|---|
| `project/credentials.ts` | 58 | Where a project's key and gateway URL come from: the environment, else the nearest `.env`. |
| `project/language.ts` | 83 | Which language an agent is written in, and the command that starts its serve entry. |
| `project/layout.ts` | 138 | The tenant's project: one folder per agent under `agents/`, holding its class, its documents and its tests. |

### `billing/`

| file | lines | what it is |
|---|---|---|
| `billing/commands.ts` | 37 | `pinecall limits`: what the org may use in this env, what it used this month, and whose keys its calls run on. |
| `billing/render.ts` | 39 | The limits as a terminal reads them: the env, a line per quota, and whose keys a call runs on. |
| `billing/service.ts` | 49 | Billing: what the org may use in this env, what it used this month, and whose keys its calls run on. |

### `accounts/`

| file | lines | what it is |
|---|---|---|
| `accounts/commands.ts` | 169 | `pinecall login \| link \| whoami \| secrets`: this machine signed in, the project tied to an org, who the key is, the org's secrets. |
| `accounts/render.ts` | 69 | Accounts as a terminal reads them: the sign-in link, who signed in, what `link` wrote, who a key is, the secrets table. |
| `accounts/service/home.ts` | 93 | `~/.pinecall/session.json`: this machine's sign-in per gateway, and the phone it calls from. |
| `accounts/service/index.ts` | 8 | Accounts: signing this machine in, linking a project to an org, who a key is, the org's secrets. |
| `accounts/service/link.ts` | 69 | Tying the project's folder to one of the person's orgs: their orgs, the key minted in the one chosen, the `.env` it is written to. |
| `accounts/service/secrets.ts` | 40 | The org's secrets: what its hosted apps are started with, per env, set and dropped, never read back. |
| `accounts/service/signin.ts` | 101 | Signing this machine in: a pairing opened at the gateway, the key collected once a person approves it, proved and kept. |
| `accounts/service/whoami.ts` | 24 | Who the project's key is at its gateway, and the console's one-use login code minted on it. |

### `providers/`

| file | lines | what it is |
|---|---|---|
| `providers/commands.ts` | 72 | `pinecall providers`: every vendor this build runs, and the provider keys this org brought of its own. |
| `providers/render.ts` | 29 | Providers as a terminal reads them: the vendor table with the platform's defaults, the org's own vendors by name. |
| `providers/service.ts` | 100 | Providers: the vendor catalog this build runs, and the org's own provider keys, added from stdin, taken back, named but never read. |

### `agents/`

| file | lines | what it is |
|---|---|---|
| `agents/commands.ts` | 265 | `pinecall agent \| lexicon \| pipeline \| voices`: what the org set over the class, its words, what it runs on, the voices to pick. |
| `agents/render.ts` | 252 | Agents as a terminal reads them: the settings table, versions, a diff, the lexicon, the pipeline, the apps, the voices. |
| `agents/service/corners.ts` | 77 | The three corners of an agent's settings — yours, the team's, production's — and how a write lands on one. |
| `agents/service/index.ts` | 44 | Agents: what the org set over the class, per corner and versioned; the lexicon; the pipeline; the processes; the voices. |
| `agents/service/lexicon.ts` | 72 | An agent's lexicon: how the voice says a word and what the ears must know, whole and versioned like the settings. |
| `agents/service/running.ts` | 117 | What an agent runs with: its pipeline as the next call would be built, the processes holding the org's agents, and a vendor's voices. |
| `agents/service/settings.ts` | 258 | An agent's settings: the fields, set and cleared as the next version of a corner, their versions, and a corner as a file. |

### `knowledge/`

| file | lines | what it is |
|---|---|---|
| `knowledge/commands.ts` | 205 | `pinecall docs \| memory \| remember`: the documents the agent searches, what it remembers about a caller, what a call teaches it. |
| `knowledge/render.ts` | 122 | Knowledge as a terminal reads it: a push, the bases, a score, an attachment, a contact's facts, the policy, an extraction run. |
| `knowledge/service/cases.ts` | 63 | The goldens on the tenant's disk: a retrieval or recall golden's questions, and memory's extraction cases. |
| `knowledge/service/docs.ts` | 206 | The documents an agent searches: a folder pushed as a base, the bases listed and dropped, a golden held against one, and who reads which. |
| `knowledge/service/index.ts` | 28 | Knowledge: the documents an agent searches, a contact's memory, the recall and extraction goldens. |
| `knowledge/service/memory.ts` | 81 | One contact's memory and the right to be forgotten, the agent's memory policy, and the recall golden. |
| `knowledge/service/remember.ts` | 44 | `remember`: memory's extraction cases run through the gateway, one model call each, judged by code. |
| `knowledge/service/settings.ts` | 3 | The corner of an agent's settings a knowledge write lands on: the agents domain's, below this one. |

### `telephony/`

| file | lines | what it is |
|---|---|---|
| `telephony/commands.ts` | 219 | `pinecall numbers \| carriers \| line \| callbacks`: the org's numbers and accounts, whose terminal a ring lands in, who to call back. |
| `telephony/render.ts` | 148 | Telephony as a terminal reads it: the numbers, what the accounts own, a plan's steps, the carriers, the line, the callbacks. |
| `telephony/service.ts` | 200 | Telephony: the org's numbers and routes, its carrier accounts, whose terminal an agent's number rings in, and the callbacks waiting. |

### `judging/`

| file | lines | what it is |
|---|---|---|
| `judging/commands.ts` | 145 | `pinecall judges \| judging`: every judge a call meets, one tried on calls, and whether the org's calls are judged and on what. |
| `judging/render.ts` | 134 | Judging as a terminal reads it: the judges table, a try, the org's judging, and a call's score. |
| `judging/service.ts` | 186 | Judging: every judge a call meets, one tried on calls, and whether the org's calls are judged and on what. |

### `calls/`

| file | lines | what it is |
|---|---|---|
| `calls/commands.ts` | 271 | `pinecall sessions \| chat \| supervise \| data`: an agent's calls, a written call, a live call's desk, the org's data. |
| `calls/render.ts` | 281 | Calls as a terminal reads them: the list, one call, its log, a chat's lines, the desk, the org's data. |
| `calls/service/chat.ts` | 236 | A written call at the agent, wherever it is held: one socket, each line a turn, redialled when the gateway drops it. |
| `calls/service/data.ts` | 156 | The org's data: erasures and their trail, who read what, the policy, consent, the do-not-call list, export. |
| `calls/service/index.ts` | 29 | Calls: an agent's calls and their logs, a written call, a live call's desk, a call heard, and the org's data. |
| `calls/service/listening.ts` | 107 | `--listen`: a live call played on this machine's speakers, through a hidden seat in its room. |
| `calls/service/sessions.ts` | 92 | An agent's calls: the list, one call whole with what it cost and how it was judged, and its log a page at a time. |
| `calls/service/supervise.ts` | 115 | A live call as a supervisor's desk sees it: its transcript as it happens, and a move on it. |

### `evals/`

| file | lines | what it is |
|---|---|---|
| `evals/commands/dataset.ts` | 250 | `pinecall runs \| cases \| personas`: the runs the gateway kept, the org's dataset, the agent's simulated callers. |
| `evals/commands/index.ts` | 99 | `pinecall test \| simulate \| eval \| runs \| cases \| personas`: the goldens, simulated callers, a call checked again, the runs, the dataset. |
| `evals/commands/terminal.ts` | 135 | The evals verbs that hold a terminal: a suite drawn as it goes, watched for changes, and a simulation printed as it happens. |
| `evals/help.ts` | 68 | The prose under each evals verb's `--help`: what the flags cannot say. |
| `evals/render/index.ts` | 244 | Evals as a terminal reads them: the matrix, progress, runs, cases and groups, personas, a simulation, a replay. |
| `evals/render/matrix.ts` | 106 | A run as a terminal reads it: one line per golden, details under each that broke, the divergences, the footer. |
| `evals/render/progress.ts` | 115 | Live progress of a suite on a terminal: the header, a line per golden as it is judged, a bar, redrawn in place. |
| `evals/service/dataset.ts` | 154 | The org's dataset: real calls kept as cases — read, decided, pulled into the repository, kept, forgotten — and the groups they fall into. |
| `evals/service/goldens.ts` | 90 | Golden files on the tenant's disk and the schema the runner accepts. |
| `evals/service/index.ts` | 74 | Evals: goldens run through the agent, the runs kept, the org's dataset, the simulated callers, a call checked again by code. |
| `evals/service/personas.ts` | 214 | An agent's simulated callers: Pinecall's switched on or off, its own written, generated, dropped, and the file-kept ones pushed once. |
| `evals/service/replay.ts` | 17 | Ring 3: one finished call rebuilt from its log and answered by the runtime's code checks; nothing re-run, no model asked. |
| `evals/service/runs.ts` | 248 | The runs the gateway kept: listed, one shown, two diffed, a real call promoted to a candidate, each judge's drift. |
| `evals/service/simulation.ts` | 228 | One simulated call: a model plays the persona against the agent wherever it is held, written or spoken, judged at hang-up. |
| `evals/service/suite.ts` | 267 | A golden suite run through the agent wherever it is held, scored by the gateway; its report, latencies and reproductions. |

### `hosting/`

| file | lines | what it is |
|---|---|---|
| `hosting/commands.ts` | 101 | `pinecall deploy`: this project run on Pinecall — uploaded as a release, installed and started there. |
| `hosting/render.ts` | 64 | Hosting as a terminal reads it: a release sent and settled, the apps, the releases, the logs. |
| `hosting/service.ts` | 209 | Hosting: the project uploaded as a release Pinecall installs and runs, followed until live; the apps, their releases, logs, rollback, stop and start. |

### `alerts/`

| file | lines | what it is |
|---|---|---|
| `alerts/commands.ts` | 159 | `pinecall monitors \| webhook \| telemetry`: what the org watches, where its alerts go, where its traces go. |
| `alerts/render.ts` | 56 | Alerts as a terminal reads them: the monitors table, one monitor, the webhook, the collector. |
| `alerts/service.ts` | 92 | Alerts: the monitors the org watches, where its alerts are posted, and where its traces go. |

### `scaffold/`

| file | lines | what it is |
|---|---|---|
| `scaffold/commands.ts` | 69 | `pinecall new \| generate`: a new project, an agent in it, one more golden for an agent. |
| `scaffold/render.ts` | 23 | Scaffold as a terminal reads it: the next steps of a new project, the files a generate wrote. |
| `scaffold/service.ts` | 151 | Scaffold: a new project, an agent in it, one more golden for an agent — files written, nothing asked of a gateway. |

### `dev/` — the engine: `start`, `console`, `prompt`, the console's screens

| file | lines | what it is |
|---|---|---|
| `dev/child.ts` | 133 | The serve entry as a child process: started detached, its door in its env, told to leave once, killed if it does not. |
| `dev/commands.ts` | 102 | `pinecall start \| console \| prompt`: the agents served and the console answered, the console opened, the prompt a state produces. |
| `dev/companion.ts` | 61 | The CLI's own socket beside the agent's process: it takes no call, and answers the console's screens. |
| `dev/console.ts` | 37 | The console's addresses: the sandbox's under `/sandbox`, production's at the root, signed in with a one-use code. |
| `dev/handlers/chat.ts` | 61 | The console's Chat screen: written calls against the agent this process serves, so a tool's breakpoint works from the terminal. |
| `dev/handlers/index.ts` | 41 | The console's dev verbs this process answers, one row per screen, over the agent's directory on disk. |
| `dev/handlers/knowledge.ts` | 77 | The console's Docs and Memory screens: this directory's documents pushed and scored, its memory goldens run. |
| `dev/handlers/runs.ts` | 75 | The console's Runs screens: a real call promoted to a candidate beside the goldens, the judges' drift, the reproductions a suite wrote. |
| `dev/handlers/screen.ts` | 40 | What every console screen's handlers stand on, and how a failure of theirs is told to the console. |
| `dev/handlers/suite.ts` | 117 | The console's Tests and Simulations screens: goldens and personas played through the agent this process serves. |
| `dev/render.ts` | 64 | The lines `pinecall start` prints once an agent is registered: connected, its routes, its line. |
| `dev/screen.ts` | 101 | The live terminal view as pure functions: events in, screen text out. |
| `dev/screens.ts` | 142 | `pinecall start` output modes: the plain log and the full-screen view, over the agent's process. |
| `dev/serving.ts` | 84 | What a serve entry says on its `--events` stdout: one wire entry a line, read into apps and events. |
| `dev/start.ts` | 136 | `pinecall start` as a process: the serve entry started and watched, the companion connected, the lines printed until it leaves. |

### `mcp/` — the MCP server over the domains' services

| file | lines | what it is |
|---|---|---|
| `mcp/agent-host/framework.ts` | 74 | A TypeScript project with nothing installed runs on the framework this server ships, lent to the agent's thread alone: nothing is written into the project. |
| `mcp/agent-host/held.ts` | 172 | An agent the MCP server holds: in a thread of its own, or attached to the process that already holds it, and reloaded on a save. |
| `mcp/agent-host/thread.ts` | 149 | An agent served in a worker thread of this process: the project's own serve entry, its `main` called with the thread's streams. |
| `mcp/commands.ts` | 51 | `pinecall mcp`: the MCP server an assistant runs this CLI as, and `install`, which adds it to every assistant here. |
| `mcp/install/configs.ts` | 56 | Somebody else's config file, with exactly one entry changed: Pinecall's. Their servers, settings and comments stay. |
| `mcp/install/hosts.ts` | 75 | The assistants `pinecall mcp install` writes into: where each keeps its MCP servers, in which format, under which key. |
| `mcp/install/installing.ts` | 57 | `pinecall mcp install`: Pinecall written into every assistant on this machine, listed, or taken out — and what was done, line by line. |
| `mcp/instructions.ts` | 34 | The server's instructions: the journey from nothing to an agent answering, and the tools by stage. Each tool's manual rides its own description. |
| `mcp/scrub.ts` | 15 | No secret crosses a model: every answer and every refusal of the MCP server passes here first. |
| `mcp/server.ts` | 89 | The MCP server: every tool registered on one stdio connection, each answer scrubbed, each failure one sentence. |
| `mcp/session.ts` | 173 | One MCP server's state — the project it works in, what it holds, what is in flight — and the Context each tool call runs with. |
| `mcp/site.ts` | 97 | Pinecall's own docs as the MCP server reads them: the site's one file cut into pages and sections, searched here. |
| `mcp/tool.ts` | 60 | A tool of the MCP server: what a model reads about it, what it takes, and the service it calls. |
| `mcp/tools/accounts.ts` | 88 | The `login`, `link` and `whoami` tools: the accounts domain, over its service. |
| `mcp/tools/agents.ts` | 121 | The `agent`, `lexicon`, `pipeline`, `voices` and `voice_sample` tools: the agents domain, over its service. |
| `mcp/tools/alerts.ts` | 63 | The `monitors`, `webhook` and `telemetry` tools: the alerts domain, over its service. |
| `mcp/tools/calls.ts` | 146 | The `calls`, `call`, `chat` and `supervise` tools: the calls domain, over its service. |
| `mcp/tools/dev.ts` | 99 | The tools that hold the agent and look at it: `start`, `stop`, `status`, its `prompt`, and the `console_url`. |
| `mcp/tools/evals.ts` | 267 | The `test`, `runs`, `eval`, `cases`, `simulate` and `personas` tools: the evals domain, over its service. |
| `mcp/tools/fields.ts` | 22 | The fields many tools take, declared once so every schema says them in the same words. |
| `mcp/tools/hosting.ts` | 55 | The `deploy` tool: the hosting domain, over its service. |
| `mcp/tools/index.ts` | 38 | Every tool the MCP server offers, by the stage a person meets it at. |
| `mcp/tools/judging.ts` | 93 | The `judges`, `judging` and `usage` tools: the judging domain, and the bill it makes, over the services. |
| `mcp/tools/knowledge.ts` | 71 | The `docs`, `memory` and `remember` tools: the knowledge domain, over its service. |
| `mcp/tools/providers.ts` | 13 | The `providers` tool: the providers domain, over its service. |
| `mcp/tools/scaffold.ts` | 66 | The `project` tool: which project the tools act on, opening another, writing a new one, generating into it. |
| `mcp/tools/site.ts` | 50 | The docs tools: `docs_search` finds the sections of docs.pinecall.io that answer a question, `get_doc` reads a page whole. |
| `mcp/tools/telephony.ts` | 77 | The `line`, `numbers`, `carriers` and `callbacks` tools: the telephony domain, over its service. |

## 4. What a verb is started with

`dev/child.ts` builds the child's command from `project/language.ts`: a TypeScript agent runs the
project's own `@pinecall/agents/serve` (resolved from the project's `node_modules`, never a copy this
CLI carries; a checkout's `.ts` entry through this CLI's tsx), a Ruby one `ruby -r pinecall -e
"exit Pinecall::Serve.main(ARGV)"` (under `bundle exec` when the project has a Gemfile), a Python
one the project's `.venv` python with `-m pinecall.serve`. The child is detached; its stdin is a
pipe whose end tells it to drain; the first SIGINT/SIGTERM is passed on as SIGTERM, a second, or
40 s, kills it. `pinecall mcp` holds a TypeScript agent in a worker thread instead
(`mcp/agent-host/thread.ts`), lending it the server's own framework when the project installed none.

## 5. Tests

`test/` mirrors `src/`: a domain's `service` and its `commands` each have a file, as do the
foundations, `dev/` and `mcp/`. `test/conventions/` holds the canon as tests (`rules.ts` runs alone
too: `node --import tsx` on it prints what breaks a rule). What every test stands on is in
`test/support/`:

| file | what it is |
|---|---|
| `support/gateway.ts` | the fake gateway: msw at `https://gateway.test` over real `fetch`; `answer` and `refuse` a route and keep each request as it was sent (path, query, body, env header, key), `stream` one as server-sent events (the feed, a log). A request no test answered fails the test |
| `support/setup.ts` | the setup every file runs: the server listens, forgets each test's routes after it |
| `support/context.ts` | a service's `Context` over the fake gateway, a project of its own, a `~/.pinecall` of its own (`PINECALL_HOME`), an IO that keeps what was said |
| `support/run.ts` | the CLI as typed: `main` in-process, the exit code and both streams back, stdin what the test pipes |
| `support/project.ts` | a tenant's project on disk for one test, removed after it |
| `support/fixtures.ts` | what the gateway answers, written once: limits, the catalog, settings and lexicon rows, judges, a run, a persona, a case |
| `support/fake-serve.mjs` | a serve entry a test scripts: its lines, a drain on SIGTERM, deaf on request |

Nothing is mocked by module: a service is tested through the requests it sends and the answers it
reads, a verb through `pinecall …` as typed. Two things are no HTTP: the chat socket (`ws`, a real
upgrade) is tested against a WebSocket server of the test's own with msw let go for that file, and the
serve child is a real process (`fake-serve.mjs`). Every `--help` is pinned in `test/help/<group>.txt`
by `program.test.ts`, written at 80 columns; a verb that changes is `pnpm test -u` and the diff read.
