# Changelog

All notable changes to `pinecall`, the CLI. Up to 0.9 it shipped inside the framework's package;
that history is [`@pinecall/agents`'s CHANGELOG](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/CHANGELOG.md).
The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

- **An agent is one folder.** Its documents and its tests live in it: `agents/<name>/docs/` and
  `agents/<name>/test/` (goldens, memory cases, personas, and the candidates `runs promote` writes)
  instead of `docs/<name>/` and `test/<name>/` beside `agents/`. Move a project's with
  `git mv docs/<name> agents/<name>/docs && git mv test/<name> agents/<name>/test`, then point its
  test runner at `agents/*/test/` (vitest's `include`, pytest's `testpaths` with
  `--import-mode=importlib`, the Rakefile's `FileList`) and each test's import of its class at
  `../agent`. `runs promote` takes `--agent`.
- **`new` names the project, `--agent` its first agent.** `pinecall new clinica-dental --agent sofia`
  writes `clinica-dental/` with `agents/sofia/`; without `--agent` it writes the project alone, and
  `pinecall generate agent <name>` adds each agent. The MCP `project new` takes `agent` the same way.
- **The CLI rewritten to one convention** (commander, one gateway client, one service per domain
  the terminal and the MCP both call). What a tenant notices: `--prod` and `--json` are global and
  `--json` answers every verb that returns data; a group's first verb is its default, so the short
  forms still work (`numbers` is `numbers list`, `memory <contact>` is `memory show <contact>`,
  `deploy` is `deploy up`) and `sessions <call>` and `judging on|off` stay one word; `sessions list`
  and `sessions show` are gone. `--agent <slug>` names an agent the gateway knows from any folder on
  every verb that asks the gateway alone (`sessions`, `agent`, `lexicon`, `judges`, `cases`, `line`,
  `memory policy`, `docs attach`); the project is needed only where files are read. Help and an
  unknown flag read as commander prints them. The MCP tools keep their names, arguments and manuals.

## [0.10.1] — a golden is turns; callers that murmur, slow down and ring from a café; judges that say what they save you from

- **`pinecall judges` says what each of Pinecall's judges saves you from**, and marks `recommended`
  the eight to switch on first.
- **A persona murmurs, speaks at its own tempo, and rings from somewhere.** `pinecall personas add`
  and `edit` take `--backchannels 0-1` (the share of the agent's answers it says an "mm-hmm" into,
  keeping its turn), `--speed 0.5-2` (its voice slower or faster, the pitch kept) and `--ambience
  television|cafe|office|street` with `--background-noise dB` (what plays behind it, and how loud);
  `show` prints them. `pinecall simulate --voice` and `pinecall test --voice` take `--ambience`
  beside `--background-noise`, as the MCP's `simulate`, `test` and `personas` do.
- **`pinecall start` prints where to talk to the agent.** Its `console` line is now `talk to it`, a
  signed-in link to the agent's chat in the console (`/a/<slug>/playground`), as the first thing a
  person does with an agent they just started.
- **A golden is turns.** `{"turns": [{"say": …, "then": [steps]}, {"event": {name, data}}, …], "expect": {…}}`:
  each turn a caller's line or a backend's fact; after a line, what must follow it in order — a
  tool and its arguments, a tool that must not run, a reply with its phrases and its `intent`, the
  end, nothing else — asserted on livekit's own test run of the line. `input`, `events`, `after_turn` and `expect.replies` are gone, with no translation: rewrite
  each golden. `pinecall generate golden` takes `--say` (once per turn) instead of `--input`, and the
  MCP's `project` takes `say`. `pinecall test` names the turn that cut a broken golden (`turn 2
  broke`) above its broken `t{n}.*` lines; `heard` and `replies` are no longer metrics.
- **`pinecall judges` lists every judge of Pinecall's library off until switched on**, and
  `pinecall golden` no longer says every golden is judged by `consent`: a golden asks only what its
  `expect` names.
- **`pinecall numbers import --account <id>`** names the carrier account the number lives in. An
  org with several accounts could not import from a terminal or the MCP at all: the gateway asked
  which and nothing could say. Without the flag the refusal now prints the flag to add.
- **`pinecall numbers buy --country <XX> [--area <digits>] --agent <slug>`** buys a number on the
  deployment's own account and points it at the agent; `--dry-run` names it and buys nothing. The
  MCP's `numbers` tool buys too, a dry run unless told otherwise, and imports with `account`.
- **`pinecall limits`**: every limit of the org in the environment as what is used of it, when the
  monthly ones start again, and whose keys a call runs on — yours, and the ones the deployment
  lends. The MCP's `usage` answers the keys too.
- `pinecall carriers list` says how many numbers each account routes here; `pinecall numbers list`
  names the account an imported number lives in.

- **Only `pinecall start` runs the agent.** `chat`, `test`, `simulate`, `remember` and
  `personas try` start no process: they knock at the gateway naming no app, and the call goes to
  whoever holds the agent — your `pinecall start`, a colleague's, production's with `--prod`.
  `--inspect` and `--inspect-brk` are `start`'s alone now.
- **The MCP talks to the agent with nothing held.** `chat`, `test`, `simulate` and `remember` take
  `prod` and reach the copy `start` holds when it holds it in that world, else whoever holds the
  agent there. The `logs` tool is gone: a call's log is `call`.
- **A call's log read with `--types` reads to its end.** `sessions log` and the MCP's `call` read on
  from the gateway's own cursor — the last seq it read, kept or not — where a page the types
  narrowed below its size used to say there was nothing after it. Both answer `live`.
- **Nothing waits by reading on a clock.** A spoken simulation follows its call's log over the
  stream, `pinecall test` draws its run when the org's feed says the run changed, and the MCP's
  `supervise watch` and `login status` wait on the log and on the sign-in itself, where each read
  a page every few hundred milliseconds.
- `pinecall sessions log <call>`: a call's log, an entry a line — the turns, each tool call with its
  arguments and what it answered, the states, the rest as data — paged with `--after`, narrowed
  with `--types`, whole with `--json`; what the MCP's `call` tool reads, in a terminal.

## [0.10.0] — one repository, one version

- Published from [pinecall/pinecall](https://github.com/pinecall/pinecall) with every other
  Pinecall package, at the one version they all carry from here on. `@pinecall/agents`
  is `^0.10.0`, the framework of the same commit. Nothing a tenant types changes.

## [0.9.52] — personas from a library and generated, with what they expect and how they act; cases grouped, diagnosed and fixed

- `pinecall personas` lists Pinecall's library first (realism and a red team), `on`/`off` per
  agent; `add`/`edit` take `--expect` (what the agent should do, repeated), `--tag`,
  `--interrupts 0-1` and `--pause s` (how a spoken caller acts); `--accepts-when`/`--declines-when`
  are gone. `pinecall personas generate [N] --about --from-call --template [--save]` writes callers
  from the agent with the judge model.
- `pinecall cases groups`, and `show`/`propose`/`apply`/`persona`/`approve`/`dismiss` on a group's
  id: cases grouped by the judge that broke them, diagnosed into a fix, a setting applied, decided
  whole. The MCP's `cases` tool does the same and tells the assistant what to do with each kind of
  fix; a new `judging` tool reads and sets the org's judge model, and `usage` says what the org
  used of its limits — evals and simulations among them — and whether its judges cost it evals.
  Needs runtime 0.1.46.

## [0.9.51] — judges are one list, switched, written whole and tried; the judge model is yours to pick

- `pinecall judges` lists every judge a call meets — Pinecall's library first, with on/off, then
  the org's own and the agent's own — and gains `on` / `off` (a library judge, for the org with
  `--org` or one agent), `add --answer verdict|score|choice:a,b,c --when always|simulations|
  trigger:'…' --reads prompt,evidence,facts`, and `try <name> --last N | --calls a,b`, which asks
  one judge of finished calls and writes nothing. `--on every-call|simulations` is gone (`--when`).
- `pinecall judging [on|off] [--model vendor/model --option key=value … | --platform]`: whether the
  org's calls are judged, and the model they are judged on; on the org's own key its evals are not
  billed. `pinecall agent set --judge x --judge-builds Class --judge-option key=value` names one agent's.
- A call's score prints N/A (`–`), a classification's choice or score (`=`), the evals and whether
  the org's own key answered them. The MCP's `judges` tool takes the same actions; `agent` takes
  `judge`, `judge-builds`, `judge-options`. Needs runtime 0.1.45 and @pinecall/agents 0.9.27.

## [0.9.50] — 2026-10-10

- `pinecall agent set --greeting improvise` (the model opens on its prompt) and `--greeting
  improvise:'…'` (with an instruction) replace `--reply`; `--greeting-interruptible on|off`, since
  an opening is no longer cut short unless it says so.
- `--hangup any`: the model ends the call whenever it judges it done.
- `--end-of-turn stt|livekit|smart-turn`: who says the caller's turn is over. The table shows it,
  and `class` when the agent's `@stt` declares it. Needs runtime 0.1.43 and @pinecall/agents 0.9.26.

## [0.9.49] — 2026-10-10

- `pinecall agent set --temperature n`, `--llm-builds Class` and `--llm-option key=value` (repeated,
  the value read as JSON when it is JSON), and their `--stt-…` and `--tts-…` twins: a plugin's own
  class and keyword arguments, run only on the org's own key for the vendor. `clear` takes
  `temperature`, `llm-builds`, `llm-options` and the rest by the same names.
- `pinecall agent` prints `class` in every corner of a field the agent's class declares itself; a
  set or clear of it is refused in the gateway's sentence. The MCP `agent` tool takes the same.
  Needs @pinecall/agents 0.9.25 and runtime 0.1.42.

## [0.9.48] — 2026-10-09

### Fixed

- `pinecall telemetry set` with several `--header` reads one piped line per header: the second header's value was read as empty, so Langfuse's two headers could not be piped.
- `pinecall telemetry --help` and its reference say what the export is: a copy of every spoken call's spans, off until set — a chat has no worker and no spans, and the console reads the call's log, never the export. A Langfuse example. `clear` says the export stopped.

## [0.9.47] — 2026-10-09

### Added

- `pinecall webhook`: where the org's alerts are posted — `set <url> [--secret]` with the secret off stdin, `test` for one signed post, `clear`, and the bare verb. The MCP tool `webhook` shows, tests and clears. Needs runtime 0.1.25.

## [0.9.46] — 2026-10-09

### Added

- `pinecall monitors`: the numbers the org watches — latency, the judges' held rate, escalations, tool failures, spend, calls — over 1, 7 or 30 days, the line each must not cross, and when each last fired; `add`, `rm`, and the bare list. The MCP tool `monitors` does the same, in production with `prod`. Needs runtime 0.1.23.

## [0.9.45] — pinecall start shows each turn's latencies

### Fixed

- `pinecall start` printed "no metrics on this turn" under every reply: the screen read the
  event camel-cased and looked for the wire's names. It now prints `e2e_latency`,
  `llm_node_ttft` and `tts_node_ttfb` as `pinecall chat` does.

## [0.9.44] — every verb's help shows it run

### Added

- `pinecall <verb> --help` ends with Examples: the verb run, with what it prints, taken from the
  reference page's own console blocks — `docs`, `memory`, `lexicon` and every other verb.

## [0.9.43] — traces to your own collector

### Added

- `pinecall telemetry set <url> [--header <name> …] [--pii]`: where this org sends its calls'
  traces, an OpenTelemetry collector of its own beside Pinecall's; each header's value is read
  off stdin, never a flag. The bare verb shows it by header name, `clear` stops it. The MCP's
  `telemetry` tool shows and clears; setting one stays the person's terminal. Needs runtime
  0.1.12.

## [0.9.41] — help after a subverb, and remember in a project of several agents

### Fixed

- `--help` after a subverb (`pinecall memory policy --help`) prints the group's help instead of
  refusing an unknown flag.
- `pinecall remember` in a project of several agents says to name one with `--agent`, instead of
  claiming the project has no extraction goldens.

## [0.9.40] — a project depends on its SDK, never on the CLI

### Changed

- A TypeScript project no longer depends on this CLI: `pinecall new` writes `@pinecall/agents` alone under `dependencies`, and `pinecall deploy` asks only for that. The CLI is installed once per machine, `npm i -g pinecall`, and Pinecall starts a deployed project with its own. A project that still lists `pinecall` keeps working.

## [0.9.39] — a Python agent, served like the other two

### Added

- A Python agent: `pinecall new <name> --python` and `generate agent --python` write a uv project (`pyproject.toml`, `agents/<name>/agent.py`, its view in Jinja, a pytest ring 0), and `start`, `chat`, `test` and `prompt` serve it through `python -m pinecall.serve`, with the project's `.venv/bin/python` when it has one. `--inspect` is refused for it, as for Ruby, and `deploy` says to run it on a server of your own. The template depends on PyPI `pinecall>=0.1.6`, the Python SDK.
- `pinecall mcp`: `project new` and `generate` take `language: python`; a Python agent is attached to, as a Ruby one is.

## [0.9.38] — cases: a call a judge broke on, kept, fixed and decided

### Added

- `pinecall test --case <name>` (repeatable) plays cases of the org's dataset by name, a pending one too; `--dataset` plays every approved case; with either and no paths, only the cases run and `test/goldens` is not needed. `--version n` runs every call on that version of the agent's settings. A golden's `expect` takes `judges`: hang-up judges asked again by name.
- `pinecall cases`: the org's dataset, real calls kept as cases — the inbox (`--status`), `show` one whole with the commands that come next, `approve`, `dismiss` (`--judge-was-wrong <judge>`, `--note`), `reopen`, `pull` its golden into `test/<agent>/goldens/` and mark it kept in the repository, `keep <call> --name x` a finished call, `forget` one. A case is named within the agent.
- `pinecall mcp` has `cases`, the same verbs for an assistant (`list`, `show`, `approve`, `dismiss`, `reopen`, `pull`, `keep`; `forget` stays a terminal's, as it cannot be undone), and `test` takes `case`, `dataset` and `version`.

### Changed

- `pinecall runs promote` writes the golden the gateway derives from the call (`GET /v1/calls/{call}/golden`), so a candidate now carries the facts the app gave the call, what memory recalled and the day it ran, and every broken judge lands in its `expect` (`judges` by name). A call nobody judged is no longer refused: its expect is empty, to be written by hand.

## [0.9.37] — the desk, as an MCP tool

### Added

- `pinecall mcp` has `supervise`: the desk `pinecall supervise` is in a terminal, for an assistant. `watch` reads a live call since a cursor — the caller, the agent, its tool calls, every move of a desk, the end — waiting up to `wait_s` for more; `whisper`, `say`, `takeover`, `release`, `transfer` and `end` move it, each landing in the call's log as a `supervisor.*` entry. An ended call is refused.

## [0.9.36] — an assistant's agent runs before anything is installed

### Added

- `pinecall mcp`: a TypeScript project with nothing installed runs anyway. `start` and `prompt` lend the agent's thread the `@pinecall/agents` the server ships — nothing is written into the project — until `npm install` pins the project's own; `status` says `framework` while it is lent. So an assistant goes from an empty folder to an agent answering without a terminal. Every CLI verb still refuses such a project by name.

## [0.9.35] — no Claude Haiku 4.5 left

### Changed

- `pinecall agent --help`, the CLI's pages and the MCP's examples name `claude-haiku-5-5` where they named `claude-haiku-4-5`; the sample call in `sessions` is priced at Claude Haiku 5.5's rates.

## [0.9.34] — every MCP tool documented: its parameters and a real call

### Added

- The MCP's tools each have a reference: every parameter, read off the tool's own schema, and one real call answered by Pinecall Cloud — `docs/mcp/`, eight pages by stage, written by `scripts/mcp-pages` and failed by a test when they drift. Every `action` now says what each of its values does, in the schema the assistant reads.

## [0.9.33] — `haiku` is Claude Haiku 5.5

### Changed

- The `haiku` tier (`pinecall test --model haiku`, `pinecall agent set --llm haiku`, the nightly's baseline column) expands to `claude-haiku-5-5`, not `claude-haiku-4-5-20251001`. A setting stored before keeps the id it was stored with.

## [0.9.32] — `pinecall generate`

### Added

- `pinecall generate` (`g` for short): `agent <name>` writes a second agent into the project from the templates `new` writes, in the project's language; `golden <name> --input '…' --tool …` writes a golden from the caller's lines and the tools that must be called. Never over a file. The MCP's `project` tool does the same with `generate`.

## [0.9.31] — `memory forget` asks for `--yes` where nobody can be asked

### Changed

- `pinecall memory forget` with nobody at a terminal erases only with `--yes`, as `pinecall data erase` does; before, a script erased without asking. `--yes` also skips the question on a terminal.

## [0.9.30] — the MCP reviewed against the plan: `prod` honoured, `simulate` waits, one packet-loss unit

### Changed

- `pinecall simulate --packet-loss` takes the share of the caller's packets lost, from 0 to 1, as `pinecall test --voice` does and as the wire carries it; a percent is refused. The console's Simulations screen still says a percent.
- `pinecall mcp`: every tool that opens the project's door takes `prod: true`, honoured by a server installed with `--prod` and refused by any other — before, `--prod` changed nothing. `simulate` runs as `test` does (`run`, then `wait` past `wait_s`, with the transcript so far); a second `test run` or `simulate run` on an agent with one in flight is refused. `docs list`, `docs attached` and `memory show` name no agent, so a project of two needs none; `memory policy` reads the two lists, not the whole settings. `start` attaches to the agent's own process, never to the companion a terminal keeps beside it; a save landing as `stop` runs is dropped, so nothing runs after it; `project open` is refused while an agent is held. Each tool's manual rides its description, and the instructions name the tools by stage instead of repeating them. One line per call on stderr: the tool, the time, ok or refused.

## [0.9.29] — the console reaches the agent an assistant holds

### Added

- An agent `pinecall mcp`'s `start` holds in a thread has a companion beside it, as `pinecall start` does: the console's Chat, Tests, Simulations, Docs and Memory screens reach it. `pinecall agent list` shows it as `pinecall-mcp/<version>`.

## [0.9.28] — every tool of the MCP

### Added

- `pinecall mcp` holds the agent and does all of it from an assistant: 35 tools. `start`, `stop`, `status` and `logs` hold a TypeScript agent in a worker thread of the server — no process — reloaded on every save (a save that does not load keeps the version before answering, and says why), or attach to a Ruby agent or a terminal already holding it; `chat` talks to it a line at a time, each answered whole; `prompt` and `console_url`. `agent`, `calls`, `call`, `pipeline`, `providers`, `voices`, `voice_sample`, `line`, `numbers` (import as a dry run first), `carriers`, `callbacks`, `lexicon`. `test` (a column per model, written or spoken), `runs` (list, show, diff, promote, drift), `simulate`, `personas`, `judges`, `eval`, `docs`, `memory`, `remember`. `deploy` and its family. `docs_search` and `get_doc` over docs.pinecall.io. No tool takes a secret, and none erases anything.

### Changed

- `pinecall deploy` packs what the project's `.gitignore` files leave in, read where each sits, and no longer asks git: a folder that is no checkout packs the same.

## [0.9.27] — Claude Desktop finds node

### Fixed

- `pinecall mcp install` gives Claude Desktop the folder of this machine's `node` on its `PATH`: a desktop app starts without the shell's, so under nvm `npx` could not find `node` and the server never started.

## [0.9.26] — mcp install names the newest CLI

### Fixed

- `pinecall mcp install` writes `npx -y pinecall@latest mcp`: inside a project that pinned an older `pinecall`, the bare name ran that copy, which has no `mcp`, and the assistant only saw the connection close.

## [0.9.25] — the CLI as an MCP server

### Added

- `pinecall mcp`: the CLI as an MCP server for Claude Code, Claude Desktop, Codex, Cursor, Windsurf, Antigravity and Gemini CLI, with its first tools — `whoami`, `login`, `link`, `project` — acting in the sandbox, starting no process, and scrubbing every key from what they answer. `pinecall mcp install` writes it into every assistant on the machine (`--list`, `--remove`, `--prod`).

## [0.9.24] — `pipeline` reads talk_share as a share

### Fixed

- `pinecall pipeline` prints `talk_share` as a percent, not in seconds.
- `pinecall judges --help` and the CLI's page name every platform judge name the gateway reserves (`identified`, `disclosed`, `honoured_stop` and `heard` beside `consent`, `grounded`, `promises`, `persona`).

## [0.9.23] — `--version`, and help that says what the runtime answers

### Added

- `pinecall --version` (`-v`, `version`) prints the CLI's version.

### Fixed

- `pinecall eval --help` names the six checks the runtime runs and their verdicts (held · broken · deferred · skipped), and its `--policy` example uses keys the runtime reads; the old `llm_ttft` matched nothing and silently skipped the latency check.
- `pinecall callbacks` says `via the agent` for a call back the agent's own tool promised, instead of `via the widget`.
- Help and messages say Pinecall where they said "the box".

## [0.9.22] — `pinecall new`, and every verb walked on what it makes

### Added

- **`pinecall new <name> [--ruby]`**: a project of one agent, in TypeScript or Ruby, ready for
  `link`, `prompt`, `chat`, `test`, `start` and `deploy`.
- **The quickstart** (`docs/quickstart.md`): nothing to an agent that answers, in ten minutes.

### Changed

- **`pinecall prompt` needs no `--state`**: without one it prints the page a call opens on.
- **`pinecall deploy` refuses a Ruby project** by name, rather than asking it to `npm i` packages it
  cannot use: the box runs TypeScript projects, and a Ruby agent runs `pinecall start` on its own
  server.

### Fixed

- **`pinecall chat` with piped input answers every line.** Two lines sent at once hung up after the
  first answer; it waits for each line to be heard and answered.
- **`pinecall chat` hangs up through the gateway**, which ends the call before closing the socket,
  so the agent's process no longer says it kept a live call. A pipe gets no `‹` prompts.

## [0.9.21] — the serve entry is the project's own framework

### Fixed

- **A TypeScript agent is served only by the framework its project installs.** The serve entry was
  resolved the way Node resolves a module, which reads `NODE_PATH` too: under pnpm that is pnpm's
  store, so a project with no `@pinecall/agents` of its own was served by whatever the store held.
  It is looked for in the project's `node_modules` and the folders above it, and nowhere else.

## [0.9.20] — the CLI, a package of its own

### Fixed

- **A member's first `agent set` (and `lexicon`, `agent knowledge edit`, `docs attach`) is no
  longer refused with "this corner is at v0 now".** The write was guarded by the version of the
  team's corner it was read through, while the gateway writes the person's own, still empty. The
  guard is now the version of the corner the write lands on (0 when it is empty): a person's own
  in the sandbox, the org's for a server's token and in production. The line that follows names
  that corner, "your corner", where it said "the team's corner".

### Changed

- **Breaking: the CLI is a package of its own.** `pinecall` on npm is the CLI alone, and the
  framework is `@pinecall/agents`. The CLI never loads a class: it starts the project's own serve
  entry — `@pinecall/agents/serve`, resolved from the project's root, or the `pinecall` gem's
  `Pinecall::Serve` — so a TypeScript project depends on both, and one CLI serves a Ruby project too.
  A TypeScript project that does not install `@pinecall/agents` is refused by name.
- **Breaking: `pinecall deploy` refuses a project whose `package.json` lists `pinecall` or
  `@pinecall/agents` nowhere in `dependencies`**, before it sends anything: the box starts the
  project's own `pinecall start`.
- The CLI's earlier changes since 0.9.19 — `start` in a process of its own with a companion socket,
  `call.started.state`, an agent's slug as its folder's name — are under Unreleased in
  `@pinecall/agents`'s CHANGELOG.
