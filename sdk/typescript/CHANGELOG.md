# Changelog

All notable changes to `@pinecall/agents`, the package a tenant writes an agent in — published as
`pinecall`, with the CLI inside it, up to 0.9. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers and tags are the
maintainer's call, so everything sits under Unreleased until one is cut.

## [0.11.17] — released with the runtime's wire fixes

- Nothing of `@pinecall/agents` changed: published at 0.11.17 with every other package.

## [0.11.16] — a failing view or hook fails its call, every write names its author, pii masked everywhere

- **A view that cannot be rendered fails its call, not the process.** `UnauthoredWrite` thrown from
  `render()` escaped the bridge through `void start(...)` and ended the serve process, every call with it;
  the call's log now gets a `render.failed` line, the model keeps the view it had and the process goes on.
  (found by the 2026-10-23 eval, B B8)
- **A hook that throws fails its call, not the process.** `onCall`, `onEvent`, `onMemory` and `onEnd` ran
  as detached promises, so a throw ended the serve process; the call's log now gets a `hook.failed` line
  naming the hook (and the event) and the error, stderr a line, and the call goes on with what the hook had
  written. (found by the 2026-10-23 eval, B B8)
- **Every state write carries its author on the wire.** A `state.set` now names its `cause`: the tool and
  the model's call id, the event and its entry, or the hook (`onCall`, `onMemory`); only a tool's first write
  and an event's had one, and the custom `state.cause` line is gone. `EventMeta.seq` is the log's seq of the
  `event.received` entry (it was a per-call counter), `Tool.run` gets the model's call id as a third argument
  and `CamelEvent` an optional `seq`. (found by the 2026-10-23 eval, B B4)
- **A line logged in `onCall` or `onEnd` lands on the call's log.** The forwarder was subscribed after
  `onCall` and dropped before `onEnd`. (found by the 2026-10-23 eval, B B3)
- **The SDK sends `call.done` after the end hook, and registers `says_done`**, so the gateway's seal waits for
  what the hook logs before it seals the log. (found by the 2026-10-23 eval, S2)
- **`@tool` on a field is refused with the sentence the docs promise**, `@tool goes on a method; book is not
  one`, as a `DeclarationRefused`, not a TypeError from inside the decorator. (found by the 2026-10-23 eval,
  B B6)
- **`runTool` says the types were erased** when the class was never handed its source, instead of `name must
  be a object, not a string`. (found by the 2026-10-23 eval, E R0-1)
- **`z` is exported from `@pinecall/agents`**: the zod `params` is read with, so a project needs no `zod` of
  its own. (found by the 2026-10-23 eval, B D5)
- **`this.call` has `to`, `direction`, `caller` and `metadata`**; `metadata` is the token's, sealed. (found
  by the 2026-10-23 eval, K F6)
- **`pinecall start` prints what the log keeps**: a value the agent declared private never reaches the
  terminal. (found by the 2026-10-23 eval, A F3)
- **An agent an admin killed is one line on stderr**, `<slug>  ✗ <slug> was killed by <name>`;
  `Pinecall.onKilled` hands over the slug and the sentence. The client no longer answers `end_call`, which
  the platform answers itself. (found by the 2026-10-23 eval, J F3, R2)

## [0.11.15] — the serve entry registers as its host

- **The serve entry registers as `PINECALL_HOST` when it is set**, else as this machine's
  hostname; `new Pinecall({ host })` says it for your own process. A hosted app's runner names each
  host, and the gateway knows a release is serving by it, on a machine that runs several.

## [0.11.14] — the wire knows `KnowledgePushed.kept`

- **`KnowledgePushed.kept`**: the files of the base a push did not name and kept.

## [0.11.13] — the wire knows `app.failed`

- **The wire knows `app.failed`, a feed event.** A hosted app that did not build, start or stay up: the org's alert, read by
  the console; an app acts on none of it.

## [0.11.12] — `onMemory` runs

- **`onMemory` runs.** Declared since the hooks were, never called: `memory.ops` now reaches it,
  after the view re-rendered with what was recalled. `MemoryOp` is the wire's op (`op`, `contact`,
  `query`, `facts`, `tookMs`), not the never-sent `{op, key, value}`.

## [0.11.11] — released with every other package

- Nothing of `@pinecall/agents` changed: published at 0.11.11 with every other package.

## [0.11.10] — released with every other package

- Nothing of `@pinecall/agents` changed: published at 0.11.10 with every other package.

## [0.11.9] — the wire knows a base's language and a golden's alternatives

- **The wire knows a base's language and a golden's alternatives.** `KnowledgeBase.language` and
  `KnowledgePushed.language` (the text-search configuration the base's words are stemmed with);
  `GoldenQuestion.expects` is a heading path or a list of them, and `GoldenMiss.expects` a list.

## [0.11.8] — the wire knows the judges' calibration

- **The wire knows `GET /v1/evals/calibration`**: `CalibrationSchema` and `JudgeAgreementSchema`, each
  judge against the labels people gave.

## [0.11.7] — the wire knows the feed's tool.ran, tool.failed and judge.broke

- **The wire knows the feed's `tool.ran`, `tool.failed` and `judge.broke`.** Each with only its
  call, agent and name (and seconds): the org's feed says a tool answered or failed and a judge
  found a call broken, never what it said.

## [0.11.6] — a tool's untyped parameter with a default takes the default's type

- **A tool's parameter with a default and no type takes the default's.** `cantidad = 1` reached the
  model as an open object, and a model that follows the schema (Grok Voice) sent `{"1": 1}` for a
  quantity. A number, a string or a boolean default now types its parameter.

## [0.11.5] — @realtime: a voice call's model that hears and speaks itself, beside the @llm

- **A voice call runs on a realtime model while a written call keeps the LLM.** `@realtime("xai/grok-voice-3.0", { options: { voice: "eve" } })` names the
  model the agent's voice calls (phone and web) run on alone, one that hears and speaks itself — no
  ears, its own voice — while the `llm` keeps answering its written calls. Its options run on the
  org's own key for the vendor; an `llm` that names such a model is refused at registration.

- **An agent an admin killed is declared no more.** An `error` coded `killed` on one agent
  (`POST /v1/agents/{slug}/kill`) drops it from the agents the client declares: the socket stays,
  the other agents go on, and a reconnect leaves the killed one out.

- **An agent no longer says it will check and then stops.** The first protocol every agent is given now
  says to call the tool in the same reply, that saying it is about to act does not act, and never to ask
  the caller to wait: once it stops talking nothing happens until the caller speaks. Open models said
  "Let me check the details of your order. Please wait." and ended the turn (2026-10-18).

## [0.11.4] — released with every other package

- Nothing of the framework changed: published at 0.11.4 with every other package.

## [0.11.3] — released with every other package

- Nothing of the framework changed: published at 0.11.3 with every other package.

## [0.11.2] — released with every other package

- Nothing of the framework changed: published at 0.11.2 with every other package.

## [0.11.1] — released with every other package

- Nothing of the framework changed: published at 0.11.1 with every other package.

## [0.11.0] — released with every other package

- Nothing of the framework changed: published at 0.11.0 with every other package. A project's agents
  live one folder each (`agents/<name>/`, its `docs/` and `test/` inside it): the CLI 0.11.0 reads
  that layout, and the framework reads the class wherever the CLI points it.

## [0.10.1] — the wire carries a golden by turns, a judge's why and recommended, and run, release and worker events

- `observe` follows the org's feed too (`{ feed: true }`, `GET /v1/events`), asks the gateway for
  only the `types` it wants, and says through `onOpen` each time a stream opens, so a reader reads
  what changed while it was down. The wire carries three new events the feed says —
  `run.changed`, `release.changed`, `worker.changed` — each with only its ids.

## [0.10.0] — one repository, one version

- Published from [pinecall/pinecall](https://github.com/pinecall/pinecall) with every other
  Pinecall package, at the one version they all carry from here on. Nothing a tenant
  imports changes.

## [0.9.28] — the wire reads evals.spent, call.started.expects and call.summary.run

- The wire reads `evals.spent` (what the harness asked a model — a judge tried, personas
  written, a case group diagnosed — its evals counted), `call.started.expects` (what a simulated
  caller expects, replacing `accepts_when`/`declines_when`), a
  `call.summary`'s `run`, and `credits.exhausted` for every quota the runtime refuses for —
  `hosted_apps`, `evals`, `simulations` and `budget_usd` were missing. Needs runtime 0.1.46.

## [0.9.27] — every judge is a model's answer, and the class names the judge's model

- **`@judge("vendor/model", { builds, options })`**: the model the agent's calls are judged on,
  over the org's and the platform's; on the org's own key — a local model through `base_url` too —
  its evals are never billed. The settings take `judge`, `judge_builds`, `judge_options`.
- The wire reads every judge as a model's answer: `ScoreVerdict` gains `classified` and `na`,
  `Judgment` gains `choice` and `score`, `call.score` gains `evals` and `own_key`, `call.summary`
  gains `simulated`. The judge rows are the runtime's new ones — `JudgeRequest`, `JudgeRow`
  (`owner`, `on`, `answer`, `choices`, `when`, `trigger`, `reads`), `JudgeList`, `JudgeTry`,
  `JudgeTried` — and `RunsOn`, `JudgeSchema`, `JudgePut` are gone. Needs runtime 0.1.45.

## [0.9.26] — a greeting is words or `improvise`, a hangup is words or `true`, and the ears choose who ends the turn

- **`static greeting` is a string** (said as written) **or `improvise`** (the model opens on its
  prompt) **or `improvise("…")`** (with an instruction); `{ text, interruptible }` and
  `improvise("…", { interruptible: true })` for an opening the caller may cut short, which by
  default they cannot. The `{ say }` / `{ reply }` objects are gone.
- **`static hangup` is a string** (when, in your words) **or `true`** (whenever the model judges);
  the `{ when }` object is gone.
- **`@stt(…, { endOfTurn: "stt" | "livekit" | "smart-turn" })`**: who says the caller's turn is
  over — Soniox with Smart Turn v3 is one line. The wire's `end_of_turn`, on the declaration and
  the settings. Needs runtime 0.1.43.

## [0.9.25] — the class declares its voice, its models and the rest, and wins

- **A class declares its environment again, and it wins over the settings.** `@voice("<vendor>",
  "<id>", { model })`, `@llm("<vendor>/<model>", { temperature })` and `@stt("<vendor>/<model>")`,
  and `static` fields for the rest: `language`, `greeting`, `hangup`, `turn`, `says`, `hears`,
  `knowledge`, `docs`, `memory`, `record`. A field the class declares is not read from the
  settings, the console shows it "set by the class", and `pinecall agent set` of it is refused.
  Needs runtime 0.1.42.
- **A plugin's own class and options**, on any of the three: `@llm("openai/gpt-5.4-mini", { builds:
  "responses.LLM", options: { use_websocket: true } })` runs the OpenAI Responses API over a
  WebSocket. Only on the org's own key for the vendor; refused on a key Pinecall lends.
- `@pinecall/agents/wire`: the settings' `temperature`, `llm_builds`, `llm_options` and the `stt` and
  `tts` twins, and `fixed` on the settings and lexicon answers, the fields the class declares.
- An environment field written on the instance (`language = "es"`) is refused at load with how to
  declare it: an instance field is a call's state. The old refusal that named a CLI verb is gone.

## [0.9.24] — a tool announces itself

### Added

- `@tool({ announce: "Let me check the agenda." })`: what the agent says as the tool starts, when the model's turn said nothing itself; a turn that spoke and then called the tool is not announced twice. Needs runtime 0.1.11.

## [0.9.23] — a call runs on the day a golden pinned

### Added

- `call.today` is the day `call.started` names when a golden pinned one (`today`), so an agent resolves "on Monday" against the golden's day, as the model does; the clock's day otherwise, as before. The field needs runtime 0.1.10.

## [0.9.22] — a refused registration is a sentence

### Changed

- A registration the gateway refuses — a slug that belongs to another org, a key it does not take — is one sentence on stderr and exit 2 from the serve entry, instead of a stack trace and exit 1.
- `docs/` is the package's own reference again — the tutorial, the class, the view, testing, production — instead of five stubs pointing at the site; the site's SDKs tab is synced from it.
- The README installs the framework alone in a project, and the CLI once per machine: a project no longer lists `pinecall`, since Pinecall starts a hosted project with its own. Every example is in English.

## [0.9.21] — a project starts with `pinecall new`

### Changed

- **The quick start begins with `pinecall new front-desk`** (CLI 0.9.22): a project of one agent,
  its test, a golden and the toolchain, instead of a clone of this repository's example.

## [0.9.20] — the package is @pinecall/agents, and the CLI is its own

### Added

- The wire reads `call.started.state`, the state a call opens in when its opener asked for one,
  and `agent.register` may carry `answers_dev`. `pc.agent(slug, { answersDev: true })` registers
  a socket that answers the console's dev verbs and declares nothing; `pc.onEntries` hands over
  every entry as the gateway wrote it.
- **`@pinecall/agents/serve`**, the entry the CLI starts an agent with: `start --file --slug [--console]
  [--events]` holds the agents (the door from `PINECALL_URL`, `PINECALL_KEY`, `PINECALL_ENV`
  only; leaves draining on a signal or the end of its stdin; answers `view.render` alone) and
  `prompt --file --slug [--state field=json]…` prints a prompt. A class it refuses — a field the
  world sets, a tool with no docstring — is one sentence and exit 2, never a stack.
- `pinecall chat --inspect[=host:port]` and `--inspect-brk` open the agent's process to a debugger.

### Changed

- **Breaking: the package is `@pinecall/agents`, and the CLI is a package of its own.** Imports
  move from `pinecall`, `pinecall/client`, `pinecall/panels`, `pinecall/views` and
  `pinecall/tsconfig.tenant.json` to `@pinecall/agents`, `@pinecall/agents/client`, … with the
  same names under them. This package has no bin: `pinecall` on npm is now the CLI alone
  ([`cli/`](https://github.com/pinecall/pinecall/tree/main/cli)), which starts a project's agents through
  `@pinecall/agents/serve` and never loads the framework itself — so a project depends on both.
  The CLI's own changes below ship in it. `@pinecall/agents/wire` exports the runtime's shapes.
- **Breaking: a call opens in the state its `call.started` carries.** A golden's state, a persona's
  and `pinecall chat --state` ride the call to the gateway, and the class applies them after
  `onCall` and before the first render. `mount`'s `opening` option is gone, and so is the suite's
  order-matched seeding. `pinecall chat <slug> --state` now works against a colleague's agent.
  Update the CLI with the runtime that writes `call.started.state`.
- **Breaking: an agent's slug is its folder's name.** `agents/sales/agent.tsx` is the agent `sales`
  on the gateway, whatever its class is called; a class whose `static slug` says another is refused
  when it is served. A project whose folders were named apart from their classes renames them.
  `--agent` takes that name. `agent.rb` and `agent.py` count as agents of a project too.
- **Breaking: `pinecall start` runs the agent in a process of its own and answers the console
  from another socket.** It starts the agent's language's serve entry, prints its lines, and passes
  it one SIGTERM on a signal (a second, or 40 s, kills it); beside it a socket named
  `pinecall-cli/<version>` registers with `answers_dev` and takes no call. `pinecall agent list`
  shows both. `--events` prints the entry's own lines, `{type, agent, call, data}` with the data
  in snake_case as the gateway wrote it, instead of the camelCase `{type, data}`. The `s` key of
  `--ui` is gone: the gateway keeps a hash of each block, not its text. A project's agents are in
  one language, or `--agent` names one. A process manager's kill timeout is 45 s.
- `pinecall chat`, `prompt`, `test`, `simulate`, `remember` and `personas try` run the agent in a
  process of their own, its language's serve entry, stopped when the verb is done; `chat`, `test`
  and `simulate` take `--inspect` for it. The console's Chat, Tests, Simulations and Memory screens
  reach the agent `pinecall start` serves instead of mounting a second one.

## [0.9.19] — the language is the world's, and the prompt writes for the channel

### Changed

- **Breaking: the language is the world's, not the class's.** A class that still declares
  `language` is refused at load (`` `language` is the world's now, not the class's: pinecall agent
  set --language <tag> ``), and the declaration no longer carries one. The framework's rules and
  protocols are English for every agent, with one more rule: answer in the language the caller
  speaks. The always-on "talk like a person on the phone" rule moved into the `<channel>` block.
  `wordsFor`, `languages` and `DEFAULT_LANGUAGE` are no longer exported.

### Added

- **`<channel>` at the end of `identity`:** how to write on a voice call, in a website's written
  chat, or on WhatsApp, picked by the call's channel and medium; `channelRules = false` on the
  class leaves it out on every channel.
- **`this.call.medium`** (`voice` · `text`), read off `call.started`'s `medium`; from a gateway that
  does not send it, the one the channel implies (`whatsapp` is `text`, `phone` and `web` `voice`).
  The client's `Call` has `medium` too.
- **`pinecall agent set --language <tag>`** writes the language in the corner, `pinecall agent clear
  language` takes it out, and a blank tag is refused before anything is written.
- **`pinecall prompt --channel phone|web|whatsapp --medium voice|text`** prints the page a given
  call would get; without them, a phone call's — it used to print a web call's, so a `render()`
  that branches on `this.call.channel` prints its phone branch now.

## [0.9.18] — `numbers available` does not call a number free

### Fixed

- **`pinecall numbers available` says `not routed here`, not `free here`.** The list knows what the
  org routes in this world, not a number held on another org's trunk of the same Twilio account,
  which the gateway only refuses at import (`409`). The verb's help and `the-cli.md` say to check
  with `numbers import --dry-run`.

## [0.9.17] — The numbers the org owns, and which are free

### Added

- **`pinecall numbers available [--account <id>]`** lists every number the org's Twilio accounts
  own, with `free here` or `routed here` for the world asked, so the number to `import` is found
  from the terminal instead of the console's Numbers screen.

## [0.9.16] — A chat whose input ends hangs up

### Fixed

- **`pinecall chat` hangs up when its input ends.** Ctrl-D or the end of a pipe waits for the
  answer to the last line (a minute at most), then closes the call: `printf 'hola\n' | pinecall
  chat` prints the answer and leaves a call ended `caller_hung_up`, not one left open.
- **`pinecall voices` asks the box's own voice, not Cartesia.** With no `--tts` the vendor is
  `defaults.tts` of the catalogue; a vendor whose plugin lists no voices — Cartesia's does not — is
  said so in one line naming the vendors that list theirs, instead of the gateway's 404.
- **`pinecall line release` says what happened.** Let go with nobody else running the agent, it
  says the line rings nowhere until a terminal claims it, not "run `pinecall start`".

## [0.9.15] — One gateway serves both worlds

### Changed

- **A `pc_live_` key goes to the world asked.** The runtime mints a person's key `pc_live_` (it opens
  both worlds), so the prefix cannot tell it from a production server's token: the CLI no longer
  refused a person's key without `--prod` as "a production server's token" — every person was kept
  out of the sandbox. Only `pc_test_` is checked before the request; a production token asked for
  the sandbox is refused by the gateway, in its words. `whoami` says what a key is from the
  gateway's answer, not its prefix.
- **Breaking: one gateway serves both worlds, and the CLI discovers no sandbox.** `PINECALL_URL`
  is the one gateway for the sandbox and production alike (`https://cloud.pinecall.io` by default);
  a verb without `--prod` acts in the sandbox and with `--prod` in production, at the same URL with
  the same key, and the `pinecall-env` header says which. Nothing is read at
  `/.well-known/pinecall`, no sandbox key is minted or kept: `session.json` loses `elsewhere` and
  `minted`. `pinecall console` opens the sandbox's console at `<url>/sandbox/` and production's at
  `<url>/`, and `start`'s console line says the same; `pinecall whoami` prints one door, who the
  key is in the world asked, and which worlds it opens. A server's token keeps the one world its
  prefix names, and `--prod` must still agree. Needs the runtime of the same release.

## [0.9.14] — The org's carrier accounts from the CLI

### Added

- `pinecall carriers list | show | add | drop`: a Twilio account, a SIP peer or a WhatsApp number
  at Meta is kept from a terminal, where before it was only the console's Numbers screen or a
  curl at `PUT /v1/carrier`. Bringing a Twilio number to an agent is now two verbs,
  `pinecall carriers add twilio …` and `pinecall numbers import …`.
- Every secret is read on stdin and never from the command line, where `ps` and the shell's
  history would keep it: typed with nothing echoed, or piped one per line (a SIP peer's password,
  then its outbound password when `--outbound-username` is given). Nothing is printed back.
- `show` says where each of a peer's networks stands with the box's operator (`waiting`,
  `approved`, `refused`); `drop` forgets an account and leaves its numbers routed until each is
  dropped. The verb is documented in the CLI reference (`docs/the-cli.md`, "carriers").

## [0.9.13] — An app reads every entry the runtime writes since 0.1.3

### Fixed

- An app no longer loses a call because the runtime named the worker that runs it:
  `call.started` (and `call.attached`'s copy of it) reads `worker`. On 0.9.12 the strict schema
  refused the whole entry, the app never held the call, and every tool of that call answered
  "this call is no longer being served".
- `call.score` reads `judged_by` (the judge model and the hash of its questions); on 0.9.12 the
  score at hang-up was an error in the app.
- Two events the runtime writes are known: `spend.unusual` (an org spending three times its usual
  day) and `vendor.switched` (a stage moving to its fallback vendor and back).

## [0.9.12] — A deploy that packs what is there, and a secret of several lines

### Fixed

- `pinecall deploy` no longer crashes on a tracked file deleted from disk: it is left out, as
  git would leave it out. A file's execute bit travels with it; every other file is 644.
- `pinecall secrets set` reads the whole of piped stdin, so a key of several lines (a PEM) is
  kept whole, not its first line.

## [0.9.11] — Logs, stop and start for a hosted app

### Added

- `pinecall deploy logs [--follow]`: the last lines of a hosted app's process, fresh from the box —
  the verb waits for lines read after it asked, and `--follow` prints what comes until Ctrl-C.
- `pinecall deploy stop` · `start`: the process drains and nothing runs, its releases and token
  kept; started, its newest release runs again. `deploy list` says `stopped`.

### Changed

- `pinecall deploy rollback <n>` asks the box to keep release n's sources as the next release,
  instead of downloading them and sending them back. Needs runtime `bbfaa80` or later.

## [0.9.10] — `pinecall deploy`: the box runs the project

The box runs the project for an org that has no server of its own: `pinecall deploy` uploads it,
the box installs it and starts it in an isolated container, and a deploy cuts no call. Needs a
gateway with hosted apps (runtime `fee2c7f` or later, what `box.pinecall.io` runs).

### Added

- `pinecall deploy`: the project run by the box itself. It uploads the folder as a release (what git
  would commit, never `node_modules` or `.env`), and the box installs it from the lockfile and
  starts `pinecall start` in a container of its own, on a token it minted for the app; the verb
  follows it until it is live — the release before answers until then — or failed, with its last
  lines. `deploy list`, `releases`, `rollback <n>`, `rm`.
- `pinecall secrets list | set | rm`: what the org's hosted apps are started with, per world; the
  value typed without echo or piped, never read back.

### Changed

- `pinecall start` prints the console's one-use login link only to a terminal. Under pm2, systemd,
  a container or a hosted app its stdout is a log somebody reads later, so the `console` line is
  the address alone and no code is minted.
- The documents an agent searches are no longer part of the project: the base lives on the
  gateway and is written in the console's Settings ▸ Docs. `docs push` still sends a local folder
  (`docs/<name>/` by default), kept out of the repository, and a deploy no longer pushes it —
  a push replaces the base whole and would take out what was added in the console.

## [0.9.9] — Runtime v2's wire, money in dollars, the org's data and its judges

The first release that speaks runtime v2's wire, the one `box.pinecall.io` runs since 2026-09-29:
every earlier version breaks on it (a call's cost in dollars, `accepts_when` on `call.started`).
Built from the repository started over on 2026-09-29, so its provenance names a commit that exists.

### Added
- **`pinecall data reads [<call|number>]`**: who read the org's calls and recordings, and the
  operator's reads and tracebacks — the org's access log.
- **Compliance judges at hang-up**: every judged call's `call.score` now carries `identified` (an
  outbound call's first words name the org), `disclosed` (the agent says it is automated early, or
  when asked) and `honoured_stop` (a caller who asked to stop went on the do-not-call list, which
  `this.call.optOut()` does). Settled by the runtime's code, at no model cost.
- **`this.call.optOut(note?)`**: the caller asked never to be called again — their number joins the
  org's do-not-call list with the call beside it, and no call of the org reaches it until a consent
  is recorded. Sent as `call.opt_out`; nothing lands in the log.
- **`pinecall data consent <number>`** (`--give express|written --source`, `--opt-out`) and
  **`pinecall data dnc`** (`list`, `add`, `import <file>`): a number's consent and the do-not-call list.
- **`pinecall data`**: `erase call <id>` and `erase contact <number|id>` (with `--yes`), `erasures`,
  `policy` (`--retention-days`, `--calling-hours 9-20`, `--per-number-day`, each clearable;
  `--consent-everywhere`; `--disclosure '…'`/`--no-disclosure` and `--no-recording-notice`, what a
  spoken call says before its greeting) and
  `export [--out <file>]` — the org's data erased, its trail, its rules, and the whole world taken
  out as JSON Lines.
- **`pinecall judges`**: the agent's own judges — `add <name> --asks '…' [--on every-call|simulations]`,
  `list`, `rm` — a question about its job the judge model answers at hang-up beside the runtime's
  panel, kept by the gateway for both worlds; its verdict is in `call.score` under its name.

### Changed
- **A lexicon is one agent's**: `pinecall lexicon` reads and writes the words of the agent of this
  directory, or the one `--agent <slug>` names, at `/v1/agents/{slug}/lexicon`; the org-wide
  `/v1/lexicon` is gone. Each agent keeps a copy of the words the org had.
- **Money in US dollars, as the runtime counts it**: `sessions` prints a call's cost as `$0.0676`
  and `pinecall test` its run's; the judges' line reads `judge_cost_usd`.
- **`sessions show` breaks a call's cost down**: a line per priced row under it (the model, the
  ears, the voice, the memory model at hang-up, each phone leg in minutes begun), and one for
  anything the box had no rate for.
- **The wire is the package's own**: the package keeps the runtime's wire it speaks in
  `src/wire/` (the types, the schemas, the reducer), held to the runtime's golden log. A tenant's
  install pulls one package fewer; nothing a tenant imports changes.
- **A persona is one agent's**: `pinecall personas` reads and writes the callers of the project's
  agent (`--agent <name>` when it holds several), at `/v1/agents/{slug}/personas`; `simulate
  --persona` finds the caller among that agent's own, and `push` sends a project's files as its
  agent's. Two agents of an org may each have a caller of the same name.

## [0.9.8] — The longest a voice call runs, and a caller who is also on the site

### Added
- **`pinecall agent set --max-duration 1-60|off`**: the longest a voice call of the agent runs, in
  minutes (ten unless set; `off` for none). Shown on the settings page as `max-duration`, and
  `pinecall agent clear max-duration` gives it back to the corner below. Needs runtime with protocol 0.6.10.
- **A caller who is also on the site.** `this.call.claimed` is the code a page showed that the
  call claimed — keyed on the phone, or claimed by the class with `this.call.claim(code)` when the
  caller said it — and `null` until `call.claimed` lands. The client's `Call` has the same field and
  verb.
- **The claim is heard the moment it lands, and survives a hand-over.** A `render()` that reads
  `this.call.claimed` is sent again as soon as `call.claimed` arrives, not at the caller's next
  turn; and a call adopted mid-conversation (`call.attached`) keeps its claim.

### Changed
- `docs/production.md` gains the table of what a team carries from the sandbox to production and
  by which verb; `worlds-and-teams.md` points at it.

## [0.9.7] — The sandbox answers at its own address, and the voices can be heard

### Added
- **`pinecall voices`.** A vendor's voices in a language, one per line with the id the `voice`
  setting takes and where the accent is from (`--country ES` keeps Spain's); `voices play <id>`
  says a sentence in one of them and plays it here, with how long the vendor took to start. With
  no words the gateway reads a line in the language; `--save` keeps the WAV; a player that fails
  is said so and the file kept; the list is the protocol's `VoicesListed`, parsed as such.

### Changed
- **Breaking: the sandbox is an instance of its own, and the CLI knocks at it there.**
  `PINECALL_URL` is production's — the identity, where a person signs in — and a verb with
  `--prod` knocks there with the project's key. Every other verb knocks at the sandbox production
  names at `GET /.well-known/pinecall` (`elsewhere`), with a key minted there from a one-use code
  production's key asked for, kept in `~/.pinecall/session.json` and minted again once when the
  sandbox answers 401. Every request and socket now says `pinecall-env` — the world it believes it
  reached, which the other instance refuses. `pinecall console` and `start`'s console line open the
  console of the instance the verb knocked at, with a code minted there; `pinecall whoami` prints
  both doors; `pinecall line from` keeps the phone under the sandbox's URL. A gateway of one
  instance — production naming no `elsewhere`: a laptop's, a box of one — is where everything
  happens: a verb without `--prod` runs there in production, and its door line says `production
  (the only instance)`. **A gateway that names no `world` at `/.well-known/pinecall` is refused
  in one sentence**: it is older than this CLI, so update the gateway before this. A server's token
  belongs to the instance it was made on: `pc_live_` needs `--prod`, `pc_test_` refuses it, and
  nothing is derived from either. Needs the runtime with instances (M1, M2).

### Removed
- **`pinecall numbers move`.** A number is one instance's: it is imported where it answers, and
  the runtime has no door that moves one between the worlds any more.

## [0.9.6] — The chat that comes back, for real

### Fixed
- **A chat the gateway refused on the way back no longer dials for ever.** The patience for a
  dropped chat socket reset on every open, and the door opens before it knows whether the call can
  be taken up; it now resets when the call answers. And the keyboard is not paused once closed.
  Found restarting the gateway under a `pinecall chat` against the box.

## [0.9.5] — A written call outlives the gateway

### Changed
- **`pinecall chat` and the console's chat carry on through a gateway restart.** A written call runs
  in the gateway, and a restart dropped the socket and ended the chat. The socket is now dialled
  again naming the call (`?call=`), for about a minute, and the conversation goes on where it was,
  history and state whole. Only the person leaving, or the call ending, closes it. Needs the
  runtime of 2026-09-24.

## [0.9.4] — A deploy never cuts a call

### Added
- **A deploy never cuts a call.** `pc.drain()` hands this process's live calls to another process
  holding the agent, or keeps them for the next one, and lets the tools running finish; a call
  handed to this process mid-conversation arrives as `call.attached` and is adopted — its state
  restored, the whole prompt sent, no `onCall`.

### Changed
- **`pinecall start` drains on `SIGTERM` and `SIGINT`** before it exits, and says in one line where
  the live calls went. Give it 40 s of grace under its process manager (`docs/production.md`).
- **A number `this.call.transfer(...)` dials passes the org's dial guards** — shape, and the
  per-minute and per-day windows — because the leg goes out on the org's own carrier. Refused,
  nothing is dialled and the value you get back says which guard said no.

## [0.9.3] — The desk takes a pipe

### Fixed
- **`pinecall supervise` takes a pipe.** Fed its moves on stdin —
  `printf 't\nq\n' | pinecall supervise <call>` — the desk sent them and then died with
  `ERR_USE_AFTER_CLOSE`: the transcript kept drawing a prompt on the interface the keyboard had
  already closed, and it outlives that interface by however long the next entry takes. The prompt
  is now drawn for a terminal only, and leaving stops the transcript instead of waiting on an
  entry that may never come — which is what a piped desk hung on once it stopped crashing.

## [0.9.2] — Handing a call to a person

### Added
- **`this.call` hands the call to a person.** `transfer(to, {mode?})` sends a phone caller on with
  a REFER, or dials the number into a browser caller's own call and falls silent once it answers;
  `attention(reason, {waitS})` asks for a supervisor and holds the caller until somebody takes the
  line or the wait runs out. Both settle on what the runtime wrote in the log — `{ok, error}` —
  so the tool decides what the caller is told. And `hold()`, `unhold()`, `dtmf(digits)`,
  `callback(number, {when?, note?})` and `hangup(reason?)`. `docs/contact-center.md`.

## [0.9.1] — A persona's model, voice and verdict, and a class that declares no doors

### Changed
- **`pinecall simulate --turns` defaults to 15, not 6.** Six was the length of a walkthrough, not
  of a call: a booking that settles an address, takes the property, the size, the condition, a day
  and a window and then confirms is past six turns before it has begun, so every simulation was
  testing the opening of an agent and the end of none.

### Added
- **`pinecall personas add|edit --llm --tts --voice --accepts-when --declines-when`.** How a caller
  is played — the model that improvises it and the voice its lines are read in, in the words
  `agent set` takes — and its own rule for a call. `pinecall simulate --judge` then scores a
  `persona` row: `held` when the caller hung up satisfied, `broken` (exit 1) when it declined.
- **`pinecall agent set --eot-threshold` and `--eager-eot-threshold`.** How sure the ears have to
  be that the caller has finished before the turn is called over, and the lower bar at which they
  say it might be. Deepgram measures a fifth of the turns ending before the person had finished at
  its own default of 0.7, so this is the knob that decides whether an agent answers half a
  sentence; `--eot-threshold 0.85 --eager-eot-threshold 0.4` is Deepgram's own pairing for a line
  that must not cut anybody off, and the eager bar is what keeps that from costing latency.
- **`pinecall agent set --record on|off`, and `clear record`.** Whether this agent's calls keep
  their audio, per world and per corner like every other setting. It is `on|off` and not a bare
  flag on purpose: the answer worth being able to give is no. Nobody's calls stop being recorded
  by this release — a corner that says nothing keeps them. A class that declares `record` is
  refused at load, by name, like every other field that is the world's.

### Changed
- **A class declares no doors: `phone`, `whatsapp` and `web` are read by nobody.** A number is
  bought, pointed at an agent and moved by whoever answers the telephone — `pinecall numbers
  import <+34…> --agent <slug>`, or the console's Numbers screen — and that was already the only
  way to MOVE one: a door a class declared could not be moved, dropped or reassigned, and the
  gateway logged a warning every time it lost one to the row that outranked it. And the web is not
  a door at all now: every agent can be talked to from a page without being turned on.

  Nothing is refused. The three fields are ignored, like any other field a class makes up, and
  they stay on `CONFIG_FIELDS` so an old class's `phone` is still kept out of the agent's state.
  What an agent ACTUALLY answers at is the new `doors` line of `pinecall start`, read off the
  gateway on every connect — so a number pointed at it while the process was running shows up
  without a restart. `pinecall numbers list` drops "declared by the app": every door is a row.

  `routesOf`, `phoneRoute`, `whatsappRoute`, `webRoute` and `RouteInput` leave the package's
  public surface, and `AgentOptions.routes` with them.

### Fixed
- **A written `pinecall simulate` stops when somebody hangs the call up.** The caller improvised
  its remaining turns down a socket the gateway had already sealed, waiting thirty seconds on each
  for an answer that was not coming. `call.ended` on the log is the end of the conversation, here
  as it is for a spoken run.

## [0.9.0] — The console is the box's, at a second name of its own

The one place a tenant looked at their sandbox was a server on their own laptop. It is a name the
box answers to now, so there is nothing local to run — and the middle number moves because a verb
was taken away.

### Removed
- **`pinecall serve` and `pinecall start --serve` are gone.** The sandbox's console was a server on
  your own machine, `http://localhost:4100`, signing every request with the project's key. The box
  serves it now at a second name of its own (`sandbox.pinecall.io` on the cloud), so there is
  nothing local to run and nothing under `cli/` that binds a port. `pinecall console` opens it.
- **The console is a repository of its own** (`../console`), built into the gateway by the
  runtime. This package no longer carries a browser program, which takes eight devDependencies,
  a tsconfig and a vitest project out of it — nothing a tenant installs changes.

### Added
- **`pinecall console [agent]` opens the box's console in a browser, signed in.** The sandbox's,
  or production's with `--prod`. The key in the project's `.env` never travels: the gateway mints a
  one-use code for it, five minutes and one use, and the page spends the code for a key of that
  browser's own. `--no-open` prints the URL instead. `docs/the-cli.md`.

### Changed
- **The console reads its world off the page, not off who served it.** One bundle, two names: the
  gateway marks the page it serves at the sandbox's, and the console's one table (`lib/mode.ts`)
  keys every screen by the world instead of by the mode. Both consoles sign in the same way now,
  both sign out, and the switcher's chip links to the other name — which the box itself names, so
  a box with one name has one console and says so.
- **`pinecall start` prints a console URL in both worlds**, each with its own one-use code: the
  sandbox's at the box's second name, production's at its own.

## [0.8.17] — `pinecall/panels` is reachable

### Fixed
- **`import … from "pinecall/panels"` failed on 0.8.16.** The panel catalogue shipped inside the
  tarball, and the subpath that reaches it was added to `exports` — which is what this checkout
  resolves — and not to `publishConfig.exports`, which is what npm serves. So `@view` landed with
  its door bricked up for everybody who installs the package. A test now holds the two maps to the
  same subpaths, and it fails when one of them drifts.

## [0.8.16] — The panel beside the conversation, and a chunk that says where it came from

### Fixed
- **A `docs.sources` entry no longer throws in the client.** The gateway says which base a chunk
  came from (`DocSource.base`, protocol 0.6.3) and the schema this package shipped against did not
  have the field — and it is a strict object, so `eventOf` refused every retrieval entry: the
  console crashed drawing a call, and the agent's own client threw once a turn for any world with
  a base attached, which is the ordinary case. The dependency moves to `^0.6.3`.

### Added
- **A pane beside every conversation, and `@view` for the agent's own panel in it.** Calls drew
  the threads and the conversation and nothing else, so the person reading a thread had no idea
  who they were reading about: whether this was the first call or the ninth, what the judges had
  said over all of them, whether a supervisor had ever stepped in. The pane says all of that,
  folded from the calls the screen already listed — it asks the gateway nothing and is there for
  every agent.

  Over it sits the agent's own panel, when the class declares one:

  ```tsx
  // agents/clinica-norte/view.tsx — the tags are `pinecall/panels`
  export default async function CustomerCard(who: Who) {
    const client = await crm.find(who.contact);
    return <Panel title={client.name}><Stat label="Servicios" value={client.jobs.length} /></Panel>;
  }
  ```

  ```ts
  @view(CustomerCard, "Cliente")
  export default class ClinicaNorte extends Agent { … }
  ```

  The view runs in YOUR process — it may be async, and that is where a CRM is read — and what
  crosses to the browser is a TREE of named nodes, never code: the same JSX as the prompt with a
  different destination, drawn by the console with its own parts in the theme the reader chose. The
  declaration is one word, so a console knows there is a panel before it asks; a class that
  declares none is asked nothing at all. `docs/writing-an-agent.md`, `docs/the-console.md`.
- **Settings ▸ Bases is the whole attachment, not half of it.** The row had the base and its chunk
  count; `mode` and `min_score` could only be set from a terminal, so a person editing bases on the
  console could not see — let alone change — who searches a base or what it keeps. Both are on the
  row now, and a second attached base says out loud that several bases are ONE search: read
  together and ranked against each other, the turn handed the most generous chunk count, each floor
  read against the base that set it.

## 0.8.15 — The k lookup was on the branch a project never takes

### Fixed
- **`docs eval` in a project asks with the attachment's k too.** 0.8.13 taught the verb to ask with
  the k the agent reads its base with, and taught it on the branch a project never takes: walking
  the project hands the golden AND the base along, and the lookup was skipped exactly where every
  real run goes. Both callers now say which agent's attachment answers, instead of inferring it
  from which arguments happen to be undefined — and a test runs the verb in a project on disk.

## 0.8.14 — Five copies of one write, and the one that erased a corner

### Fixed
- **One `memory policy` erased the rest of the corner.** The voice, the stt, the llm, the greeting,
  the hangup and the attached base went out of a corner in one version, silently. The door takes
  the WHOLE set with the version it was read at, and this verb built the body on `yours` — null
  for every key that holds no corner of its own, which is a server's token, a CI key and anybody
  acting in production. `agent set` was fixed for this on 2026-09-19; the lesson had not travelled.
- **The lexicon sent the words of one corner and the version of another.** Same cause, other half:
  a key with no corner of its own wrote the team's words with `if_version: null`, so the door had
  nothing to refuse and the second of two people saving at once won in silence.

### Changed
- **One definition of a settings write.** Five verbs — `agent set`, `agent clear`, `agent
  knowledge edit`, `docs attach|detach`, `memory policy` — each spelled out "read the corner, put
  one field in, send the whole set with its version", and the one that got it wrong is what this
  release is about. They all go through `theCornerToWrite` now, which is the only place that picks
  the corner and the version, and `theCornerRead`/`theCornerWritten` are the only two answers to
  "which corner" in the CLI — the lexicon's door included.

## 0.8.13 — A golden that asked the index the wrong question

### Fixed
- **`docs eval` asks with the k a turn gets.** With no `--k` it asked at the gateway's own default
  of eight while the agent read that base with the four its attachment names: `recall@8 0.92`
  printed for calls that were running at `recall@4 0.75`. A golden asks what a turn gets, so it
  asks with the attachment's k, in this corner; a `--base` nobody said this agent reads is still
  the door's default, because there is no attachment to ask.
- **A `render()` can be about the turn it is answering.** The caller's turn reached the class's
  `call.history`, but nothing asked for a new view when it did, so a render that read it was sent
  one turn late — while the page has always said a view says what to do in THIS turn. The bridge
  renders again when the turn lands, which is the window the platform's lookups already run in.

## 0.8.12 — An unknown flag, everywhere the same sentence

### Fixed
- **`numbers list --bogus` reads as every other verb's unknown flag.** The parser sat inside the
  verb's own catch, so node's `Unknown option '--bogus'` was printed raw with exit 1 instead of
  `no such flag for numbers: '--bogus' — \`pinecall numbers --help\`` with exit 2.

## 0.8.11 — The audit of the verbs against their own page

### Fixed
- **`pinecall sessions show <call>` is a command.** `show` was read as the call id, so it answered
  `no call show on this gateway` — and `supervise`'s own refusal told people to type it. `list` and
  `show` are both optional words; what the verb does is decided by whether a call id was typed.
- **`runs diff`, `promote` and `drift` answer `--json`.** All three parsed the flag and printed the
  same lines at a pipe, which their help and their page have always promised they would not.
- **`numbers` exits 2 with no key**, like every other verb — it exited 1, which means "something
  was measured and did not hold" — and `numbers list` refuses a flag it does not take.
- **`eval` prints the gateway's sentence**, not `{"detail": …}` around it.
- **The persona roster lines up again.** Its two columns were a fixed 12 and 46 characters, so a
  name longer than that pushed its own row right; they are as wide as what is in them.

### Changed
- The page said every connecting verb opens by printing which gateway it went to; two do
  (`whoami`, `callbacks`), and it now says so. `runs drift`'s 200-call ceiling, the door
  `sessions <call>` and `supervise` ask first, and `--turns`' default are on the page too.

## 0.8.10 — Verbs that answered about calls nobody wrote

### Fixed
- **A call nobody wrote is refused by name.** `sessions show CA_typo` printed a summary of nothing
  and `score not judged`, with exit 0, because the events door answers an empty page for a call
  that was never opened; `supervise CA_typo` opened a desk over an empty transcript and took moves
  that could not land. Both ask the one door that knows — `GET /v1/calls/{call}/state` — first. A
  desk also refuses a call that has ENDED, naming `sessions show` as the way to read it, and
  `sessions show` on a call still running says so rather than reporting it unjudged.
- **`runs diff` no longer says "nothing moved" over a broken run.** It compared only the cells both
  runs held, so a newer run whose goldens had all moved read as no change while its own `--json`
  listed failures. A measurement the older run never made is printed when it is BROKEN
  (`not measured → broken`, and the exit code is 1), and one the newer run stopped making is
  printed too, so a golden nobody ran is not read as a fix.
- **A flag a verb does not take is refused, with that verb's help.** `whoami --json` was accepted
  and answered with the same two lines, and node's own sentence for an unknown option names `--`
  and positional arguments. It reads `no such flag for whoami: '--json' — \`pinecall whoami --help\``
  and exits 2.
- **`--prod` is refused by a verb that reaches no gateway.** `prompt --prod` took the flag and
  rendered the same offline prompt, which reads as production having been consulted.
- **A file a flag named says what was wrong with it.** `eval --policy missing.json` and
  `prompt --state missing.json` printed node's `ENOENT: no such file or directory, open …`, and a
  file with a trailing comma printed `Unexpected token }` with no file in the sentence. Both name
  the flag and the file now, and cannot-run is exit 2.
- **The gateway's sentence, not the JSON it arrived in.** A refusal printed
  `the gateway answered 404: {"detail":"no eval run …"}`; FastAPI's `detail` is read out of it, and
  a 422 reads as the field and the rule it broke.

### Changed
- `simulate --help` lists `--agent`, `memory --help` lists `policy --note`, `runs --help` and its
  page list `--json`, and `sessions --help` names the optional `list` the verb has always taken.

## 0.8.9 — A flag that does nothing, and a refusal nobody could read

### Fixed
- **`--agent` is refused where it does nothing.** `personas list|show|add|edit|rm` parsed it and
  dropped it, so `personas list --agent whoever` answered the whole org's roster with exit 0 — a
  flag that looks like a filter and never was. It names the CLASS, and only `try` and `push` have
  one to name; the other five say so and exit 2.
- **A refused socket carries the gateway's sentence.** `pinecall simulate` with a key that does
  not open `app` printed `the gateway refused the socket: closed with 1008` — a number, for a
  refusal a person could act on in a second. The close frame's reason is the gateway's own
  sentence and it is what the app prints now. A 1008 also stops the retry loop: a key whose scopes
  do not open a door will not open it on the third try, and a client that retried for ever said
  nothing while nothing worked.
- **A listing piped into `head` exits quietly.** `pinecall runs list | head` closed the pipe and
  node printed an EPIPE stack over what a person was reading. A reader that stopped reading is not
  an error.
- **Exit 2 means the command cannot run, wherever the refusal was thrown.** A project of several
  agents with none named, a golden with no such case, a file that holds no agent class — all came
  back as 1 through the dispatcher's generic catch, so the page's own table could not be relied
  on. `CannotRun` is read once, at the door.

## 0.8.8 — What a screen says when it is refused

### Fixed
- **A refused read is said once, and never becomes a spinner.** Settings and Lexicon printed the
  gateway's refusal twice — once where the screen would have been, once at the foot — and Settings
  then cleared it on its next effect pass and sat on "Asking the gateway…" for ever, because the
  promise that had failed was long settled. The foot is for a refused WRITE; a refusal is cleared
  by a read that succeeds, not by the next attempt starting.
- **The class name stopped leaking onto the screen.** Pipeline drew `GatewayError: this key does
  not open pipeline: …` — `String(error)` is the class in front of the sentence. `saidBy` is one
  function now, beside the error it unwraps (`shared/api.ts`), and a screen prints the gateway's
  words alone.

## 0.8.7 — What the doc audit found in the code

### Fixed
- **`this.call.today` reaches the class.** The bridge built the call world from the lifecycle
  hook's shape, which has no such field, so the day the call opened — what a view and an agenda
  have to count "today" and "el martes" from — was `undefined` in every mounted agent, and a class
  that guarded it fell back to the machine's clock: a different day, in a different timezone, on a
  box. `runtime/connect.ts` builds a `CallLine` now, and `test/runtime/connect.test.tsx` pins it.
- **The Team screen's role table said what the runtime does not.** `supervisor`, `manager` and
  `developer` all open `words` — the lexicon, the opening's words, what is remembered
  (`types/member.py:ROLES`) — and the console's table omitted it for all three, so a supervisor
  reading which doors their role opens was told the wrong set.

### Changed
- **The pages say what the tree does.** An audit of every page against the code: `docs/the-cli.md`
  gained the flags it never named (`runs --json`, `memory policy` with `--agent` and `--note`,
  `lexicon hear --note`, `sessions list`); `docs/writing-an-agent.md` gained the three refusals a
  tenant hits at declaration (a tool name, `pii` naming a parameter that is not there, `stage` on a
  class with no `stage` field), what `this.call` carries besides the room (`today`, `history`), and
  the testing surface the package exports and no page named (`describe`, `runTool`, `snapshot`,
  `diff`, `logOf`, `agent.on`, `static doc`, `mount`'s options) — and lost a claim about
  `exactOptionalPropertyTypes`, which the tenant preset does not set; and
  `docs/console-content-brief.md` was brought to the console that exists.

## 0.8.6 — A simulation says who it is playing

### Fixed
- **A written simulation records its caller.** The gateway has carried `call.started.persona`
  since protocol 0.6.2, and the Personas screen reads a caller's runs off it — but nothing put it
  on the wire: `pinecall simulate` opened `WS /v1/chat` without saying who was being played, so
  every written simulation was a call nobody could attribute and the runs pane stayed empty while
  the simulations went on happening. `chatUrl` takes the name now, and `test/cli/chat.test.ts`
  pins it.

## 0.8.5 — The org's callers, and a console that knows where you came from

### Added
- **Personas opens on a standing, not on a page about callers.** Where the screen used to explain
  what a persona is, it now reads like Overview: how many callers there are and how many have
  never been called, how many runs between them, when the last one was — then **Latest runs**, the
  newest simulations of the whole org whichever caller ran them, each row the session it was, and
  **Never called**, which is the one thing on the screen somebody can act on. The explanation is
  one line, and in full only where it is needed: an org with no callers yet.
- **What a caller has actually done, beside the caller.** The Personas screen has a third pane:
  every simulation that persona has run, newest first — which agent answered, when, how many
  turns it took, how it ended, what the judges said, what it cost — and a row opens the session it
  was. It reads `GET /v1/personas/{name}/runs` in the key's own corner, a screenful at a time,
  and a caller nobody has called yet says so and points at Simulations.


### Changed
- **A persona is the ORG's, in the console and in the CLI.** The screen lists every caller the org
  wrote, with no agent to pick first — a caller is a person on the phone, not a field of an agent —
  and reads them from `GET /v1/personas`. `personas list · show · add · edit · rm` name no agent
  either; `--agent` and `--file` stay on `try` and `push`, the two that need the class.
- **The simulate form reads as a list of options.** Three switches with their sentences beside
  them wrapped mid-word in a 340px pane — "Noisy / line" — and read as one grey smear. Each is a
  line of its own now, with what it does under its name, and Max turns says what it counts where
  it is typed: the lines the CALLER says, which is what the cap has always been.
- **Whisper and Say are two boxes, not one behind a switch.** A supervisor on a live call should
  never have to check which mode they are in before pressing Enter: one of the two is heard by
  the customer. Each has its own line and its own button, and the caller's is the loud one.

### Fixed
- **Back goes back.** A screen reached from several places — a session from Live, from Personas,
  from Evals, from the palette — had one back link written into it, so it was wrong from
  everywhere but one: "← Sessions" after arriving from Personas. The frame remembers the screen it
  left (`lib/whence.tsx`), the detail page asks, and the link says where it actually goes —
  "← Live", "← Personas" — falling back to its own list on a reload or a pasted URL. The same for
  a knowledge base, which is opened from the org's Docs and from an agent's.
- **The Chat screen stops scrolling twice.** The transcript's height was the viewport minus a
  guess at everything above it (`100vh - 490px`), so a head of two lines pushed the window past
  the bottom and the page grew a second scrollbar beside the transcript's. The window takes what
  the page has left, and the lines inside it are the only thing that scrolls.
- **The desk knows a chat from a call.** A conversation with no room — the widget's chat,
  WhatsApp — opened the desk by taking a seat in a room that does not exist and asked the browser
  for a microphone to take it over. It does neither now: no ear, no seat, no microphone, and no
  Transfer, which the gateway refuses on a thread anyway. The same Whisper · Say · Take · Hand
  back · End, typed. What says which is the call's own state: `room` is null for a text session.

- **A dead page's leftovers, swept.** `ui/shared/frame.tsx` and `ui/shared/styles/` — 1154 lines —
  were the operator page's and outlived it; nothing imported them. The console wears `ui/ui.css`
  over `ui/tokens.css`, and the stylesheet test now pins that as the shared vocabulary.

### Removed
- **The operator's page is gone.** `/admin` was a second bundle with a second credential — the
  box's ops key, typed into a browser — doing a poorer version of what the console's **Box**
  group already does: Organizations, Fleet, Routes, Box usage and Box settings, drawn for a
  person the box made an operator and opened by that person's own key. One page, one build, one
  credential. A box's first org is made where it always was, on the box:
  `pinecall-runtime init --org … --email … --person …`.

## 0.8.4 — A corner that reads no base says so

### Fixed
- **A corner that reads no base says so.** The gateway resolves an agent's settings knob by knob
  now, so a missing field means "not set here" and the corner below supplies it. Settings' Bases
  section and `pinecall docs detach` both dropped the field when the last base went, which read
  as "not set" and handed the agent the team's bases instead of detaching it. Both send an empty
  list.

## 0.8.3 — Personas of their own, one Chat, and a CLI that refuses in words

### Changed
- **Talk and Chat are one tab, called Chat.** The agent had two tabs for the same room — the
  microphone, or writing. Now one screen offers both ways in: **Call** (the microphone, over
  WebRTC, and the agent answers out loud) or **Write** (text, no audio), with the conversation as
  the page's tall window, the call's own controls in its head, and the Inspector beside it as
  before. Its path stays `/a/<slug>/talk`, so links made before still land.
- **Settings keeps what is set in a pane of its own.** The corner-by-corner table left the page for
  a pane at its right, of the Inspector's kind: full height, its own scroll, dragged wider, one
  corner at a time (yours, the team's, production's) with the history under it.
- **Lexicon is two tabs.** *Pronunciation* — how the voice says a word, as a table of written and
  said — and *Recognition* — the words the ears must expect, as chips — each with what it does to a
  call in one line, over a switch saying which copy is being edited, and a save bar that says when
  there is something unsaved.
- **Docs creates a base.** **New base** on the org's Docs screen: a name, and the first documents
  picked off the disk or written there; the base is begun with them, as the gateway begins one.
- **Sessions is grouped by day.** *On a call now*, *Today*, *Yesterday*, then each date with how
  many sessions it holds; the time column says it is UTC.
- **A persona is the agent's, not the project's.** The synthetic callers left
  `test/<agent>/personas/*.ts` for the gateway, beside the agent's settings: `pinecall personas`
  (list · show · add · edit · rm · try) writes them, the console's Personas screen writes the same
  ones — in production as in the sandbox — and `pinecall simulate --persona` reads them from there.
  `pinecall personas push` sends a project's remaining files up once, evaluating each so a caller
  whose state came from `lib/` lands as the value it produced; the folder is then yours to delete.
  The dev verb `simulate.roster` is gone with them, and the class in the directory is still what a
  simulation is put on.

### Added
- **Personas, a screen of their own, above Simulations.** An agent's callers down the left, the
  one chosen read beside them — what they want, how they talk, what they know — with **Use in a
  simulation**, **Edit** and **Delete**, and **New persona**. Each field says what it does to the
  call. The page reads and writes the gateway's own doors (`GET`·`PUT`·`DELETE
  /v1/agents/{slug}/personas[/{name}]`), the same callers `pinecall personas` reads, so it works
  in production as in the sandbox and needs no `pinecall start` in a directory. Simulations'
  Persona field links to it (**Manage**).

### Fixed
- **A simulated caller no longer talks over the agent's greeting.** The first line waits for the
  opening to be said (runtime).
- **`pinecall agent set --llm haiku` no longer stores a model nobody answers to.** A short name —
  `haiku`, `sonnet`, `opus` — is expanded to the id its provider takes, through the same table
  `pinecall test --model` reads, instead of being written as typed and read by the gateway as
  `anthropic/haiku`; a word that names no model at all is refused with exit 2 and never written.
- **`pinecall personas` says what happened, and leaves with the right code.** `--agent` may be an
  agent of this project by its name and is resolved to the slug the gateway files its callers
  under; `rm`, `show`, `edit` and `try` on a caller nobody wrote all end in the same sentence and
  exit 2, as does a name the gateway's rule refuses (lower-case letters and digits joined by
  hyphens); `--json` and `--file` are documented and honoured by every verb that prints what the
  gateway answered — `try`, which prints a call as it happens, refuses `--json`; a `push` that is
  refused halfway names what landed and what is still only a file and exits 2; and a verb nobody
  wrote prints the usage without loading the agent's class.
- **The console no longer loses work without saying so.** Lexicon asks before a corner switch
  throws away unsaved words instead of dropping them silently; Settings' *What is set now* follows
  the corner the form is on; Docs' **New base** names the files that did land when an upload stops
  halfway, and says when nothing was made under the name; **Delete** on a persona sends one
  `DELETE` however often it is pressed; Simulations keeps the chosen agent in `?agent=`, so a
  reload lands on the same one; and the fields of Lexicon, Docs, Sessions, Settings, Simulations,
  Personas and Chat each have a name a screen reader can say.

## 0.8.2 — The console in the dark

### Added
- **The console has a dark theme.** It follows the system's light or dark, and the sun or moon in
  the top bar flips it; the flip is kept in the browser until the system's own theme changes.

## 0.8.1 — Docs you edit from the console, and a simulation that says why it cannot start

### Fixed
- **A spoken simulation the gateway refused no longer leaves the console waiting.** The call's id
  was handed to the page before the gateway had accepted the call, so a refusal — a server token
  without `evals`, no worker — left Simulations on *Waiting for the call's room to open…* for
  good. The id is handed over with the call's first log entry, and a refusal comes back to the
  form in the gateway's own words.

### Added
- **Docs: a base opens onto its files, and a person changes them from the console.** The org's
  Docs table opens a base (`/docs/<base>`) onto its files — File · Characters · Chunks · Arrived —
  with **Add files…** (a picker, several `.md` at once), **Write one** (a path and an editor),
  each file opened to read and edit and saved with **Save**, and **Take out**. Every change is
  searchable on the next call. A base pushed before the gateway kept its files says so, and a
  push again from the project keeps them from then on. The agent's Docs tab opens the same page
  from its rows.

### Changed
- **`--voice` says what the caller sounds like now.** The gateway reads a simulated caller's lines
  in an ElevenLabs voice the agent does not have, in the agent's language (runtime); `simulate
  --help` and the testing page no longer speak of the box's speech tool.

## 0.8.0 — Simulations you hear, Settings you pick from

### Changed
- **Simulations is a screen of its own, under Sessions.** The Simulate button left the Live floor:
  the screen starts a simulation and stays on it, and a spoken one is heard live, the caller and
  the agent, the moment its room opens. Voice starts on there, and the turns field is *Max turns*.
  The agent's Calls tab no longer simulates: its **+** is *Call a number*, once the org dials out.
- **Settings, rebuilt for the person setting it.** One tab a section — STT, LLM, Voice,
  Conversation, Memory, Knowledge, Bases — and every choice a list of values that run: a vendor
  appears only when the box has its key and runs models at it, the model is picked from those, the
  voice from the curated names, the turn's silence and interruption words and a base's chunks from
  values the runtime takes. Nothing is typed that could name something that does not exist. The
  form opens on what the agent runs on (your corner before you set it is the team's), and the
  corner-by-corner comparison sits under it.

### Fixed
- **A settings write no longer erases the corner it lands in.** The gateway writes the org's own
  corner for a key that holds none — a production token, a person acting in production, a CI key —
  and `agent set`, `agent clear`, `agent knowledge edit` and `docs attach|detach` were building the
  whole set on an empty row, so each one took out what the last one had written: on the box,
  writing the knowledge dropped the base attached a minute earlier, and setting a voice dropped the
  knowledge. Every write now reads the corner the door will write, as `agent pull` already did, and
  the line it prints names that corner and its version instead of "your corner v?".

## 0.7.0 — The class is code, the world is environment

### Changed
- **The class is code, the world is environment.** A class declares the contract — its doors,
  `language`, state, `@tool`s, events, `render()` — and nothing it runs on. `voice`, `llm`, `stt`,
  `greeting`, `hangup`, `says`, `hears`, `memory`, `knowledge` and `docs` on a class are refused at
  load, before a prompt is printed or a gateway is knocked at, and the refusal names the verb that
  sets each (`pinecall agent set --voice <name>`, `pinecall lexicon add`, `pinecall memory policy`,
  `pinecall agent knowledge edit`, `pinecall docs attach`). Nothing is seeded from the class any
  more and `pinecall start` prints no "the world wins" lines: there is no class value to differ from.
- **Knowledge and bases are two things.** What the agent knows by heart is `knowledge`: a page of
  Markdown in its settings, per world and corner, versioned, read whole into the prompt's static
  block on every call — written in the console's Settings ▸ Knowledge or with `pinecall agent
  knowledge edit` (`$EDITOR`), and open to a supervisor's or manager's key (`words`). What a turn
  searches is `bases`: the documents pushed with `pinecall docs push` and attached with `pinecall
  docs attach <base> --k <n>`. A class reaches them from a tool with `await
  this.knowledge.search(query, { k })`, and a class that searches in a world where no base is
  attached is refused at registration naming `pinecall docs attach`.
- **`pinecall knowledge` is `pinecall docs`** — `push`, `list`, `drop`, `eval`, and now `attach`,
  `detach`, `attached`. `pinecall agent` prints two rows, `knowledge` as a size and `bases` by
  name; `clear` takes either.
- **One project layout.** `agents/<name>/agent.tsx` and beside it only what that agent uses;
  `lib/` shared; `docs/<name>/` the documents it searches and nothing else; `test/<name>/goldens/`
  the conversations `pinecall test` runs with `docs.json` and `memory.json` — the retrieval and
  recall goldens — beside them; `test/<name>/personas/`; `test/<name>/memory/` the extraction
  cases. A directory holding a bare `agent.tsx` is no longer a project: the verbs look for
  `agents/<name>/agent.tsx` and say so. Business knowledge is not in the repository.
- `examples/clinica-norte` is the one example, on that layout; `examples/tienda-sur` is gone.
- `pinecall pipeline` and the console's Pipeline screen read the three legs as the next call is
  built and mark nothing as `turned` or `← set`: with no class value to differ from, every value is
  the world's, and Settings is where it is changed.

### Fixed
- `pinecall agent stop ""` asks which app, as a bare `stop` does, instead of posting to
  `/v1/apps//stop` and printing the gateway's 405.

## 0.6.0 — What is running, where, and a stop it obeys

### Added
- **What is running, and a stop.** `pinecall agent list` prints every process holding the org's
  agents in the world asked — the agents, whose corner, the machine and address, the SDK, since
  when — and `pinecall agent stop <app>` closes one: the process prints `stopped by <name>` and
  exits instead of dialling back. The console's Overview gains the same list, with a Stop per row.
  The SDK sends the machine's name at `agent.register` and hears a stop on `pc.onStopped`.

## 0.5.0 — One key a person, a project linked to its org, `pinecall start`, and nothing promoted

### Added
- **`pinecall link`: a project's folder is linked to one org.** In the project's folder it signs
  the machine in through the browser if it is not, asks which of your orgs this is (`--org`
  names it), mints your key there and writes `PINECALL_KEY` — and `PINECALL_URL` when the gateway
  is not the cloud — into `./.env`, leaving every other line as it was, and warns when `.env` is
  not in `.gitignore`. A second org is a second folder.
- **One key per person, and `--prod` on any verb.** Your role says what you do; a per-person
  **production** switch, set by an admin (an admin's is always on), says whether you may do it in
  production. `--prod` anywhere on the line sends `pinecall-env: production` for that command; the
  gateway answers `403 <name> has no production access: an admin gives it in Team` when the switch
  is off. Nothing named is the sandbox. `pinecall whoami` ends `· production: yes|no`.
- **`pinecall agent`: what the org set over the class, per world and per corner, a version a row.**
  The three corners on one page — yours, the team's, production's — `set` with the version it
  was read at (a corner that moved is told so, never written over), `clear`, `history`, `diff`,
  `rollback`, and `pull`/`push` for whoever keeps a corner in git; `--team` writes the team's,
  `--prod` production's. `list` prints the agents held. The class's own `voice`, `llm`, `stt`,
  `greeting`, `hangup`, `memory` and `docs` seed a world that has nothing set, once; after that
  **the world wins**, and `pinecall start` prints one line per field the class still says
  differently, with what to delete.
- **`pinecall lexicon`**: the org's words — how the voice says a brand, what the ears must know —
  laid over every agent's own `says` and `hears`, whole and versioned per corner, production's with
  `--prod`. A supervisor's or a manager's key opens it (`words`). **`pinecall memory policy`** is
  the memory field of the settings on its own.
- **Agent ▸ Settings and Org ▸ Lexicon in the console.** The corners, the form, the history with
  roll back. On the gateway's console both are **editable**: they write production's corner
  directly, with its history and rollback. A `words` key sees the opening and the memory as fields
  and nothing else.
- **Tokens, where Keys was** (`/tokens`, open to every key): your own keys, and **New server
  token** — a label and a world, production's only for somebody with production access — shown
  once as `PINECALL_KEY=…` for the server's secrets. A server token (`pc_live_`/`pc_test_`) is the
  org's and outlives whoever made it; the list says which world, whose ("the org's · made by Ana",
  "Bruno · their own"), when it was last used, and revokes. Overview says "New server token" and
  "Tokens in use".
- **Team ▸ Production**: a switch per person (an admin's reads *always*), and one in the invite
  form. A person without it who opens the gateway's console sees **No production access**.
- **The SDK takes the world.** `new Pinecall({ url, apiKey, env: "production" })` for a person's
  key; a server's token needs none. `World` is exported from `pinecall/client`. With `mount`, an
  app runs the agent inside its own server — `docs/production.md`.

### Changed
- **`pinecall run` is `pinecall start`.** `pinecall start --prod` runs production's agent, on a
  person's key with production access or on a server's token; `--serve` stays the sandbox's.
- **The key is the project's.** Every verb reads `PINECALL_KEY` and `PINECALL_URL` from the
  environment, else from the nearest `.env` up from where it runs; the gateway is
  `https://box.pinecall.io` unless one names another. v1's `PINECALL_API_KEY` is never read. The
  first line says `key from the environment` or the `.env`'s path.
- **`pinecall login` only signs the machine in**, kept in `~/.pinecall/session.json` (0600,
  `PINECALL_HOME` moves it) with the phone `pinecall line from` said; no verb runs on that key,
  `link` mints from it.
- **The local console, refused, says** *This project is not linked*: `pinecall link`, then
  `pinecall serve`.
- **`pinecall pipeline` reads.** `set` and `clear` say where they went (`pinecall agent set`) and
  exit 2; the Pipeline tab lost its form and points at Settings. The hold melody stays where it was.
- **`agents` left the planned verbs**: it is `pinecall agent list`.
- **Team ▸ Roles says `supervisor` and `manager` open memory**, as the runtime's presets now do.
- **Memory in the sidebar, beside Evals.** What every agent of the org carries between calls, on
  one page: each fact with the agent whose call taught it (a link to that agent's Memory tab), a
  search the gateway runs across every page, **Drop**, and **Load more**. `GET /v1/memory`.
- **Pipeline ▸ Hold melody.** What the caller hears while a tool runs, on the phone and on the
  web: the runtime's own melody, a file of yours (**Upload a file…**, converted by the gateway),
  or off, with **Listen** before a caller does. It has its own doors (`…/pipeline/hold-audio`) and
  is saved when chosen, never by the knobs' Save, which replaces their whole set.

### Removed
- **Profiles**: `~/.pinecall/config.json`, `pinecall config`, `pinecall use`, `pinecall gateway`,
  `--profile`, `pinecall login --key-stdin`/`--as`, and the `"pinecall": { "org" }` field of a
  package.json. A project is linked instead; a server keeps its token in its secrets.
- **`pinecall keys`**: a server's token is made in the console's Tokens screen.
- **`--env` on `start` and `chat`**: `--prod` says the world. `numbers move --env` is unchanged.
- **Promote, for settings and words**: `pinecall agent promote`, `pinecall lexicon promote` and
  the console's Promote buttons. `--prod` writes production directly, history and rollback are the
  safety, and the goldens (`pinecall test`, `pinecall knowledge eval`) run in CI before a deploy.
  `pinecall runs promote`, a call written down as a golden candidate, is unchanged.

## 0.4.0 — The project names its org, `--prod` looks at production, and no signup

### Added
- **A project names its org, and every verb inside it takes that org's profile.** `"pinecall": {
  "org": "<slug>" }` in a package.json; the nearest one that names an org wins, `--profile` still
  wins over it, and a machine holding no profile of that org is refused rather than handed the
  active one. Outside a project nothing changes. Four checkouts of four orgs need no `pinecall use`.
- **`--prod` looks at production for one command.** Any verb, anywhere on the line: it takes the
  profile's production key for that command and keeps nothing, so the next one is in the sandbox
  again — no `pinecall use <org> production` and back. `--env` keeps its meaning where a verb
  takes it.

### Removed
- **`pinecall signup`.** A terminal no longer makes an org: whoever runs the gateway makes it and
  invites people, who arrive with `pinecall login`. The gateway's `POST /v1/signup` door is not
  changed.

### Changed
- **`pinecall config rm` keeps the gateway this machine is pointed at.** It forgets the profile
  named, and the active mark when that was the one, and no longer drops what `pinecall gateway
  <url>` wrote.
- **The console's Live and Chat read the reply in flight from the wire's
  reducer.** `agent.transcript` is a delta — one word with its timings on a voice call, one model
  token on a written one — and the reducer joins them into `state.live.agent`, cleared by
  `turn.agent`; the console keeps no joining of its own. The dependency is `^0.3.0`.
- **The console's Live screen.** The words being said are the call's last row, word by word, and
  the list follows them down; the pane is 320 to 400px and every pane is dragged wider or narrower
  and found as it was left; a measurement is a ruled row that never breaks a number.
- **A session with no audio to play draws no player** — a written call keeps no recording.
- **Team draws no Disable and no Remove on your own row.** The gateway refuses both for the person
  asking; the screen no longer offers them.
- **No country codes in the console.** The dial guards are four; which countries a dial may reach is
  the carrier account's own setting.
- **The console carries the new logo and mark.**

## 0.3.1 — One login for every org and both worlds, and the console redesigned

### Added
- **`pinecall gateway [url]`** — where this machine is pointed, and one word to point it somewhere
  else. Every verb goes to `https://box.pinecall.io` until it says otherwise, so a person on the
  cloud types `pinecall login` and nothing else; a box of your own is named ONCE and every verb
  after it goes there. A URL on `pinecall login` still wins for that one command.

- **One login keeps every org and both worlds.** `pinecall login` writes a profile per org the
  person belongs to, named after the org, each holding their sandbox AND production key (the
  gateway mints them from the one in hand). `pinecall use <org>` moves between orgs and `pinecall
  use <org> production|sandbox` between worlds, with no second login; `pinecall config` says which
  worlds a profile holds. A person still only LOOKS at production: `app` there is a machine's key.

- `pinecall signup` asks for a password in the GATEWAY's own rule, read from
  `/.well-known/pinecall`, instead of a number of its own that could refuse what the box accepts.

### Changed
- **A machine with no profile is on the cloud, not on localhost.** `pinecall login` with no URL was
  already the cloud's; now the same is true of every verb that runs before a key is kept, and the
  refusal says *not signed in to <gateway>* with the one-word verb that fixes it.
- **The console, redesigned.** One light theme in Inter, its colours in one file
  (`ui/tokens.css`) and its parts in `ui/` — page, card, stat, grid table, controls, pill, icons
  drawn in the repo. A sidebar in three groups (Agents, Gateway or Sandbox, Settings) with live and
  count badges, folding to icons; a top bar with a switcher whose two environment chips open the
  OTHER console at the same path; an agent's head and tabs; ⌘K over screens, agents and listed
  sessions. **Overview moved to `/overview`**; `/` is Home. The table in `lib/mode.ts` now carries
  each screen's group and icon. The dark theme is gone.
- **Live is the org's floor in three columns** — the calls, one watched, what it holds — with the
  whole supervisor's desk under the call's head; a simulated call opens there. **Calls is an
  inbox**: an agent's sessions grouped by contact, their messages read from each call's log, and a
  composer that writes as the agent into a live text call.
- Sessions search by id, number, caller and outcome, filter by agent and channel, and open a call id
  pasted whole; Talk and Chat sit beside an Inspector of the call's log; a chat that has ended reads
  as a transcript.

### Added
- **Home**: today against yesterday, the calls that need a look, who is on the floor, where calls
  arrive, and what is left to set up.
- **On a gateway with the console's doors** (the runtime's `docs/protocol/console-api.md`; each is
  probed, and an element whose door answers 404 is not drawn): the day's numbers, the median answer
  and the budget (`GET /v1/insights`); `escalated · low score · promise made` on a row; judging
  turned on from Home; sessions searched, counted and paged by the gateway; unread and names in
  Calls, and a message into a WhatsApp thread inside its window; every fact an agent remembers, one
  dropped; a judge attached to a finished call; the widget's title, tagline, greeting, accent and
  autostart kept per agent and world; the workspaces a password opens, offered on the sign-in card;
  a member's password reset by a one-use link from Team, and *Forgot password* saying so.
- **Talk takes writing beside the voice**: a composer under the conversation sends what is typed
  into the same call (LiveKit's `lk.chat` text input), and the transcript reads as bubbles.
- **A session opens on its recording**; consent proof, the prompt's blocks and the full log fold
  under one *Details* card that a `#seq-N` link opens.
- **Team**: a Roles table — what each role opens — and **Single sign-on**, an org's own OpenID
  Connect provider set from the console (`GET`/`PUT`/`DELETE /v1/org/sso`); the sign-in card offers
  *Continue with SSO* on a gateway that has it, finding the workspace by the email's domain.
- **Outbound calls**: Numbers sets the org's outbound trunk up plan-first and shows the guards an
  operator set (`GET`/`POST /v1/carrier/outbound`), a SIP carrier declares where the box sends the
  calls it places, and the Calls inbox gains *Call back* and *Call a number* (`POST
  /v1/agents/{slug}/dial`) once the org can dial.
- `lib/sessions-wire.ts`: session lists read with `score`, `flags`, `total` and `next` optional,
  until the protocol that carries them is published.

## 0.3.0 — The sandbox's console on your machine

### Added
- **`pinecall serve`: the sandbox's console, on your machine.** `http://localhost:4100` is the
  console for what YOU are running — your copies, their calls, chat, suites, knowledge, memory, the
  widget, phone testing. It is a sidecar: every request is forwarded to the gateway with the
  profile's sandbox key, which never reaches the browser, so there is no login. One per machine (a
  second one for the same gateway and org points at the first), loopback only, and a foreign `Host`
  or `Origin` is refused. `pinecall run --serve` is both in one terminal; a plain `run` names a
  sidecar that is up. A production key is refused with where production is watched.
- **Phone testing**, a screen of the local console: the org's production numbers, the agent each
  reaches, and whether the gateway knows which phone is yours (the runtime's `GET /v1/line/numbers`).
- `Pinecall#onConnected(listener)`: heard on the first connect and on every reconnect.

### Changed
- **The gateway's console shows production, and only production.** The world toggle, the world
  choice at sign-in and the copies per person are gone from it; Chat and running a suite are the
  local console's. One bundle, two modes, and which screens each has is one table
  (`src/cli/ui/console/lib/mode.ts`). A browser that held a sandbox key from before is moved to the
  same person's production key.
- `pinecall run` in the sandbox prints the local console's URL, or the verb that opens it, instead
  of a gateway link with a login code. In production it prints the gateway's, as before.
- The phone `pinecall line from` kept is re-sent on **every** connect, in every mode, not once per
  start in the plain log only.

### Fixed
- `pinecall knowledge push <dir> --agent <name>` (and `eval <golden> --agent`) ignored `--agent` at a
  project's root; the agent named gives the base.
- The usage of `chat`, `prompt` and `line` says `--agent`, and `line` says it works on a production
  number. Evals' empty roster names the goldens folder of a project, not only `test/goldens`.
- A gateway that restarted printed a stack per redial under `pinecall run`. It is one line now,
  `gateway  … — reconnecting`, and `gateway  back`.
- **Test on the production number.** `pinecall line from <+your-phone>` now reaches your sandbox
  copy on a production number too (the runtime's `rings-for` door): your phone reaches the agent
  you are running, every other caller reaches production. `pinecall run` re-sends the phone when
  it starts, for every agent, not only one that declares a number, so a gateway that lost it learns
  it back from the next run instead of quietly sending your test call to production.

## 0.2.0 — A project of several agents

### Added
- **A project of several agents.** `agents/<name>.tsx` at a repository's root, with every folder
  the verbs read shared by name — `knowledge/<name>.md` and `knowledge/<name>/`,
  `test/goldens/<name>/`, `test/personas/<name>/`, `memory/<name>.golden.json`. At that root
  `pinecall run` holds every agent on one socket, each line prefixed by its slug; `test`,
  `knowledge push|eval` and `personas list` act on each agent against its own folders; `chat`,
  `simulate`, `prompt`, `remember`, `memory eval` and `line` take `--agent <name|slug>`. One agent in
  its own folder reads beside its `agent.tsx` as before. The paths are one function,
  `src/cli/home.ts`, and every console door (goldens, chat, simulate, knowledge, memory) reads the
  agent's home.
- **No goldens is none, not an ENOENT**: an agent with no `test/goldens` yet has an empty roster.
- **0.1.0, and every dependency comes from the registry.** A `workspace:*` range is rewritten by
  pnpm to the version of the checkout next door, which is not a version anyone can install.
- **A release is a tag, and the tag has a guard in front of it.** `release.yml` fires on `v*`:
  `guard` refuses unless the tag and `package.json` say the same number, `gates` runs the same
  `ci.yml` every push runs — a tag is not a branch, so without that the release path had no gate
  at all — and only then does `publish-npm` touch the registry, over OIDC with no token stored
  anywhere. The package is packed with `pnpm pack` and published with `npm publish <tgz>`, because
  `npm pack` does not apply `publishConfig`: the manifest it builds still points `main` and `bin`
  at `src/` and `bin/`, neither of which `files: ["dist"]` ships. `scripts/the-version` refuses
  while a dependency is `workspace:*` — pnpm would rewrite it to the version of the checkout next
  door, which is not a version anyone can install.
- **`pinecall numbers`, and `numbers move` crosses the two worlds.** An org buys ONE number, so a
  team wanting to try a new agent on the real line had nowhere to try it: a second number is a
  second bill, and a third world would be a third of everything. `pinecall numbers move +34… --env
  sandbox` points the org's own number at the sandbox for an afternoon and back again — one row,
  in effect on the next call, with the carrier untouched because a call arrives at this box
  whichever world answers it. Beside it: `list` for the key's world, `import` off the org's
  carrier account (`--dry-run` prints the steps and writes nothing) and `drop`. It replaces
  `phones` in the planned table, because the door, the console's screen and the runtime's CLI all
  say numbers.
- **The front page says whose corner each agent is, and filters by it.** The sandbox holds one
  agent per person, and a key that opens `team` — an admin's, the operator's — is now answered
  every member's corner rather than only its own, so the same slug arrives several times. The page
  gains a WHOSE column and a choice of *everything* / *mine* / *the team's*; the selector and the
  rail's count stay one row per slug, because a screen is addressed by slug alone and the door
  behind it answers in the corner this key opens. A developer sees none of it: there is one corner
  and nothing to filter.
- **The console signs out.** A way out beside whose console it is, which the page had none of:
  a key is the tab's and dies with it, so closing the tab was the only way to stop being signed
  in — no use at all to somebody who wants to come back as somebody else. It forgets every world's
  key rather than the one on screen, because the toggle mints the second from the first.

### Changed
- **`pinecall keys revoke` takes the fingerprint `keys list` prints.** The listing shows the first
  twelve characters, because a full sha256 is unreadable in a column, and the door matches the
  whole hash — so revoking the word on the screen answered `404 no live key of this org has the
  fingerprint …` for every key there was. `revoke` resolves what you typed against the org's own
  rows first: the whole hash still works, a word that names two keys is refused with both, and one
  that names none says which verb lists them.
- **The nightly bootstraps the way a person does.** It ran on `PINECALL_DEV_KEY: dev` and
  `PINECALL_URL` — one key that needed no `api_keys` row, and a variable the CLI no longer reads —
  so it would have failed every night from now on, and for a reason that had nothing to do with
  the goldens. It now does the three steps the walkthrough does: `migrate up`, the gateway, then
  `keys issue` piped straight into `pinecall login --key-stdin`, with `PINECALL_HOME` saying where
  that profile goes. The key never becomes a variable, a file of its own, or a line in the log.
- **La agenda de `clinica-norte` lee la hora en la zona del centro.** `new Date(startsAt).getHours()`
  da la hora de la MÁQUINA: en un runner en UTC el hueco de las trece era el de las once, así que
  la regla que lo rechaza se aplicaba a otro hueco y el que dos pruebas buscaban no existía. Verde
  en un portátil en +02:00 y rojo en CI, que es la peor forma de fallar. `hourOf(startsAt)` lo lee
  del texto, que lleva la zona escrita.
- **Nothing tells you to type `pinecall ui` any more.** The verb was deleted when the console
  became the gateway's page, and eleven places went on naming it: the supervise desk's own line,
  `pipeline --help`, the sentence a simulation prints when it ends, and the console's Evals page,
  in a `<code>` a person reads on screen. A test pins the prose now, the way one already pinned
  the group list.
- **`pinecall --help` names every verb there is, and only those.** It advertised `ui` for four
  days after that verb was deleted — typing it answered `no such group: ui` while the help said it
  was there — and it never grew a row for `line`, built and documented all along. The table is
  hand-written and had drifted both ways; a test now pins it against `builtNames()`. `chat --env`
  is in `docs/the-cli.md` too, which it was not.
- **`pinecall config rm <name>`.** A profile is a key in a file and there was no way to take one
  out: a gateway that had moved and a key that had been revoked both stayed on the list for good.
  It forgets the row and takes the active mark with it rather than leaving it pointing at nothing.
- **`~/.pinecall/dev` is gone, with the runtime's dev key.** A local gateway used to write that
  file at every start and this CLI folded it in as a profile nobody had kept — the one source that
  beat both `pinecall login` and an exported key, so a verb could land somewhere nobody chose. A
  local gateway runs the same Postgres and the same issued keys a box does now, so it is
  `pinecall login http://localhost:8080` like any other gateway.
- **`--env` asserts which world you are in, and never selects one.** A key opens one world, so a
  flag that CHOSE would be a flag that lies; `pinecall run --env production` says which world you
  believe the key in hand opens, and the verb stops when it opens the other. Nothing said means
  the sandbox — a deployment types it out loud, which is the deliberate act it should be. The run
  asks the gateway BEFORE the socket rather than reporting where it landed after.
- **The world things are written in is the `sandbox`, not `development`.** One word was naming a
  world and naming "mine" at the same time, and `env: development` did not say whether it was a
  laptop or a box.
- **`pinecall chat [agent]` takes a slug, and `--file` takes the file.** Named an agent, chat
  mounts nothing and is only the caller's side: a written call at whatever is already holding that
  slug — your own `run` in the other terminal, or a colleague's. `--agent` used to mean a slug in
  three verbs and a FILE in six, which is a flag with two meanings and no way to tell which one
  you got: it is a slug everywhere now, and `test`, `simulate`, `remember`, `personas`,
  `knowledge` and `memory` take `--file`. A path typed where a slug goes is told so.
- **A free slot in `clinica-norte` has an id, a real date and a specialty.** Reserving used to
  mean repeating a phrase back — a slot was `{ when: "martes a las diez", doctor: "…" }` and
  `book` took the sentence — so choosing was comparing text, and text comparison failed both ways
  it can: two slots at the same hour with different professionals were indistinguishable (a caller
  picked five o'clock with one physiotherapist and was booked with a different doctor), and a
  recogniser that mishears the hour left nothing to identify a slot by at all. `book` and
  `propose` now take the id the agenda gave, and nothing else. `startsAt` carries the date and the
  zone, because "martes a las diez" does not say which Tuesday. And `freeSlots` asks what the
  appointment is FOR: the agenda held three names and no specialties while the knowledge base
  described nine professionals with theirs, so the model was left to join the two itself.
- **Talk is two columns.** The door and the words on the left, the call's own log on the right,
  instead of the log stacked underneath: a person talking to an agent and the log of that same
  call were never both on screen without scrolling. Stacks again under a laptop's width.

### Added
- **The console accepts an invitation.** `/invitations/<token>` is a card where the person the
  link names chooses their password and takes their first key; until now the Team screen showed
  the raw token and told them to `POST` it with curl. Team hands out the link instead, and so does
  the operator's `orgs invite`. The card knows the token and nothing about the person — the token
  is the right, and a card that said whose it was would tell a stranger who found the link.
- **An admin page for the operator, at `/admin`.** A second browser program beside the console,
  with its own bundle, its own router and its own credential: the box's ops key, typed in and
  proved at `GET /v1/ops/whoami` before it is kept, under a storage name of its own. Four screens
  — Orgs (every tenant, and one of them whole: its quotas against what it is holding, its keys,
  its people read-only, the vendors it brought), Routes, Fleet with its cordons, and Usage folded
  off the log. Nothing about a plan is on it: what an org is charged is not the runtime's to know.
  Two programs and not two sections of one, because the ops key belongs to no org and must never
  reach a tab holding a tenant's — the import table lets neither page name the other.
- **`src/cli/ui/shared/`.** What both pages wear, defined once: the fetch to the gateway and its
  one error shape, the credentials context, the theme, the frame (the shell, the brand, the
  crumbs, the rail, the empty state) and the style vocabulary. The console was where all of it
  lived; it now imports it, and its own stylesheet holds only what is the console's — the agent it
  is looking at, and the two worlds.
- **`docs/worlds-and-teams.md`.** The model as a developer walks it, on one page: the two worlds
  and what is yours against what is the org's, the path from the sign-up to the deploy, the roles
  and the seats, two developers on one agent, and the four traps. Linked from the README, the
  tutorial and the CLI page.
- **`pinecall whoami` and `login` say the world.** `org clinica · key k_1 · sandbox · laptop`:
  where you are is the key you hold, so the verb that says which key you hold says which world.
- **`pinecall keys`, and a Keys screen.** `issue | list | revoke` the API keys this org's machines
  run on, and the same three in the console. A key issued there is a machine's: it holds `app` in
  production unless `--scope` says otherwise, names nobody, and is printed once. It is the last
  step before a deploy, because a key a person holds by being logged in no longer holds an agent
  in production — the process on the box does.
- **Numbers, the whole screen.** The org's carrier brought from the console — a Twilio account,
  verified once, or a SIP peer with its own networks — shown by kind and account and never a
  secret, replaced or forgotten; a number imported from what that account owns, picked from a
  list, or bought on the box's account by country and area code; every write preceded by the
  gateway's own plan (`?dry_run=true`) drawn step by step and confirmed by a second click; a
  bought number marked; one let go from its row. Before this the screen only listed.
- **`pinecall signup`.** The one verb that needs no key: it makes an org (at
  `https://box.pinecall.io` unless another gateway is named) with you as its admin — allowed
  whatever that gateway's people decided for a new one. The sign-up answers a production key; a
  terminal is a laptop, so it asks `/v1/login/env` for the same person's DEVELOPMENT key and keeps
  that one in `~/.pinecall/credentials` exactly as `login` keeps one — `pinecall run` and
  `pinecall chat` work straight after, and the console link it prints signs the browser in to
  production, where the org's numbers, people and usage are. A gateway that mints no second world
  is said out loud and the production key is kept. The password is typed in silence or read from
  stdin, never a flag. It prints a console link that signs a browser in once. Both it and `login`
  now say out loud when an exported `PINECALL_API_KEY` would shadow the key they just kept, and
  `signup` asks `GET /.well-known/pinecall` first so a gateway that opens no sign-up is named
  before anybody types a password, not after.
- **The console signs a person in and never makes an org.** Making one is `pinecall signup` or
  `POST /v1/signup`; the console's login card asks for an org, an email and a password, and points
  at the verb for anybody without one. The page ships inside the runtime every self-hoster serves,
  so a registration form in it would be one flag away from open registration on somebody else's
  box. A test reads the console's sources, comments stripped, and fails if any file knocks at the
  sign-up door.
- **The console's org layer.** Before anybody picks an agent: Live (every call up across the org,
  repainted as `GET /v1/events` says the floor changed), Sessions across every agent, Numbers,
  Team (invite, change, the invitation token shown once), Usage. An agent selector in the header,
  a Production / Sandbox toggle that holds one key per world and mints the other for the same
  person, and a rail that draws only what the key's scopes open.

### Added
- **`pinecall line`: whose terminal the sandbox number rings in.** An org shares one
  sandbox number, so with three developers on one agent it used to ring wherever somebody had
  restarted last — you would dial it to test your change and be answered in a colleague's
  scrollback. The first `pinecall run` to hold an agent takes its line and a second developer
  claims it on purpose; `claim` and `release` are the two moves, and `run` prints the line under
  the console's URL for any agent that answers at a number. With one developer nothing changes and
  the word never appears.

### Changed
- **`pinecall login` signs you in through a browser.** It asked for an API key, and a person has
  none — the console mints theirs into the tab and never shows it, so there was nowhere to copy
  one from. It now prints a link and opens it: you sign in on the page, where a password belongs,
  and the page hands this terminal a key of its **own** — minted for you, labelled as this
  machine, revoked on its own from Keys. No password ever reaches a shell, and the day an org
  signs in with Google this verb does not change. **With no URL it is `https://box.pinecall.io`
  and it says so** before anything is kept. `--key-stdin` is still the machine's way in.
- **The console has a `/cli` screen**: the card a person opens from their own terminal, naming
  the machine that asked and approving it once.

### Removed
- **`pinecall ui`.** The gateway serves the console now; nothing in this CLI opens a port.

### Added
- **`pinecall run` prints the console's URL** — `https://<gateway>/a/<agent>?login=<code>` — with
  a one-use code that signs the browser in for a key of its own. A gateway that refuses the code
  is one line, and the app runs on.

### Changed
- **`knowledge push` and a contact's memory are your key's world's.** A push with the sandbox
  key a login keeps replaces the sandbox base and never the one the telephone answers from;
  promoting is the same push with the machine's key. A test call's facts stay in the sandbox.
  Nothing in the verbs changed — the gateway reads the world off the key it always sent.
- **Two developers of one tenant no longer take each other's agent.** The gateway holds a
  sandbox agent per person, so `pinecall run` on your laptop and your colleague's are two
  agents: each `pinecall chat`, each suite and each console reaches its own. Nothing in this CLI
  changed for it — what says whose corner you are in is the key, and `pinecall signup` and
  `pinecall login` already keep one per person. The org's sandbox *number* stays one door,
  answered by whichever run started last.
- **`pinecall keys` is now `pinecall providers`.** The verb for the vendor keys an org brought
  takes the name of the scope that opens it (`providers`), and `keys` means the org's own API
  keys, here and at the gateway. The console screen follows: `/providers` is the vendor accounts,
  `/keys` the API keys.
- **The console wears the design canvas.** IBM Plex Sans and Mono, the pink accent on four
  near-blacks (and the paper theme under it), panels with hairlines, the header strip with the mark
  and the breadcrumb, a 204px rail with the accent bar on the screen you are on. Every screen
  redrawn on the canvas's own measures: Calls edge to edge with the list, the head strip, the desk
  and the seq · kind · text timeline; Talk as one centred column with the round door; Chat as
  bubbles off the call's log; Sessions, Evals, Pipeline, Knowledge, Memory, Keys and the org's
  screens in the same panels and tables. Nothing a screen states changed — only how it is drawn.
### Changed
- **The console is served by the gateway at `/`** and holds a person's scoped key, never the
  org's: spent from `?login=`, or asked for as org, email and password, and kept in
  `sessionStorage` for the tab's life. The log stream and the recording carry the key on a header,
  so nothing rides a URL. The header shows who is signed in and which world the key opens.
- **`pinecall run` answers the console for its directory.** A written call to the class, the
  personas and a simulation, the goldens and a suite, the knowledge folder and its golden, the
  memory goldens, a promoted candidate, drift and the reproductions are asked of the gateway,
  which relays them to the `pinecall run` holding the agent (`dev.request` → `dev.answer`). The
  console's screens no longer call `pinecall ui`'s own `/ui/*` server for any of it; the sentence
  for another directory's agent now says `pinecall run`. `Agent.onDev` and `DevRefused` join the
  client's surface.

### Added
- **A chat can open part-way through.** The Chat screen offers the states this directory's goldens
  declare, which is `pinecall chat --state` by name; a conversation that opens in one gets a mount
  of its own, because the opening is applied where the class is held.
- **A broken run's reproductions, in the console.** Evals → a run → the goldens that did not hold,
  each opened whole: the golden as written, every verdict on it, and the requests the model
  actually answered. The log keeps only a hash of each prompt block on purpose, so that file is
  the one place the text is, and `ui/reproductions` is how a page reaches a file on this disk.
- **A model matrix from the console.** The suite form takes models, comma by comma, the way
  `pinecall test --model` is repeated — and a call read on the Sessions screen carries the same
  two buttons the Evals screen has: re-check by code, and promote.
- **The console does what the terminal does.** Five screens landed at once, and every one of them
  runs the very code its verb runs: **Knowledge** (the folder pushed from this directory, the
  bases listed and dropped, the golden asked), **Memory** (one contact read and forgotten, the
  recall golden, the extraction goldens), **Keys** (the provider accounts this org brought),
  **Evals → drift** (each judge's held-rate over two windows) and, on any judged call, **re-check
  by code** (ring 3) and **promote to a golden candidate**. The header says whose gateway this is.
  The console's own doors are a table now (`ui/doors.ts`): a screen that needs something only the
  terminal in the agent's directory can do is one module and one row, and the server that serves
  them knows nothing but their paths.
- **`pinecall simulate --listen` works.** The call comes out of this machine's speakers while it
  happens: the same hidden `observe` seat the console's listen button takes, joined from Node with
  `@livekit/rtc-node` (an optional dependency) in a process of its own, both tracks through
  livekit's own `AudioMixer`, written to whichever of `ffplay`, `play`, `aplay` or `pw-play` is on
  the PATH. The seat is
  knocked for until the room opens, so the ear lands on the greeting. `--listen` turns `--voice`
  on, out loud: a written call has no audio in it.
- **Chat from the console.** A screen of its own: the class of the directory `pinecall ui` runs in,
  mounted once in that process as `pinecall chat` mounts it, one socket per conversation, the tools
  running in that terminal. `--as` is the `as` field of the form. Three doors of the console's own:
  `ui/chat`, `POST ui/chat/say`, `POST ui/chat/end`.
- **`pinecall pipeline`.** What the agent hears, decides and speaks with as the next call would be
  built, the class's opening, the medians livekit measured, and which of the five knobs is turned.
  `set` and `clear` turn the same knobs the console's Pipeline screen turns, over the same door —
  and `set` sends the whole set, so turning one knob never gives another back to the class.
- **Run the goldens from the console.** Evals → Run a suite: every golden of this directory as a
  checkbox, with the caller's first line and what it expects; voice and a noisy line beside; the
  run appears in the table as the gateway opens it. `ui/goldens` and `POST ui/test` are the
  console's own doors, and the suite they run is the one `pinecall test` runs — its orchestration
  moved to `testing/suite.ts` so it is written once.
- **Simulate from the console.** Calls → Simulate: a persona from this directory's
  `test/personas`, written or spoken, judged or not, the line spoiled or clean — and the page goes
  to the call as it opens. Spoken, the listen button beside it is the speakers `simulate --listen`
  always refused to be. The `ui` process runs the same `aSimulation` the terminal verb runs and
  prints the turns; the page reads the log. Two doors of the console's own, `ui/personas` and
  `POST ui/simulate`, never the gateway's.
- **`Call.run`** — the eval run that opened this call, or null for a person, read off the same
  first entry the line is read from. `pinecall test` seeds a golden's state into the call that
  carries a run, and into no other; the `eval_` caller prefix it used to look for is gone.
- **`pinecall test --voice` in the docs**: ring 2 over the same goldens, and where a broken golden
  is written out (`.pinecall/evals/<run>/<golden>.json`) with the requests its model answered.
- **`greeting`: how a class opens a call**, without an `onCall` hook to do it.
  `greeting = "Clínica Norte, buenos días."` is the words, read out as written;
  `greeting = { reply: "saluda y preséntate" }` hands the model an instruction the caller never
  hears and lets it find its own opening. Exactly one of the two, refused at load when it is
  neither or both. `allowInterruptions: false` is the legal notice nobody talks over.
  Clínica Norte opens with words, Tienda Sur improvises — one of each, in the examples.
- **`pinecall sessions [call]`** — the calls this gateway has run, and what one of them came to.
  With nothing after it, one row per call newest first: when it came in, how long it lasted, why it
  ended, what it cost and the line the agent left as its outcome. With a call id, that call's
  **score**: the verdict, how many questions the judging put to a model and what they cost, then one
  line per judge with the question it answered — and, for a judge that did not hold, its own
  reasoning. `--agent`, `--limit`, `--json`. It reads ring 4's judging back; it runs nothing.

### Fixed
- **Clínica Norte's CRM is per call**, hung off the instance like its agenda, instead of one
  module-level map every call in the process wrote into. A `TODO` naming a bridge function that
  never existed is gone. `docs/the-cli.md` no longer lists `sessions` and `supervise` as unwritten.
  `testing-an-agent.md` is split: memory's and the index's goldens have their own page.
- **A reproduction says why there is no prompt, and only then.** `Cell.asked` is a list, or
  `null` when the runtime kept no requests; the file writes the sentence for `null` and an empty
  list for an empty list, where it used to read `[]` as "not recorded".
- **Clínica Norte's knowledge file stops giving procedure.** Three sentences that told the agent what
  to ask before checking the agenda contradicted `freeSlots`'s own description, which had to shout
  them down; the facts stay, the procedure lives in the tools.
- **`pinecall ui` served a blank page from a checkout, and had for as long as it has existed.** Two
  faults, one evening. The console's directory arrives as a URL's path and so ends in a separator,
  and the server guarded its own root with `files + sep` — which reads `…/console//`, which no file
  under it starts with, so every request fell through to the page and the browser parsed a megabyte
  of JavaScript as HTML. And beside the module sits `console/` twice: the built one in the package
  and the SOURCE in a checkout, whose `index.html` points at `main.tsx`, which no browser runs. The
  existence check could not tell them apart. Both are pinned by tests that fail without the fix.

### Added
- **`pinecall supervise <call>`** — a human at the desk, from this terminal. The call's transcript
  as it lands, and one line per move: `w <text>` whispers to the agent, `s <text>` puts a sentence
  in its mouth verbatim, `t` takes the line, `x` gives it back, `e [reason]` ends the call, `q`
  leaves and the call goes on. Every move lands in the caller's own log as its own `supervisor.*`
  entry with a seq, so what a human did is read the way what the agent did is read. The audio is
  `pinecall ui`, which has a room; a terminal has no speakers this process may reach.
- **`hangup = { when: "..." }`** on a class: the model may end the call itself, and you say in your
  own words when. The tool is livekit's own `end_call`, hidden while the agent is greeting, and the
  call's log gets `call.ended` with `agent_hung_up` rather than the drain its close reason would
  otherwise have looked like. A class that declares nothing cannot hang up: only the caller and a
  supervisor end a call. Clínica Norte declares one.

### Removed
- Clínica Norte's `transfer()` tool, which returned a sentence and did nothing. A tool the model can
  call that changes nothing is a trap, and this one was the tool a model reached for on the first
  real call of this project. What replaces it is real: the agent can now end the call.

### Changed
- An extraction golden is the schema's shape, not this package's: `ExtractionGolden`,
  `ExtractionExpected`, `ExtractionBroke`, `ExtractionJudged`, `ExtractionCases` and
  `ExtractionRun` come from the wire's shared schema and are generated, so a case written in
  TypeScript, in Python or in Ruby is one contract and not three that drift. The file format
  is unchanged — a transcript stays a list of `[who, what]` pairs, which the schema now says
  in its own words.

### Added
- `pinecall memory eval [golden.json] [--k n]`: a memory golden, the read side of the table. A
  list of `{holds, asks, expects}` — what memory holds about a question's contact, what the caller
  said, and the fact or facts that should come back — asked of `recall` and answered as `recall@k`
  and `nDCG@10`, computed by code with no model in the loop. No contact of the org is read or
  written: each question's facts go to a scratch contact and are deleted again, which is what makes
  the figures the real ranking. A fact answers when what came back CONTAINS what was expected,
  folded for case, accents and whitespace, because a fact is a sentence a model wrote. Every
  question memory did not answer whole is printed with what came back instead, and the verb exits 1
  when anything did. `memory/golden.json` beside the agent file by default; Clínica Norte ships one
  of seven questions, eight or nine facts each.
- **`pinecall remember [paths]`** — the goldens `memory.remember` is held to, which is the write
  side and the half that persists. A case is one call already held (both speakers, in `said`), the
  facts memory already holds (`holds`), and what must come of the hang-up's one model call: which
  categories got a fact (`writes`), which never did (`never`), which values must not survive in any
  fact's text (`never_says`), and which held facts the call contradicted (`invalidates`) — its
  mirror included, so a model that supersedes whatever it touches is caught too. A case may
  `plants` sentences somebody tried to get into memory, and planting one IS the assertion that
  admission refuses it. Nothing asks a model whether two sentences mean the same thing: a category
  is your own word, a value is a literal, a supersession is an id. One model call per case, run in
  the gateway on the org's own keys against the class this terminal is holding; exits 1 when a case
  did not hold. `test/memory` beside the agent file by default; Clínica Norte ships three.
- A ring-1 golden may open its call already knowing things: `"memory": [...]` seeds the facts the
  `recall` tool answers for that call alone. It is how you test the one thing memory exists for —
  that the agent uses what it remembered — without a contact in a database and without leaving a
  fact behind. Clínica Norte ships one.
- `pinecall knowledge eval [golden.json] [--base <name>] [--k <n>]`: every question of a golden
  asked of the base, and `recall@k` and `nDCG@10` printed — computed by code with no model, so two
  runs answer the same numbers. Prints every question it missed with what came back instead and
  exits 1 when anything did, so a base can be held to its golden in CI. Clínica Norte ships one.
- **`@render(ThePrompt)` on the class, the other spelling of `render()`.** A prompt that has grown
  gets a function beside the class, and the props ARE the instance —
  `Prompt<T> = (agent: T) => Child`, so `({ stage, customer }: Support) => …` stays typed with no
  wrapper. It is exactly `render() { return ThePrompt(this); }` and produces the same block, byte
  for byte. A class that declares both spellings is refused when it is defined: `TiendaSur declares
  both @render(TiendaPrompt) and a render() method; two ways to answer one question — keep one`.
  Tienda Sur is written this way; Clínica Norte keeps the method.
- **`@state` in three spellings**: bare `@state`, `@state({ pii: true })` (sugar for
  `visibility: "pii"`), and `@state({ visibility })`. `pii: true` beside a `visibility` that says
  something else is refused by name.
- **Decorating one field decides them all.** A class that decorates no field has every own field as
  state, as before; a class that decorates any means *these, and nothing else*, so an undecorated
  field on it is the tenant's scratch space — out of the snapshot, out of the prompt, out of
  `state.changed`, and writable with no tool running. It is the first way to keep a helper field
  out of the log.
- **The view is a method of the class.** `render(): Child` on `Agent`, returning JSX, with `this`
  as the state — no view file, no props, no block a class declares of its own. A class with no
  `render()` sends an empty view. The file a tenant writes is `agent.tsx` for that reason; the CLI
  loads either name, and every default path, usage line and doc says `agent.tsx`.
- `Agent#remembers(text)`: whether memory has already told THIS call something under that word —
  the word a fact was filed under, or the fact itself. The bridge folds the call's own `memory.ops`
  entries into it (`runtime/recall.ts`) and re-renders, so a branch that asks about the caller
  follows what the runtime actually found. It replaces the old `memory.has()` of the view props.
- What the class knows, reads and remembers travels in the declaration: `knowledge` is read beside
  `agent.tsx` and sent whole as `{ path, text }` (a missing file is refused at load, with the path);
  `docs` names the base it was pushed under — `docs = "clinica-norte"` or
  `{ base, mode?, k?, minScore? }`, typed as `DocsDeclaration` — and the old glob form is refused
  with the verb that replaces it; `memory = { remember, forget }` is `MemoryDeclaration`.
- `pinecall keys add <vendor>` · `rm <vendor>` · `list`: the org brings its own provider key for
  a vendor without an operator, on its own API key. The key is read from stdin and never from the
  command line, it is echoed and printed nowhere, and `list` answers vendor names alone — no door
  of the runtime ever gives a provider key back. `keys` leaves the planned table.
- `pinecall knowledge push [dir] --base <name>` · `list` · `drop <base>`, and
  `pinecall memory <contact>` · `memory forget <contact>`: the folder of `*.md` to the gateway
  under a name, and one contact's facts read or erased. Both leave the planned table.
- `pinecall chat --as <contact>`: the written caller says who it is, and the socket carries it as
  `?contact=`, so an agent that declares `memory` can be made to remember somebody from a terminal.
- The console: a `memory.ops` and a `docs.sources` each read as one row of the live timeline, and
  Sessions prints a lookup as `n sources · ms` with what was found one click under the turn.

### Changed
- **Nothing the framework writes is a hole for somebody else to fill.** The view is one block, all
  of it the tenant's words: what memory recalled and what the knowledge base returned reach the
  model as `tool_result` blocks, JSON-encoded, where content from outside the conversation belongs
  (`runtime/docs/security/prompt-injection.md`). `pinecall prompt` and `pinecall run --show-prompt`
  print the three regions with no marker line anywhere.
- The `knowledge` block is the runtime's to write, from the `{ path, text }` the declaration already
  carries: the app sends nothing for it, because the same file twice is a worse bug than an empty
  block.
- Both examples are one `agent.tsx` with a `render()` and no `views/` directory, and they say how
  their chunks come back on the declaration — `docs = { base, k: 4, minScore: 0.5 }` — instead of
  inside the prompt. Their ring-0 suites and their captured prompts were retaken.
- `promptOf(agent)`, `showPrompt(agent)` and `mount(Class, { pc, … })` no longer take a `views`
  argument, and `load()` no longer resolves a view file. `describe(ctor, source, file)` takes the
  file name, because the parser reads the dialect off the extension.
- `render(agent)` is now `promptOf(agent)`: `render` is the decorator a class wears, and one name
  cannot be two things. `layout()` is no longer exported — `promptOf` is that function under the
  name a tenant reads it by.
- The class docstring survives a class decorator: the parser puts a decorated statement's start
  after the decorator, so a docstring read up to there found `@render(…)` in the way and gave up.
  It is read up to the first decorator now.
- `withAuthor`, `withAuthorAsync`, `currentAuthor` and `UnauthoredWrite` moved to
  `agent/authors.ts`. Who is writing the state is one idea, and `agent.ts` was at the 400-line
  ceiling the tree test holds.

- The framework, from zero: the `Agent` base whose fields are the state and whose every assignment
  is a change with an author; `@tool` with `when` / `stage` / `confirm` / `preview` / `pii` /
  `timeout`; docstrings read out of the class's own source; `@state({ visibility })`;
  `static events`; the four lifecycle hooks; `collapse`, `restore`, `startIn`, `last(contact)`.
- The views: JSX that renders to text, and the prompt as named blocks in two regions in one order —
  `identity`, `knowledge`, `tools`, then the view, which is the whole dynamic region.
- The live call as a value: the room reduced from its own entries, the turns, and the six verbs —
  `say`, `reply`, `send`, `mute`/`remove`, `invite` — each one command on the wire.
- `pinecall/client`: one socket, the agents on it, the tool calls it answers, and any log the key
  can read, folded by the protocol's own reducer. Plus `pinecall/client/testing`, a gateway and a
  log that are not there, so an app's own suite needs neither a network nor a key.
- The bridge: `mount()` — one live instance per call, the opening state seam, and a sync that
  sends only the block whose text actually changed.
- The CLI: `run`, `chat`, `ui`, `prompt`, `test`, `simulate`, `eval`, `runs`, `personas`, `login`,
  `whoami` — and `groups.ts`, which declares every verb the design names and this tree has not
  written, so a person is told what a verb *will* be instead of "unknown command".
- One resolution order for the gateway and the key (`cli/env.ts`), `~/.pinecall` at 0600, and a
  gateway on a dev key that ignores an exported `PINECALL_API_KEY` out loud.
- The console `pinecall ui` serves on 127.0.0.1 under a nonce: Talk, Calls (live), Sessions,
  Pipeline and Evals. The org key never reaches the browser.
- Two examples written the way a customer writes one — `clinica-norte`, `tienda-sur` — with their
  goldens, personas and prompt-blocks tests; CI (`scripts/check`) and a nightly that drives both
  on two models and watches each judge's drift.
- `ARCHITECTURE.md`, `docs/` (writing an agent, the prompt, testing, the CLI), and
  `.claude/skills/`.

### Changed
- The prompt is a list of named blocks in two regions instead of two strings: `identity`,
  `knowledge` and `tools` (static, cached), the history, then `view` (dynamic). `render(agent)`
  returns `Blocks` — `{ blocks, history }`, every block `{ name, region, text }` in send order —
  and `showPrompt()` rules its page `── identity (static) ──` … `── history ──` …
  `── view (dynamic) ──`. `call.setPrompt(name, text)` names a block.
- The console's Live screen gained a `PROMPT` panel and the Sessions screen a section listing
  every block by name with its hash, length and seq, read from `state.prompt` by name.
- The licence is spelled out where a user of the package meets it: the Apache-2.0 copyright line
  is filled (`Pinecall`), `README.md` has a License section, `package.json` carries the author and
  the repository, and `CONTRIBUTING.md` says there is no CLA. npm ships `LICENSE` in the tarball.
- Comments naming a page of the runtime's engineering notebook now say **the runtime's**
  `docs/decisions/<page>.md`: read from this repository, the bare path pointed at a file that is
  not here.
- `pinecall simulate --judge` names `pinecall-runtime sessions show <id>` (and the console) when a
  call never seals. It used to name `pinecall sessions show`, a verb this CLI declares and has not
  written, so the sentence sent a person to a stub.

### Removed
- `<Prompt>`, the tag that rendered its children as paragraphs: `<>` already does exactly that,
  and no example ever wrote one. The name is the type `Prompt<T>` now.
- The whole marker apparatus: `<Memory>`, `<Retrieved>`, `<Knowledge>`, `marker()`, `Fills`,
  `fills()`, `withFills()` and the `AsyncLocalStorage` that carried them; `ViewProps`, `View`,
  `Views`, `propsFor`, `viewFor`, `checkViews`, `layoutOf`, `declaredBlocksOf`, `PromptDeclaration`
  and `static prompt`. A view file, a prompt block a class declared for itself and a hole a
  gateway filled are all gone, with their tests. `PROMPT_BLOCKS` is the layout, and it is the
  framework's.
- `Regions`, `staticRegion`, `historyRegion` and `dynamicRegion`: the blocks above are what they
  were. `setPrompt(region, …)` went with the wire's `region`.
- `@pinecall/web`, the browser package: nobody installed it and it read a projection nobody read.
