# Changelog

All notable changes to `pinecall`, the CLI. Up to 0.9 it shipped inside the framework's package;
that history is [`@pinecall/agents`'s CHANGELOG](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/CHANGELOG.md).
The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

- **`voices list` says each voice's language**: a vendor the providers row lists by language showed
  every voice once per language with nothing telling the rows apart (Google's, eight times each).

## [0.11.24] — released with the dot's marked walk (2026-10-25)

## [0.11.23] — released with the dot's smaller face (2026-10-25)

## [0.11.22] — released with the dot's fix for phones (2026-10-25)

## [0.11.21] — `pinecall walks`, and start watches each agent's own folder (2026-10-25)

- **`pinecall walks`**: a tutor agent's walks, recorded in its voice for a visitor to play with no
  call, listed with their sentences, length and voice; `walks play <walk>` plays one here. `start`
  prints each walk as the agent records it.
- **`start` watches each agent's folder and the project's `lib/`, not the project's root**: a script, a note
  or a pulled settings file anywhere in the project reloaded every agent and cut a `test` run in flight.
  The MCP server's held agent watches the same. (2026-10-24 tools eval, T F6 · R F20 · P F1)
- **A class the gateway refuses at its declaration is not answering**: `start` waits for `agent.configured`,
  so a refused class prints no `connected` line nor a link to talk to it, and a reload to one keeps the
  version before answering instead of ending `start` with every live call. (T F7 · R F3 · R F18)
- **`start` and `prompt` end with the agent's process's exit code** — 2 for the gateway's refusal of a
  class, as for any refusal — instead of 1. (R F3)
- **The MCP server asks again which process holds an attached agent** before each tool: a terminal's
  `pinecall start` reloads under a new app, and every tool after a save was refused with a bare 404. (P F2)
- **`chat` fed from a pipe says one line at a time**, each once the agent answered the one before, as a
  person types: every line reached the model at once, while a tool of the line before still ran. (T F4 · R F4)
- **`numbers import --move` sends the move**, the dry run included: it never reached the gateway, which
  answered "so say move" whatever was typed. (T F10)
- **The MCP `simulate` refuses audio parameters without `voice`**, as the CLI and the MCP `test` do; it ran
  a written simulation and counted it. (T F14)
- **`personas` lists past a file that is no persona** and names it; one bad file made every listing verb
  exit 2. `push` still refuses it. (R F21)
- **`docs eval <golden> --base <base>` asks at the agent's k** in its project, as with nothing named; it
  asked at the gateway's default, 8. (R F22)
- **`lexicon add|hear|rm --team` shows the team's corner it wrote**, not "your corner". (T F8)
- **`runs promote` names a judge that broke the call and no golden field asks again** (`expected-outcome`)
  instead of "nothing broke". (T F11)
- `the-cli.md`: `whoami`'s exit code is 2 for a refusal, as the table says; `start --ui`'s row says where a
  prompt's text is read; a class may declare its voice and models (it is no longer "refused at load"). (T F9 · P F14 · R F2)

## [0.11.20] — a search's sources in `sessions log`

- **`sessions log` shows where a search's chunks came from**: base, path, heading and score, one after the
  other. The line was the raw JSON cut at 160 characters, inside the first excerpt, so no heading was ever
  visible. (found by the 2026-10-23 eval, D D-6)

## [0.11.19] — start reloads on save, a caller that interrupts, the MCP's waits

- **Bare `pinecall` prints the verbs by what they are for, on one screen, and exits 0**; `pinecall --help`
  is the whole map. It printed 109 lines and exited 2. (found by the 2026-10-23 eval, A F2)
- **A pipe whose reader closed ends the verb quietly**: `pinecall chat --events | head -1` died with an
  `EPIPE` stack. (found by the 2026-10-23 eval, A F10)
- **A `.ts` persona file loads again**, through tsx's own import, and a `.json` one holding `{ goal, style,
  facts?, state? }` is a persona too; a file that is neither is refused naming the shape. `personas push` and
  the plain `personas` failed with `Cannot find module …?v=`. (found by the 2026-10-23 eval, F F2)
- **`pinecall start` prints the kill**: the `error` the gateway sends an app — `<agent> was killed by
  <name>` — is a line of the screen. (found by the 2026-10-23 eval, J F3)
- **`data policy` says the +1 floor whenever the org's setting is wider than it**, not only when it is
  unset. (found by the 2026-10-23 eval, J F4)
- **`deploy` refuses a link or a device in the folder** with the gateway's sentence, instead of skipping
  it in silence. (found by the 2026-10-23 eval, I F1)
- **`numbers import --move`** takes a number off the trunk it is on now, as the `409` asks. (found by the
  2026-10-23 eval, K F8)
- **`agent diff --team`** reads the team's corner against production's. (found by the 2026-10-23 eval, J F6)
- **`sessions log` narrowed to a page that kept nothing says the log goes on**, before the `more:` line.
  (found by the 2026-10-23 eval, A F11)
- **`runtime recommend` on an old `pinecall-runtime` names the version it needs** (0.11.3) and the
  upgrade, instead of argparse's own refusal. (found by the 2026-10-23 eval, L B3)
- **`generate --help` links the page that exists** (`concepts/expectations`). (found by the 2026-10-23 eval,
  A F7)
- **The MCP's `test run` and `simulate run` answer the run's id even at `wait_s: 0`**: the timer starts once
  the run has begun. (found by the 2026-10-23 eval, L D3)
- **The MCP's `numbers import` takes `move`**, as the `409` asks; `agent set` refuses a field nobody set
  by name and says the value each field takes; `background_noise` is validated (dB under the caller, 0 to
  60); `project new`'s `path` is said to be the parent; Studio's `headers`, `params` and `collect.fields`
  shapes, a broken save's sentence, and `watch` on an ended call are written as the product does them;
  the pages' account ids are whole and the `voices` example names its vendor. (found by the 2026-10-23
  eval, L B5, L D4, L D6, L D8–L D12, L D14)
- **`pinecall start` reloads the class on save**, as four pages promised and only the MCP host did: the
  agent's folder is watched, a burst of writes is one reload, the next process registers before the one
  before drains, and a save that does not load leaves the version before answering and says why. The host
  and `start` share the one implementation (`dev/reload.ts`); a Ruby or Python agent held by `start` reloads
  too. (found by the 2026-10-23 eval, A F1)

## [0.11.18] — numbers held by another org, a blank lexicon word

- **`numbers available` tells a number another org holds from one routed nowhere**: "held by another org"
  beside "routed here" and "not routed here".
- **`lexicon add` refuses a blank word or a blank way to say it** before asking the gateway, with the verb's
  form.

## [0.11.17] — released with the runtime's wire fixes

- Nothing of the CLI changed: published at 0.11.17 with every other package.

## [0.11.16] — every refusal exits 2, `test --version` plays the version, `limits` shows every limit

- **`pinecall test --version 2` plays the run on that version of the agent's settings.** The CLI's own
  `-v, --version` was a root option, which commander reads anywhere on the line, so it won over the verb's
  `--version <n>`: the CLI printed its version, played nothing and exited 0 — a green gate that tested
  nothing. The root has the flag only when the line gives it to no verb; `pinecall --version` and `-v` are
  unchanged. (found by the 2026-10-23 eval, E B1)
- **BREAKING: every refusal of the gateway is exit 2, in the gateway's own sentence; exit 1 is only what was
  measured and did not hold.** A 400, 401, 403, 404, 409, 422, 429 or 503 — a name nothing answers to, a run
  already going, an input the schema refuses, a quota, a vendor with no key — stopped the command from
  running and measured nothing, yet all but the 404 were exit 1, the code of a golden that broke. A step in CI
  still fails on either; 1 now says the agent is what failed, 2 that the check never ran. `test` tells a second
  run by its id and a golden the schema refuses by its name and field (`golden x, turns: List should have at
  most 40 items …`), where it printed `goldens.0.turns: …`. (found by the 2026-10-23 eval, E D9)
- **`pinecall simulate` exits at once when the gateway refuses the caller's next line, and hangs the call up.**
  The written call's socket stayed open after the 503 or 400, which held the process (and the call, with
  its seat, until the command was killed); it is closed however the run ends, and so is a `--listen` seat.
  (found by the 2026-10-23 eval, F F3)
- **`pinecall simulate --judge` exits 2, with the reason, for a call nobody judged.** No judge on, only
  `n/a` and classifications, the evals used up, or no `call.score` within a minute used to exit 0, a silent
  green in CI; a judge that answered `broken` is still exit 1. (found by the 2026-10-23 eval, F F5)
- **`pinecall test` refuses `--packet-loss`, `--background-noise` and `--ambience` without `--voice`, as
  `simulate` does.** A written run ignored them and ran green. (found by the 2026-10-23 eval, G D5)
- **`pinecall test --voice --grep <golden>` plays the matching golden out loud.** A spoken run with nothing
  said asked the gateway for the approved dataset as well, which a spoken run cannot play, so it was refused
  even when the agent had no case; it plays the golden files alone now, in the CLI and in the MCP's `test`
  tool (`--voice` beside `--dataset` or `--case` is still the gateway's refusal). (found by the 2026-10-23
  eval, G B1)
- **`pinecall simulate` says who plays the caller when it opens the call**, so the gateway refuses a model it
  cannot run before the call exists and keeps the model with the run. (found by the 2026-10-23 eval, F F3
  and F F8)
- **`pinecall limits` prints every limit**: the budget (`$4.25 of $60`), hosted apps, memory facts and
  knowledge chunks beside the rest; the MCP's `usage` answers them too. (found by the 2026-10-23 eval, C B6)
- **`pinecall judging --agent <name>` says what an agent's calls are judged on**: its own `--judge`, its
  class's, or the org's, and whose key it is; `judges add|off|…` says `n judge(s) in the list`, the size of
  the list, which read as a count of the judges on. (found by the 2026-10-23 eval, C D4)
- **`docs push`'s help says what the line counts.** The legend called the chunks what the files "became",
  which read as the base's; it now says files sent, the base's others left as they were, and the chunks of
  the files sent, and `docs list` counts the whole base. The guide for reading a call's searches shows
  `--json` for each chunk's base, path and heading, which the one-line view cuts. (found by the 2026-10-23
  eval, D D-6)
- **The `chat --as`, `data reads`, `studio` and `kill` pages say what the product does**: `--as` is the
  call's contact and where it shows; `reads` is the environment's own and a server's key is recorded; a
  secret is named in a header's value alone and an answer that repeats one shows `***`; a `pinecall start`
  of a Ruby agent is two apps, and which one prints the kill line. (found by the 2026-10-23 eval, J F7,
  J F5, I F3, I F4, J F3)

## [0.11.15] — `pinecall deploy` runs a Python project

- **`pinecall deploy` runs a Python project.** A project whose agents are `agent.py` is uploaded with
  its `pyproject.toml` and Pinecall installs it with uv on CPython 3.13 (`uv.lock` when it has one);
  `.venv` and `__pycache__` never travel. A project with agents in two languages, or a Python one
  with no `pyproject.toml`, is refused before anything is sent. Ruby is still run on your own server.

## [0.11.14] — docs push upserts, docs pull and rm, cases add, test plays files and dataset, alerts

- **The docs folder is a checkout of the base.** `pinecall docs push` writes the folder's files into
  the base by path and keeps the base's other files, so a document added in the console survives
  it; the line says `· N kept`. `--replace` makes the base the folder, as a push did before. A
  `README.md` at the folder's root is never sent. New `docs pull [dir]` brings the base back into
  the folder, one line per file (`written`, `unchanged`, `not in the base (kept)`), and
  `docs rm <path>` takes one file out of it.
- **`pinecall cases add <file…>`: a golden written by hand kept as a case.** Each file's golden, or
  each of a list, is kept approved under its name, `--name`, or the file's basename; `--held-out`
  as `keep` has it. The same name rewrites the case; a name a call made is the gateway's 409. A
  case names only words: a golden that names a state or a tool stays beside the code.
- **`pinecall test` plays the files and the approved dataset together.** With nothing said, the
  goldens under `test/goldens/` and every approved case not held out and not kept in the
  repository both play, and each line of the matrix says `file` or `case`. `--files` plays the
  files alone, as before; `--dataset` and `--case` are unchanged. The MCP's `test` tool does the same.
- **The MCP: `docs` takes `pull`, `cases` takes `add` (the golden as JSON, never a file), and a new
  `alerts` tool lists what the org was told.**
- **`pinecall alerts`: what the org was told.** Every alert of the environment, newest first, kept
  90 days whether or not a webhook is set, and whether it was mailed; `--limit`, `--prod`.

## [0.11.13] — released with every other package

- Nothing of the CLI changed: published at 0.11.13 with every other package.

## [0.11.12] — `carriers drop` says what it does, the templates name their tool

- **`carriers drop` says what it does.** Its help read "its numbers stop ringing here"; the
  gateway keeps them routed until each is let go with `numbers drop`, as the page said.
- **The Python and Ruby templates name their tool.** Their view told the model to call
  `takeMessage`, the TypeScript name; the tool in those two is `take_message`.

## [0.11.11] — a case written by hand reads as one

- **A case written by hand reads as one.** The gateway now keeps cases a person wrote in the console
  (`source: "person"`, no call): `cases show` says `written by <who> (by hand, <env>)` where a
  call's case says `from <call>`, and its `broke` says no call made it, and `cases forget` names no call for it.

## [0.11.10] — `pinecall pipeline melody`: the hold melody from the terminal

- **`pinecall pipeline melody`: the hold melody from the terminal.** What a caller hears while a
  tool runs or the model is slow: `show`, `upload <file>`, `default`, `off`, and `after
  <seconds>`, the seconds of the agent's quiet before it starts (2.5 unless set; `after default`
  gives it back). One choice per agent per environment; `--prod` sets production's.

## [0.11.9] — `docs push --language`, a golden question with several pages, the questions a section answers

- **`pinecall docs push --language <code>`: the language a base speaks.** `en`, `es`, `pt`, `fr`,
  `de`, `it`, `nl` or the configuration's name; left out, the gateway counts it from the files'
  words. The push's line says which (`clinica-norte · 7 files · 41 chunks · spanish · 812 ms`),
  and when the files said none clearly it says how to say one. `docs list` shows each base's.
  The MCP's `docs` tool takes `language` on `push`.

- **A golden question may name several pages.** `expects` in `docs.json` is a heading path or a
  list of them, any one of which answers; a miss names the list.

- **The questions a section answers travel with it.** `<!-- asks … -->` under a heading, one a
  line, indexed beside the section in a caller's own words; every other HTML comment is dropped
  from the base.

## [0.11.8] — a simulation names who plays its caller; how far each judge can be trusted

- **`pinecall simulate --llm --tts --caller-voice`: who plays the caller, for one run.** The model
  and the voice a simulated caller is played on were the persona's alone; a run now names its own
  and the persona keeps its. The MCP's `simulate` takes `llm`, `tts` and `caller_voice`, and its
  `personas` takes `tts` beside `llm` and `voice`, as `pinecall personas add --tts` does.

- **`pinecall judges agreement`: how far each judge can be trusted.** One line per labelled judge —
  labelled, compared, agreed, the rate, and trusted — from `GET /v1/evals/calibration`, which only
  `curl` read until now; `--org` for every agent's calls. The MCP's `judges` tool takes `agreement`.

## [0.11.7] — the agent `new` writes confirms the message; the runtime's keys are called that

- **The agent `new` writes tells the caller their message reached the team.** Its view said the message
  reached the team and never asked the agent to say so; on an open model (gemma4:12b) the agent went
  straight to "anything else?" and its own golden passed 2 times in 5. Now 20/20 in TypeScript, 10/10
  in Python and in Ruby, on the same model.
- **One word for the keys an org did not bring: the runtime's.** `pinecall limits`, `login`'s advice and the
  MCP's `usage` say *lent by the runtime*, where they said the deployment, the host or the platform.

## [0.11.6] — released with every other package

- Nothing of the CLI changed: published at 0.11.6 with every other package.

## [0.11.5] — the voice calls' realtime model set apart from the LLM; pinecall studio; one way in with pinecall login

- **`pinecall studio`: the agents built in the console's Studio, from a terminal and from the MCP.**
  `list`, `new <name>`, `pull <name>` (the definition as `<name>.studio.json`, the release it was
  read at beside it), `push <name>` (the file saved as the next release over that one; refused when
  someone saved meanwhile), `try <name> <tool> key=value…` (one tool's request sent once: status,
  time, body), `deploy <name>` (the sandbox's release into production) and `code <name>` (the agent
  as a TypeScript project: `<name>.zip`, or its files written into `--out`). The MCP's new `studio`
  tool (`list`, `show`, `new`, `save`, `try`, `deploy`) builds one end to end, and `chat` talks to it.

- **A voice call runs on a realtime model while a written call keeps the LLM.** `pinecall agent set
  --realtime xai/grok-voice-3.0 --realtime-option voice=eve` (and the MCP's `agent`, `settings.realtime`
  and `settings.realtime-options`) names the model the agent's voice calls run on alone, one that
  hears and speaks itself; `--llm` keeps answering its written calls. `clear realtime` and
  `clear realtime-options` take them out, and the settings table shows both rows, `class` where the
  class declares `@realtime`. `pinecall providers` prints the realtime models under the table, one
  line per vendor (`realtime · xai: …`), and the MCP's `providers` answers them under `realtime`.

- **The MCP's `runtime` tool shows the stack before running it, and takes every stage.** A new
  action, `recommend`, answers what `pinecall-runtime setup --recommend` reads: the machine, where
  each vendor's key is (never its value), each measured model and whether it fits, and the stack
  that fits — for the assistant to show the person before `up`. `up` takes `stt`, `turn`, `llm`,
  `tts`, `judge` and `caller` as `setup` does, and `email` for the console's admin; its description
  no longer says the default is "local": it is the stack that fits the machine. No password passes
  through the assistant: `setup --yes` makes none up, and the manual says what sets one.
- **A project that names a runtime on this machine, where there is none, is told so.** Its
  `pinecall.json` says `http://127.0.0.1:8080` (it was made beside a runtime of its author's); the
  refusal said to sign in there, which nobody can. It now says `pinecall-runtime setup` runs one,
  or that the file is edited to name your Pinecall. The page says how a project moves: editing
  `pinecall.json`, nothing else.

- **One way in: `pinecall login`, once per machine, and a project says where it runs in `pinecall.json`.**
  `pinecall link` and the CLI's `pinecall setup` are gone, and no key is written into a project
  any more. `login [url]` signs the machine in and says what the gateway gives your agents; it
  chooses no org. `pinecall new` writes `pinecall.json` at the project's root — the gateway this
  machine is signed in to and the org it runs in, asked when you belong to several (`--org` with
  nobody to ask) — which holds no key and is committed. Every verb finds its key in one order:
  `PINECALL_KEY` in the environment, then in `.env`, then the project's `pinecall.json` and this
  machine's key in that org (minted once from the sign-in, the first time a verb needs it, and kept
  in `~/.pinecall/session.json`), then the sign-in alone outside a project. Each verb's first line
  says the org. A project with a key in its `.env` keeps working as it did. The runtime on this
  machine (`pinecall-runtime setup`) signs it in by itself; `~/.pinecall/local.json` is gone.

- **`pinecall kill [agent]`, an admin's.** Every app holding the agent in the env — whoever's —
  lets go of it and keeps its other agents; it leaves every list, the console and the playground.
  Nothing is erased: its settings and calls stay, and an app that declares it again holds it again.

- The agent `pinecall new` writes takes no message on a blank or a guess: `takeMessage` refuses an `about` (or a name) that says nothing — `not specified`, `unknown`, `n/a` — and tells the model to ask for it; once the message is taken it still answers what the documents answer, and says goodbye when the caller wants nothing more instead of repeating it. Its ring-0 tests say so in the three languages.

- **MCP: a held agent whose thread dies says so.** A tool or a hook throwing where nothing caught it ended the agent's thread, and `status` kept answering `held: thread` while every `chat` and `test` waited out its timeout. The thread's end is now the sentence `status` leads with and every tool refuses with — its exit code and the last lines it printed — until a save loads a version that lives.
- `pinecall setup` on a project whose key points at another host asks that host instead of reading this machine: it advises a stage at a time from what it serves and what it lends, then the org's own keys (`GET /v1/providers/advice`), offers to give the org a key this shell exports, and ends with the `pinecall agent set` line for the stack.

## [0.11.4] — the agent pinecall new writes greets once and takes the message the moment it has both

- The agent `pinecall new` writes asks only for what the caller has not said and takes the message the moment it has both; its view no longer says "Greet the caller" on every turn, which a model that follows the view to the letter did, greeting again at each one.

## [0.11.3] — pinecall setup on a screen; a model with its own slash reaches the gateway whole; pinecall team

- **`pinecall setup`**: the runtime on this machine chosen on a screen (Ink). It reads the machine through `pinecall-runtime setup --recommend` — the card and its memory, Apple silicon, RAM, Docker, an Ollama already running, the key variables set — shows every model measured for a voice agent with whether it fits and how it did, and offers five ways: recommended, all local, with keys, stage by stage (the ears, the end of turn, the thinking, the voice, the judge, the simulated caller — each a list narrowed as you type, `local/<tag>` taking any Ollama model) or chat only. It says where each key is (the environment, an unsourced shell file, nowhere) and never takes one; then runs `pinecall-runtime setup --yes` with the answers. `--yes` and a pipe run the recommended stack as the flags amend it; `--recommend` prints the reading.

- `--llm hf/Qwen/Qwen2.5-3B-Instruct` and `--llm livekit/openai/gpt-5-mini` reach the gateway whole: a model with a slash of its own lost everything after it (`split("/", 2)`), and the gateway was asked for `Qwen`.

- **`pinecall team`**: the org's people, `team password <email>` sets anyone's password (typed twice without echo, or piped), `team reset <email>` makes a one-use link to choose it. The MCP server's `team` tool lists them and answers that link: no password passes through the assistant.

- **The runtime on this machine, with no `login` and no `link`.** A project with no key of its own acts on the runtime `pinecall-runtime setup` left in `~/.pinecall/local.json` (read after the environment and `.env`, never over them); `whoami` says `key from the local runtime`. The MCP server's `runtime` tool runs that setup from an assistant (`up`, `status`, `down`).

## [0.11.2] — released with every other package

- Nothing of the CLI changed: published at 0.11.2 with every other package. `deploy logs` gets fresh lines from a gateway at 0.11.2.

## [0.11.1] — every verb walked again: a deploy followed to the end, every flag refused by name, a broken run says why

- **`deploy up` and `deploy rollback` follow a release to the end.** The follow read the org's whole
  feed and left with a validator's text on the first entry that was not a release's (the gateway
  now filters the feed by type).
- **A flag out of range is refused in words that name it**: `--interrupts`, `--pause`, `--speed`,
  `--backchannels`, `--turns`, `--packet-loss`, `--ambience`, `--give`, `--end-of-turn`, `--record`,
  `--greeting-interruptible`, `--max-duration`, `--endpointing-ms`, `--min-interruption-words`,
  the thresholds, `--k`, `--mode`, `--min-score`, a webhook's URL and a collector's URL. `prompt
  --channel` and `--medium` are checked before the child is started.
- **A file that is not there is refused by name, exit 2**: `agent push`, `remember` and `data dnc
  import` printed Node's own error, exit 1; a settings file that is not JSON says so.
- **`test` says why a run broke.** A run that failed before its matrix (a model the vendor has
  not, a vendor with no key) printed `a golden broke` and nothing else; its reason stayed in
  `--json`. The reason is printed, and the exit says `the run broke`.
- **`supervise`'s one-line description names its moves** (take the line, give it back); it named a
  `transfer` the desk has not.
- **`judges add|on|off|rm` print the gateway's refusal alone**, which now names the verb to type;
  the hint printed above it could call the org's judge Pinecall's.

## [0.11.0] — an agent is one folder; a run followed on the feed; every verb walked, and what is not there refused by name

- **`chat` and `simulate` on an agent nobody holds exit 2**, as `test` and `remember` do: the gateway
  closes the socket with 4000 plus the status it would have answered, and the terminal reads it.
- **`line` says who is running the agent when nobody holds its line**, and `claim` to take it; it
  said "nobody is answering: run pinecall start" while a `start` was running.
- **`pipeline set` and `clear` say where they went** (`agent set`, `agent clear`), as the page
  promised, instead of "too many arguments".
- **`test <golden-name>`** runs that golden of the agent, with or without `.json`, beside a path.
- **`agent pull` prints the corner's own row** — what `push` sends back — and refuses a corner that
  sets nothing; `push` of what the corner holds writes nothing. `runs drift` takes the project's
  agent when none is named. `data export --out` into a folder that is not there is refused by name.
  `docs detach` of a base the corner does not read exits 2, as `attach` does. `deploy logs` of an app
  the box has not is the gateway's sentence, not the stream's raw body.
- **Every verb has a line in `--help`**, and the settings table's labels read whole (`end-of-turn`).
  The providers catalog drops two columns the gateway never filled (`variable`, `also known as`).
- **A new agent gets its `docs/` folder**, with a note on what goes there, as the layout promises.
- **`data policy --disclosure x --no-disclosure`** (and the recording-notice pair) is refused as
  the other contradicting pairs are; it changed the policy before. Its numbers name their flag when
  refused, as `runs drift --limit` and `docs eval --k` do now.

- **A flag said again for each value no longer swallows the path after it.** `test --model haiku
  agents/x/test/goldens/a.json` ran every golden with the path as a second model; `--model`,
  `--case`, `generate golden --say|--tool`, `personas --fact|--expect|--tag`, `judging --option` and
  `telemetry set --header` take one value each time they are said, as the page always wrote them.
- **`sessions log --types` shows those types alone**: the gateway sends every reader the call's end
  (`call.ended`, `call.score`), and a page asked for by type printed them too.

- **A settings write puts only what it moved in your corner.** The first `agent set` (or `docs
  attach`, `memory policy`, `knowledge edit`) on an empty corner copied the team's whole row into
  it, so every field you never touched stopped following the team's. The gateway reads a call's
  settings field by field, and now so does a write.
- **A name the gateway has nothing for exits 2**, as a name typed wrong here always did: a second
  `judges rm x`, `monitors rm <id>`, `runs show <typo>`, `--agent nobody` answered the gateway's 404
  with exit 1.
- **`agent clear` names its fields, or takes `--all`.** With nothing named it cleared the whole
  corner without a word; it is refused now. The MCP's `agent clear` takes `all` the same way.

- **`judges show <name>`** prints one judge whole: whose, its switch, how and when it answers, what
  it reads, its question.
- **What is not there is refused by name, before anything travels**: `agent set` with no field;
  a settings write that changes nothing (`agent clear` of a field nobody set); `lexicon rm` of a
  word the lexicon has not; `docs attach` of a base the env has not; `runs list --limit` outside 1
  to 200; `monitors add --days` other than 1, 7 or 30, which said only "Invalid input"; `agent
  knowledge edit` with no terminal, which hung on an editor nobody could type at. `sessions log
  --limit` is read at last: the flag went to `sessions`, which has one of its own, and the page
  was always 200 entries.
- **Lists read truer.** `personas` names the files written here and not pushed; `cases list
  --status approved` with none says so instead of "no cases here"; `cases groups` puts the cause
  on its own line; `agent show` prints a base's mode and floor beside its k; `runs show` names the
  agent's own model as `test` does; `test` prints its header once; `supervise` acknowledges each
  move it sent (`end sent`). `--rename` is `personas edit`'s and no longer appears in `add --help`;
  `generate golden --help` marks `--say` required.

- **`test` follows the run instead of holding a request open for it.** The gateway answers the
  run as it starts it and plays it after; the terminal reads the row on each `run.changed` of the
  org's feed (and every twenty seconds besides) until it is over. Ctrl-C leaves the run going on the
  gateway, as before; `runs show <id>` reads it. A row still running past the gateway's deadline
  is named as a gateway that stopped, instead of waited on.
- **A golden that gives `memory` on an agent that keeps none breaks alone**, its cell saying what
  policy to set; the rest of the suite plays. It aborted the whole run with a 400 before.

- **`printf 'hello\n' | pinecall chat` answers.** The pipe's lines were read before the call was
  open, said to nobody, and its end hung up a call never spoken to: `chat` printed nothing and left
  the call live. stdin is read once the call is open.
- **`prompt --prod` is refused**, as its page always said: it runs offline, in no env.

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
