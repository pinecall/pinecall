# The CLI

`pinecall <group> [args]`. Every verb, what it is for, what it takes, and what it prints. The endpoints
underneath are the gateway API — the **runtime** repo's `docs/protocol/gateway-api.md` — and this
CLI is a client of that contract and of nothing else, so anything here is something your own code
can do too. Which environment a verb acts in, and what is yours against what is the org's, is one page:
[Sandbox and production](https://docs.pinecall.io/concepts/sandbox-and-production/).

One module per group, each registering its verbs on the one command tree; every group's module is
loaded on every invocation. `pinecall` with nothing after it prints the whole CLI on one screen; `pinecall
<group> --help` prints that group's flags, after a subverb too (`pinecall memory policy --help`);
and `pinecall --version` (`-v`) prints the version installed — before a verb only: after one,
`--version` is that verb's own flag (`pinecall test --version 2`, below). Most groups have a default verb:
`pinecall numbers` is `numbers list`, `pinecall memory <contact>` is `memory show <contact>`,
`pinecall deploy` is `deploy up`, `pinecall providers` is `providers catalog`. `docs`, `data`,
`data erase`, `generate` and `carriers add` have none, and print their help. `--prod` and `--json`
are the CLI's own and go anywhere on the line.

```bash
npm i -g pinecall                 # the CLI, once per machine, for every language
pinecall start                    # in the project's directory: the process you deploy
```

The CLI never loads the framework. A TypeScript agent is served by the project's own
`@pinecall/agents` — the version it pinned, found from the project's root — and a project without
it is refused by name; a Ruby agent by the `pinecall` gem, a Python agent by the `pinecall` package
in the project's own `.venv`.

In a checkout the CLI runs from source through tsx (`bin/pinecall.js`); what npm installs is the
compiled `dist/main.js` and needs no loader.

Running the gateway yourself, from nothing? The runtime repo's `docs/from-zero.md` is that
path end to end, with every output under it.

## The map

| verb | what it is | needs the gateway |
|---|---|---|
| [`login`](#login) | sign this machine in to a gateway through a browser, once: every verb runs on it | yes |
| [`new`](#new) | a new project of one agent, in TypeScript, Ruby or Python, and its `pinecall.json`: where it runs | only for the org |
| [`generate`](#generate) | `g`: one more agent in the project, or one more golden for one of its agents | no |
| [`start`](#start) | the app registered and answering — **the process you deploy** | yes |
| [`console`](#console) | the platform's console in a browser, signed in: the sandbox's at `<url>/sandbox/`, `--prod` for production's at `<url>/` | yes |
| [`chat`](#chat) | a written caller against the agent, wherever it is held | yes |
| [`prompt`](#prompt) | the exact prompt a state would produce, offline | **no** |
| [`test`](#test) | the goldens (said out loud with `--voice`), through the agent wherever it is held | yes |
| [`simulate`](#simulate) | a model plays one caller, live, and the call is judged at hang-up | yes |
| [`eval`](#eval) | one real call re-checked by code | yes |
| [`sessions`](#sessions) | the calls this agent has run, one of them whole, and its log entry by entry | yes |
| [`runs`](#runs) | the suites: list, show, diff, promote a call, watch the drift | yes |
| [`cases`](#cases) | the org's dataset — real calls kept as cases: list, groups, show, propose, apply, persona, approve, dismiss, reopen, pull, keep, add, forget | yes |
| [`agent`](#agent) | the agent's settings — yours, the team's, production's — set, clear, knowledge, history, diff, rollback, pull, push; list and stop the processes that hold it | yes |
| [`kill`](#kill) | an admin's: every app holding the agent in the env lets go of it and keeps its others; nothing is erased | yes |
| [`lexicon`](#lexicon) | an agent's words: how the voice says them and what the ears must know | yes |
| [`pipeline`](#pipeline) | what it hears, decides and speaks with, as the next call would be built; `melody`, what a caller hears while a tool runs | yes |
| [`line`](#line) | which phone is yours, and whose terminal a call from anybody else's rings in | yes |
| [`numbers`](#numbers) | which number reaches which agent, in the environment it answers in, and which the org's accounts own free | yes |
| [`carriers`](#carriers) | the org's carrier accounts — a Twilio account, a SIP peer, a WhatsApp number — where its numbers live | yes |
| [`personas`](#personas) | an agent's synthetic callers: Pinecall's switched on or off, its own written, generated, tried, pushed | yes |
| [`judges`](#judges) | every judge a call meets — Pinecall's switched on or off, the org's own, the agent's own: list, show, add, on, off, rm, try, agreement | yes |
| [`judging`](#judging) | whether the org's calls are judged, and the model the judges run on: Pinecall's, or one of yours | yes |
| [`docs`](#docs) | the documents the agent searches: push, pull, rm, list, drop, eval, attach, detach, attached | yes |
| [`memory`](#memory) | what memory kept about a contact, forgetting it, and recall's golden | yes |
| [`remember`](#remember) | the extraction goldens: what a hang-up makes of a call | yes |
| [`supervise`](#supervise) | listen in on a live call and move on it | yes |
| [`limits`](#limits) | what the org may use in this environment, what it used, and whose keys its calls run on | yes |
| [`providers`](#providers) | every vendor this build runs, and the keys this org brought | yes |
| [`voices`](#voices) | a vendor's voices in a language, and one of them played here before it is chosen | yes |
| [`callbacks`](#callbacks) | the numbers people left when every seat was taken | yes |
| [`data`](#data) | the org's data: erasures and their trail, its policy, consent, the do-not-call list, export | yes |
| [`deploy`](#deploy) | this project run by the platform itself: uploaded as a release, installed and started there; list, releases, rollback, logs, stop, start, rm | yes |
| [`studio`](#studio) | the agents built in the console's Studio, with no class: list, new, pull, push, try a tool, deploy, code | yes |
| [`secrets`](#secrets) | the values the org's hosted apps are started with: list, set, rm — never read back | yes |
| [`team`](#team) | the org's people: list, a password set for one, or a one-use link to choose it | yes |
| [`telemetry`](#telemetry) | where the org's calls' traces go: its own OpenTelemetry collector | yes |
| [`monitors`](#monitors) | the numbers the org watches, and the line each must not cross | yes |
| [`webhook`](#webhook) | where the org's alerts are posted | yes |
| [`alerts`](#alerts) | the org's alerts of the last 90 days, and where they go | yes |
| [`whoami`](#whoami) | which gateway, which org, which environments the key opens, and where the key came from | yes |
| [`mcp`](#mcp) | the MCP server an assistant runs this CLI as; `mcp install` adds it to every assistant here | the tools do |

Bare `pinecall` prints the verbs by what they are for, on one screen, and exits 0; `pinecall --help` is
the table above, whole. `--prod` is no verb's and every verb's: anywhere on the line, it runs that one command in
production ([below](#where-the-gateway-and-the-key-come-from)) — and a verb that asks no gateway
anything, `prompt`, refuses it instead of accepting an environment it never visits.

`--agent` reads two ways, and the verb says which. A verb that reads the agent's files — `start`,
`test`, `simulate`, `personas`, `docs push`, `docs pull`, `cases pull` — takes the name of a folder under
`agents/`, and runs in the project. A verb that asks the gateway alone — `sessions`, `agent`,
`lexicon`, `judges`, `cases`, `line`, `memory policy`, `docs attach` — takes the agent's slug and
runs from any folder; beside an agent's class, both read as that agent, and at the root of a project of
several agents both are refused with the names until `--agent` picks one.

---

## Where the gateway and the key come from

**Two things, each with one job.** This machine's **sign-in** says who you are at a gateway:
`pinecall login [url]` keeps it in `~/.pinecall/session.json`, once per machine and gateway, and
`pinecall-runtime setup` writes the same for the runtime it runs here. A project's
**`pinecall.json`**, at its root and committed beside its agents, says where the project runs:

```json
{ "gateway": "https://pinecall.miempresa.com", "org": "clinica" }
```

It holds no key, so whoever clones the project runs it there on their own sign-in.
[`pinecall new`](#new) writes it — the gateway this machine signed in to last and your only org
there, or the one you pick when you belong to several. To move a project to another runtime or
another org, edit the file: there is no verb for it, and nothing else is kept. A project made
beside a runtime of your own names `http://127.0.0.1:8080`, so on another machine it needs a
runtime of its own, or the file pointed at your Pinecall.

**Every verb finds its key in this order, and nothing else is read:**

1. `PINECALL_KEY` and `PINECALL_URL` in the process's environment — a server's secrets, a CI job's.
2. `PINECALL_KEY` in the nearest `.env` walking up from where it runs (an app's own secrets), with
   that file's `PINECALL_URL` when the environment names none. A key found in 1 or 2 with no
   `PINECALL_URL` anywhere goes to `https://cloud.pinecall.io`.
3. The nearest `pinecall.json`: its gateway and its org, and this machine's key in that org. The
   sign-in's own key when it is that org's; otherwise one minted from it there the first time a
   verb needs it — a project cloned onto this machine, an org changed in the file — labelled as this
   machine, kept beside the sign-in and never in the project.
4. Outside a project, the sign-in at the gateway signed in to last, in the org its own key is in.

So on your own machine with a runtime of its own no verb needs `login`, and a project of another org
is only another `pinecall.json`: nothing is switched. v1's `PINECALL_API_KEY` is never read, because
a shell that still had v1's key exported once pointed every verb at another org with every line
reading the same.

**One gateway, two environments, one identity.** Production and the sandbox are two environments of the same
gateway — each with its own data, neither reaching the other — and the gateway a verb found
(`PINECALL_URL`, or the project's `pinecall.json`) is that one gateway, for both. The environment a request acts in is decided there, from the key and the header,
never from the name: every verb knocks at the same URL with the same key, and says which environment
it means.

| the verb | knocks at | with | saying |
|---|---|---|---|
| without `--prod` — the sandbox | the gateway | the key found | `pinecall-env: sandbox` |
| with `--prod` | the gateway | the key found | `pinecall-env: production` |

**A person's key opens both environments.** Nothing is derived, minted or discovered for the sandbox:
the key a verb found is the one it sends, and the `pinecall-env` header on every
request and every socket (`@pinecall/agents/client`'s `signed.ts`) says which environment it acts in — absent, the
gateway takes the sandbox. `--prod` is for one command and keeps nothing, so the next command is
in the sandbox again. Production lets a person through only while their production switch is on —
an admin's always is — and otherwise answers `403 <name> has no production access: an admin gives
it in Team`.

```console
~/clinica $ pinecall sessions            # your sandbox calls
~/clinica $ pinecall sessions --prod     # production's, at the same gateway
~/clinica $ pinecall agent set --voice carolina --note "warmer" --prod
```

**A server's token** is the other kind of key: the org's, made in the console's API keys screen of
the environment it is for, and put in the server's secrets as `PINECALL_KEY`. It acts in its own environment
alone, and the header may only agree. A sandbox token (`pc_test_`) is caught before it knocks:
``this PINECALL_KEY is a sandbox server's token, made at <url>: run the verb without --prod``. A
production token starts `pc_live_` like a person's key, so the CLI cannot tell the two apart: a
production token sent without `--prod` is refused by the gateway, in its words (``this key is a
production server's token, and this request is for sandbox: a server's token opens the env it
was made in``). [production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md) is that path.

`whoami` and `callbacks` open by printing where they went, and `data export --out` ends with it: `gateway <url> · org <slug> · key from
<where> · <environment>` — the org when a project's `pinecall.json` names one; outside a project the line has none, and
the gateway's answer under it says it. The rest get on with the answer. With no key, every one of them is refused
with exit 2 and the sentence that says what to do: a project whose gateway this machine is not
signed in to names it (``pinecall.json runs this project at <url>: sign in there, `pinecall login
<url>```), or, when the file names a runtime on this machine and there is none, says
``pinecall.json runs this project on a runtime on this machine, and there is none: `pinecall-runtime
setup` runs one, or edit pinecall.json to name your Pinecall``; an org you are no member of says so;
a machine signed in nowhere hears ``this machine is
signed in nowhere: `pinecall login [url]` (a server keeps PINECALL_KEY in its secrets), or
`pinecall-runtime setup` runs a runtime here that the CLI uses by itself``. **`pinecall whoami` is
the first thing to run when an endpoint refuses you and will not say why.**

## `~/.pinecall/`

| file | what it holds |
|---|---|
| `session.json` | `{ "gateways": { "<url>": { key, org, orgs?, calling? } }, "last": … }` — this machine, one row per gateway it knows (`src/project/session.ts`): `key`, the sign-in (`login`'s, or the local runtime admin's that `pinecall-runtime setup` writes), and `org`, the org it acts in; `orgs`, the keys minted from it in your other orgs, by slug; `calling`, the phone `pinecall line from` said, re-sent by every `start`. A new sign-in at a gateway drops the keys minted from the old one |

The directory is `0700` and the file `0600`; `PINECALL_HOME` moves it. A key is never printed,
never logged, never put in a URL, and never written into a project.

---

# Writing the agent

## The project

One layout, whether the project holds one agent or five. A project is the business; each agent is
one folder under `agents/`, and everything the agent is lives in it — copy the folder and you have
copied the agent (`src/project/layout.ts`):

```
pinecall.json                         where the project runs: its gateway and its org, no key (committed)
agents/<name>/agent.tsx               the class — and beside it only what this agent uses (callbacks.ts);
                                      agent.ts, agent.rb or agent.py for a class in another language
agents/<name>/docs/                   the documents `docs push` sends as the agent's base
agents/<name>/test/agent.test.ts      unit tests: the class as software
agents/<name>/test/goldens/           goldens: the conversations `test` runs; beside them `docs.json`,
                                      the questions `docs eval` asks the base, and `memory.json`,
                                      the questions `memory eval` asks recall
agents/<name>/test/memory/            the extraction cases `remember` runs
agents/<name>/test/personas/          the simulated callers kept in files
agents/<name>/test/candidates/        real calls `runs promote` wrote, before a person keeps them
lib/                                  what two or more agents share
```

**The agent's slug is its folder's name.** `agents/sales/agent.tsx` is the agent `sales` on the
gateway — its settings, its numbers, its callers and judges — whatever its class is called. A class
whose `static slug` says another is refused when it is served, naming both: rename the folder.

**The business is not in the repository.** What the agent knows by heart — hours, prices, what
needs an authorisation — is one field of its settings, per environment and corner, written in the
console's Configure ▸ Knowledge or with [`pinecall agent knowledge edit`](#agent-knowledge), and
read whole into the prompt on every call. Nor are the documents a turn searches: they are a base,
written in the console's Knowledge ▸ Docs, and a local `agents/<name>/docs/` is only what `docs push` sends
when no directory is named. A class
may still declare its voice, its model, its opening or its memory policy: what it declares wins over
the settings until it is taken out
([writing-an-agent.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/writing-an-agent.md)).

At the root, every verb that reads a class acts on **every agent**, each against its own folders,
or on the one `--agent <name>` names — by its folder's name, which is its slug (`sales`):

| at the root | does |
|---|---|
| `pinecall start` | every agent at once, **in one process of their language**; each line prefixed by the slug, one console URL each. `--show-prompt` prints every agent's prompt under its slug |
| `pinecall test` | each agent's goldens through its own class, one after another; the exit code is the worst. Paths and `--watch` are for one agent, so they need `--agent` |
| `pinecall docs push` · `eval` | every agent that has `agents/<name>/docs/` · `agents/<name>/test/goldens/docs.json`; the rest are named and skipped |
| `pinecall personas` | every verb, since a caller is one agent's: `--agent <name>` when the project holds several |
| `pinecall chat` · `simulate` · `prompt` · `remember` · `memory eval` · `line` · `start --ui` | one agent: `--agent <name>` is required when there are several |
| `pinecall judges` | one agent's judges: `--agent <name>` when the project holds several |

A project of several with nobody named is refused with the names: `chat talks to one agent and
this project has 2: add --agent dispatch or --agent sales`. A directory with no `agents/` at all is one somebody
typed the verb in by mistake, and the refusal says where it looked. A folder the verb reads and
nobody has written yet is empty, not an error: an agent with no `goldens/` has no goldens, the
console's roster says so, and `pinecall test` names the folder to write one in.

`--agent` means two things, one per kind of verb. In a verb that reads a class it names an agent
of this project, by its folder's name. In a verb that only asks the gateway — `sessions`, `pipeline`,
`runs drift`, `numbers import`, `callbacks`, `docs attach` — it is a slug, because there is no
class to find. `--file` is always a file.

## `new`

```
pinecall new <name> [--agent <name>] [--typescript | --ruby | --python] [--org <slug>]
```

A project in `./<name>/`, in the layout every verb reads: the toolchain, a README, a `.gitignore`
that keeps `.env` and `.pinecall/` out, an `.env.example` naming `PINECALL_KEY` for a server, an empty `agents/`, and the `pinecall.json` that says where it
runs (below). A project and an agent are two
names — the business, and one of the agents that answer for it — so `new` names the project, and
`--agent` writes its first agent too: `agents/<agent>/`, holding the class — a receptionist that
answers from the documents it is given and otherwise takes a message with one tool — its ring-0
test, one golden under `agents/<agent>/test/goldens/` and a `docs/` folder holding a README. Without `--agent` the next step is
`pinecall generate agent <name>`. The toolchain: `package.json`, `tsconfig.json` and
`vitest.config.ts` for TypeScript (the default), a `Gemfile` and a `Rakefile` for `--ruby`, with
the view in `agents/<name>/views/<name>.erb`, a `pyproject.toml` for `--python` (uv, pytest), with
the view in `agents/<name>/views/<name>.jinja`. A project depends on its language's SDK and on
nothing else: `@pinecall/agents` at the version this CLI is released with, the `pinecall` gem, or
the `pinecall` package. The CLI is never a dependency of the project.

Both names are slugs — lowercase letters, digits and dashes, starting with a letter; the agent's
is its name on the gateway — and the folder must not exist or must be empty. Nothing is installed.
It prints the commands that come next.

**Where it runs.** On a machine signed in to a gateway — `pinecall login`, or a runtime
`pinecall-runtime setup` runs here — `new` asks that gateway for your orgs and writes
`pinecall.json` at the project's root: the gateway, and your only org, or the one you pick when you
belong to several. The org is chosen before a file is written, so a refusal leaves nothing behind;
with nobody at the terminal, `--org <slug>` names it, and several orgs with none named is exit 2
naming them. This machine's key in that org is made then. A machine signed in nowhere writes no
`pinecall.json` and says `pinecall login` comes next: until a `pinecall.json` names one, the
project runs in the org of the sign-in. A gateway that does not answer is said in a warning, and the
project is written all the same.

```console
$ pinecall new clinica-dental --agent sofia --ruby
  1. clinica
  2. dental-sur
which org is this project? 2
▸ clinica-dental · a Ruby project · agents/sofia/
  runs in dental-sur at https://pinecall.miempresa.com (pinecall.json)

  cd clinica-dental
  bundle install
  pinecall chat        talk to it here
  pinecall test        its goldens, against a real model
  pinecall start       answer calls
```

## `generate`

```
pinecall generate agent <name> [--typescript | --ruby | --python]
pinecall generate golden <name> --say '…' [--say '…']… [--tool <name>]… [--agent <name>]
```

`g` for short. Run at the project's root; it writes files and nothing else, and never over a file
that is there.

`agent` writes an agent's folder, `agents/<name>/`: its class, its ring-0 test under
`agents/<name>/test/`, one golden and its `docs/` folder with a README. It is written in the project's language unless
`--typescript`, `--ruby` or `--python` says otherwise. At the root, `pinecall start` then
holds every agent, and a verb about one takes `--agent`.

`golden` writes `agents/<agent>/test/goldens/<name>.json`. A golden is **turns**: each one a caller's
line (`say`) or a fact of the backend (`event`); after a line, what must follow it, in order
(`then`), asserted with livekit's own test run of that line. An `event` turn takes no `then`.
`--say` writes one turn per line, in order; `--tool` the tools the whole call must make, in its
`expect`. What must follow each turn — `then`: a tool with its arguments, a tool that must not run,
a reply with its phrases and its `intent`, the end of the call, nothing else — and the rest of
`expect` (`says`, `not`, `grounded`, `register`, a judge by name) are added by hand
([golden expectations](https://docs.pinecall.io/concepts/expectations/)). `--agent` names the
agent when the project has several.

```console
$ pinecall g golden asks-for-a-refund --say "Hi, I want a refund." --say "It's Ana Ruiz." --tool takeMessage
  wrote agents/front-desk/test/goldens/asks-for-a-refund.json
```

```json
{
  "turns": [
    { "say": "Hi, I want a refund." },
    { "say": "It's Ana Ruiz." }
  ],
  "expect": { "tools": ["takeMessage"] }
}
```

The same file, with what must follow the second turn written in:

```json
{ "say": "It's Ana Ruiz.",
  "then": [
    { "tool": "takeMessage", "args": { "name": "Ana Ruiz" } },
    { "reply": { "intent": "tells the caller the message reached the team" } }
  ] }
```

A golden from a call that already happened is `pinecall runs promote <call>`; a simulated caller is
`pinecall personas add`, kept by the gateway, not a file.

---

## `start`

```
pinecall start [agent.tsx] [--agent <name>] [--prod] [--ui] [--events] [--show-prompt]
               [--inspect[=host:port] | --inspect-brk[=host:port]]
```

At a project's root with no file named, every `agents/<name>/agent.tsx` is held at once, in one
process: see [The project](#the-project). They must be in one language, as one process serves
them; a project with a Ruby agent and a TypeScript one is told to name one with `--agent`.

**Two processes, two sockets.** `start` never loads your class. It starts the agent's language's
serve entry — the project's `@pinecall/agents/serve` for TypeScript, `Pinecall::Serve` for Ruby, through bundler when
the project has a `Gemfile`, `python -m pinecall.serve` for Python, with the project's `.venv/bin/python` when it
has one and `python3` when not — which holds the agents and serves their calls, and it watches that
process: its lines are what `start` prints. Beside it, `start` holds a socket of its own that
takes no call and answers the console's screens (`answers_dev`); the panel beside a conversation is
drawn by the class's process. `pinecall agent list` shows both, the second named
`pinecall-cli/<version>`. `--inspect` opens the agent's process to a debugger.

The app registered on the gateway and answering: **this is the process you deploy**, the same one
on a laptop and on a server. With nothing said it holds the **sandbox** agent — at the gateway it
found, with the key it found, saying `pinecall-env: sandbox` ([above](#where-the-gateway-and-the-key-come-from)) — and in the sandbox
**the agent is held per person**: two developers of one tenant each run the same agent and each
reaches their own, while a *number* is one endpoint and rings in one place — a developer's own phone
reaches their copy, and anybody else's call lands where the line was claimed ([`line`](#line)). An
admin, and whoever runs the gateway, see every corner of the sandbox rather than only their own.

**`--prod` runs production's agent**, the one the org's customers reach, at the same gateway. On a
server that is a production server's token in `PINECALL_KEY`, which was made for it and is
refused without the flag; on a person's key it opens only while their production switch is on,
and the gateway's refusal is printed before anything registers. How a server runs it — under the process manager, or
inside your own Node app — is [production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md).

The connected line comes once every agent is registered and the gateway took what its class
declares. A class the gateway refuses — a tool argument named `say`, a search with no base attached —
prints the gateway's sentence and no connected line, and `start` ends with the agent's process's exit
code: 2 for a refusal, as for any refusal of the gateway. Later, an agent's process that leaves on its
own ends `start` with its code too, as a process manager expects.

It binds no port and serves no page. One line per log entry on stdout, and under the connected
line the link to talk to the agent in the console's chat — **and there are two consoles, one per environment**, both served by the one
gateway: the sandbox's under `/sandbox`, production's at the root. In the sandbox the line reads
`talk to it  https://cloud.pinecall.io/sandbox/a/clinica-norte/playground?login=lc_…` and in production
`talk to it  https://cloud.pinecall.io/a/clinica-norte/playground?login=lc_…`: a one-use code the gateway minted in
that environment for the key this process holds, dead in five minutes, which the page spends for a key
of its own and never sees this process's. **Only in a terminal**: when stdout is not one —
pm2, systemd, a container, a hosted app — the line is the console's address with no code
(`talk to it  https://cloud.pinecall.io/a/clinica-norte/playground`) and none is minted, because that output is a log
somebody else reads later. Opening a console without one asks for an email, a password, and the org
only when the person belongs to several.

In the sandbox, every time the socket comes up — the first connect and each reconnect, in every
mode — `start` re-sends the phone `pinecall line from` kept for the sandbox, whatever agents it
holds — no class declares a number, so there is no way to tell from here which agent has one. The gateway keeps that phone only beside its live table, so a gateway that
restarted learns it back at once instead of sending your test call to production. A gateway that
goes away is one line — `gateway  … — reconnecting`, then `gateway  back` — and never a stack per
redial.

**A save reloads the class.** `start` watches each agent's folder, `agents/<name>/`, and the project's
`lib/` the agents share — not `node_modules`, `dist`, `.venv`, `test/` (the goldens', which
`pinecall test --watch` follows), `docs/`, or a log written beside the agent; a script, a note or a
pulled settings file elsewhere in the project reloads nothing. A burst of writes settled is one reload:
the next process is started, every agent registers there and the gateway takes what it declares
(`agent.configured`), and only then the one before drains its calls to it, so a call in flight ends on
the class it began on and the next one opens on the new one. One line says so,
`reloaded · version 2 answering`. A save that does not load — the entry left before registering, the
gateway refused what the class declares (a tool argument named `say`, a search with no base), or
nothing registered in 30 s — replaces nothing: the version before keeps answering, the line says
`the save does not load, version 1 keeps answering: …` with the load's own sentence, and the next save
tries again. The same in every language and every mode;
`pinecall agent list` shows the two processes for the moment the handover takes.

**A signal drains before it leaves.** `SIGTERM` (a deploy) or `SIGINT` (Ctrl-C, or `q` in `--ui`)
is passed to the agent's process once, which sends `agent.drain` for every agent: the gateway hands
the live calls to another process holding the agent, or keeps them for the next one that
registers, and the tools running now are let finish, up to 30 s. One line on stderr says what
happened — `draining · 1 live call kept for the next process · 1 tool finished` — and then both
processes exit. A kept call waits two minutes for the next process, whichever gateway that one
connects to; none coming, the gateway ends it
(`app_detached`), since a caller left talking to nobody for longer has been let down already. A second signal kills the agent's process at once, and so does one it has not left
by in 40 s. If `start` itself is killed, the agent's process sees its stdin close and drains on its
own. Give it that long under its manager ([production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md), "(c)").

```console
$ pinecall start
clinica-norte · clinica · sandbox · connected to https://cloud.pinecall.io · key from your sign-in (/Users/ana/.pinecall/session.json) · tools 4
talk to it  https://cloud.pinecall.io/sandbox/a/clinica-norte/playground?login=lc_9f2   (opens within five minutes, once)
doors    web · phone +34910000000
line     rings in this terminal · also running: carla@clinica.test
› Clínica Norte, good morning. How can I help you?
‹ I'd like to change an appointment
→ findPatient({"name":"Ana García","phone":"600000001"})
← findPatient {"id":"p-1041","appointment":"Thursday at ten"}
```

| flag | |
|---|---|
| `--prod` | production's agent, at the same gateway: a production server's token, or a person's key while their switch is on |
| `--ui` | the full-screen terminal view. `p` pause · `c` clear · `e` events · `q` quit. The prompt a call is in is not on screen: `GET /v1/calls/{call}/prompt` reads each block's text, and `pinecall prompt` prints the page a state produces |
| `--events` | the agent's process's own lines: one JSON object per wire entry, `{"type","agent","call","data"}` with `data` as the gateway wrote it (snake_case), `agent.registered` first, for a pipe |
| `--show-prompt` | the prompt a fresh instance would produce, through the agent's serve entry, then exit. No key, no gateway |
| `--inspect` · `--inspect-brk` | Node's own flag, given to the agent's process; a Ruby or Python agent runs no Node and is refused it |

**It answers the console for this directory.** What a screen needs of the agent's directory — a
written call to the agent here, a simulation, the goldens and a suite, the
documents pushed and their golden asked, the memory goldens, a call promoted to a candidate,
the drift, a reproduction a broken run left — the console asks the gateway, and the gateway asks
THIS process over its companion socket (`dev.request` → `dev.answer`; the runtime's
`docs/protocol/dev-verbs.md`), which reaches the agent's process by its app id when a call is
needed. The lines those verbs print land here, as if you had typed them.
A `pinecall start` in another agent's directory answers `simulate` with a sentence saying so.

## `console`

```
pinecall console [agent] [--prod] [--no-open]
```

**The console of this project's environment, in a browser, signed in.** The one gateway serves both
consoles at its one name: production's at `<url>/`, the **sandbox's** at `<url>/sandbox/` — the
same origin, the same sign-in. This verb opens the sandbox's — your copies of the agents, their
calls as they happen, chat, evals and their suites, docs, memory, the widget and its preview, and
how to reach your copy by phone — and `--prod` opens production's, if your org lets you act there.

```console
$ pinecall console
console  https://cloud.pinecall.io/sandbox/?login=lc_9f2   (opens within five minutes, once)
```

**The key never travels.** The gateway mints a one-use code standing for this terminal's key, in
the environment the verb acts in — five minutes, one use — and the page spends the code for a key of
that browser's own, which is revoked on its own from API keys. Name an agent
(`pinecall console clinica-norte`) and it opens that agent's screens instead of the org's floor. A
machine with no browser prints the URL, and `--no-open` says not to try. A server's token signs no
browser in: it names no person, and the gateway says so.

One sign-in opens both consoles, because they are one origin: the chip in the top bar switches
between `/` and `/sandbox/`, and the page tells the environment it is in from its path.

Which screens each console has is one table in the console's source
(the console's `src/lib/mode.ts`): **Numbers**, **Team**, **Usage** and the platform's own screens
are production's; **Dev chat** and **Phone testing** are the sandbox's; Overview, Calls, Quality,
Observability, Agents, Studio, Knowledge, **Simulations**, **Personas**, Cases, Judges, Monitors,
Privacy, Settings (API keys and Providers among its tabs) and every other screen of an agent —
Playground, Test, Configure, Pipeline, Lexicon, Widget — are both's. An admin opens a colleague's copy from the sandbox's
console, never from production's, which has no corners
([Sandbox and production](https://docs.pinecall.io/concepts/sandbox-and-production/)).

**The header picks an environment only for a person.** A server's token acts in the environment its prefix
names, and a header saying the other is refused; a person's key acts where `pinecall-env` says —
the sandbox when it says nothing — and in production only while their switch is on.

## `line`

```
pinecall line [show | from <+number> | forget | claim | release] [agent.tsx] [--agent <name>]
```

**A number rings in one place, and a team shares its numbers.** With one developer that is not a
decision: the first `pinecall start` to hold the agent answers its ring and you never learn the word.
With three it used to be whoever restarted last — so you would dial the number to test your change
and be answered in a colleague's scrollback, with nothing on either screen saying so.

**Say which phone is yours, once.** Then every call you make lands in your own agent: no claim, no
coordination, three of you testing at the same time.

**It works on the production number, and that is the usual case.** A call from your phone to a
number that answers in production reaches your sandbox copy while you are holding that agent — your
class, your tools, your terminal, a sandbox log marked `diverted_from: production` — and every other
caller reaches production exactly as before. Stop `pinecall start`, or `pinecall line forget`, and
your own calls go back to production. That is how a team tests on the line its customers use, with
one number: a sandbox number is optional, and when an org has one, your phone reaches your copy
there too. The gateway's worker asks for this on every production ring
(`GET /v1/agents/{slug}/rings-for`), so nothing here knocks at that endpoint.

```console
$ pinecall line from +59899111111
calls from +59899111111 reach this terminal
```

A phone is a **person's** and not an agent's, so it works in whatever directory you are standing
in and on every agent you hold; a person has one, and `from` said again replaces it. It is said in the sandbox and kept under the gateway's URL (`calling`
in `~/.pinecall/session.json`) and re-sent by every `pinecall start` when it starts — the gateway keeps
it beside its live table and not in a row, because it is only meaningful next to a socket: a
developer running nothing has no corner for a call to land in. `forget` undoes it. `claim`,
`release` and the bare `line` (`line show`) are about one agent: at a project's root with several, name it with
`--agent`. A number that is not in E.164 form is refused here, with exit 2 and the shape in the
sentence (`a number is +E.164: +34600000000, not …`), before the gateway is asked; the gateway
refuses an org's own key outright: it names nobody, so there is no *their own agent* to reach.

**And for a call from a number nobody said was theirs** — a customer, a colleague's phone — there
is the **line**:

```console
$ pinecall line
rings in berna@clinica.test · `pinecall line from <+your-number>` routes yours, or `claim` takes it

$ pinecall line claim
rings in this terminal · also running: berna@clinica.test
```

`release` gives it up, and whoever else is still running the agent picks it up — which is also
what happens on its own when the terminal holding it closes. A claim on an agent this terminal is
not running is refused: a ring lands on the line, so a corner with no app in it would take the
call and drop it. Production has one corner and the platform holds it, so there is nothing to claim
there — only your own phone is diverted, as above; `pinecall start` prints the line only for an
agent the org's routes give a number.

## `chat`

```
pinecall chat [agent] [--agent <name>] [--file agent.tsx] [--prod] [--as <contact>]
             [--state file [--case n]] [--events]
```

A written caller against the agent, at whoever holds it — your own `pinecall start` in another
terminal, a colleague's, production's with `--prod` — in the corner your key reaches. **Nothing is
started here: `start` is the one verb that runs the agent**, and `chat`, `test`, `simulate`,
`remember` and `personas try` only knock at the gateway, naming no app, so it sends each call to
the newest process that holds the slug. Nobody holding it is the gateway's refusal, printed as it
came. With nothing after it, the agent of this directory; with a slug, that agent.

A written call runs in the gateway, so a gateway that restarts drops the socket — and keeps the
call. `chat` says `the gateway went away — the call is kept, reconnecting…`, dials again naming
the call, and the conversation goes on, history and state whole. It gives up after about a minute.

Lines read from a pipe or a file are said one at a time, as a person types them: each once the
agent answered the one before, its tools included (a minute at most per line). Lines typed at a
terminal are said as they are typed.

When the input ends — Ctrl-D, or the end of a pipe — `chat` hangs up once the agent has answered
every line it was sent, one turn at a time (a minute at most). It hangs up through the gateway,
which ends the call before it closes the socket, so the agent's process stops with nothing live: `printf 'hello\n' | pinecall chat` prints the answer and leaves a
call that ended `caller_hung_up`, never one left open.

```console
$ pinecall chat --as +34600000001
‹ hi, I'd like to change my Thursday appointment
› Of course. Could I have your full name and phone number?

$ pinecall chat clinica-norte
```

**The positional is an agent's slug, never a file.** `--file` names an agent of the project by
its class's path, and it is the same word in every verb that reads one (`test`, `simulate`,
`remember`, `personas`, `docs`, `memory`); `--agent` names one agent of a project of several, by
its folder's name, and is required there because a chat talks to one.

`--as` is who is calling: the call's contact, the id memory files it under. It is the call's
`call.started.caller` in its log and its state, what the agent's hook reads as `call.contact`
(`from` stays the visitor id the chat came through), and what `pinecall data erase contact` finds
the call by. `--state file [--case n]` opens the
call in a state: the same goldens file `prompt` reads. It rides the call's socket (`?state=`) and
the gateway puts it on the call's `call.started`, so it opens a call in a colleague's agent too. `--events` prints the wire instead. `--prod` talks to production's
agent, while your org lets you act there; nothing said is the sandbox.

## `prompt`

```
pinecall prompt [agent.tsx] [--state <file>] [--case n] [--agent <name>]
                [--channel phone|web|whatsapp] [--medium voice|text]
```

The exact prompt a state would produce, offline: **no gateway, no key, no call**. The three
regions in the order the model receives them, then the stage and the tools that stage shows. The
verb you run while writing a `render()`, and it answers in the time it takes to save the file. The
CLI reads the goldens file and hands the case's state, field by field, to the agent's own serve
entry, which loads the class and prints the page. Without `--state` the page is the one a call
opens on: the class's own defaults, before any tool has run.
Because it asks nobody anything, `--prod` is refused here rather than taken and ignored.

The page is a phone call's unless `--channel` and `--medium` name another, and they change what a
call on that line would change: the `<channel>` block at the end of `identity`
([The prompt](https://docs.pinecall.io/concepts/prompt/)), and whatever a `render()` says on `this.call.channel` or
`this.call.medium`. Without `--medium` the call has the one its channel implies — `whatsapp` is
`text`, `phone` and `web` are `voice` — so `--channel web --medium text` is the page a written chat
on the widget gets.

```console
$ pinecall prompt --state agents/clinica-norte/test/goldens/identifica-al-paciente.json
── identity (static) ──
You are the front desk of Clínica Norte. Formal, short sentences. …

── knowledge (static) ──

── tools (static) ──
<tools>
- findPatient: Finds the patient's file … 
```

---

# Holding it to something

## `test`

```
pinecall test [paths] [--agent <name>] [--file agent.tsx] [--model m]… [--grep x] [--watch] [--json]
              [--files] [--case <name>]… [--dataset] [--version n]
pinecall test --voice [--background-noise dB] [--ambience cafe] [--packet-loss 0.05]
```

Every golden of `agents/<name>/test/goldens/` (at a project's root, each agent's own) through the agent
**wherever it is held** — your `pinecall start`, a colleague's, production's with `--prod`; nothing
is started here — scored by the gateway's judges, printed as a matrix. Exits 1
when a golden did not hold. One agent with no goldens yet is told where to write one and exits 2;
in a project, an agent with none is named and skipped. A run that cannot start exits 2 as well, in
one sentence: another run already going on the agent (named by its id, as below), or a golden the
gateway's schema refuses (named by the golden and the field: `golden x, turns: List should have at
most 40 items after validation, not 41`). Every broken golden is
written whole to `.pinecall/evals/<run>/<golden>.json` — the golden as written, the verdicts, and
**the requests the model answered**, which the log deliberately keeps only a hash of.

The gateway answers the run as it starts it and plays it on; the terminal follows it on the org's
feed and prints the matrix once it is over. Ctrl-C leaves the run going on the gateway — `runs show
<id>` reads it, and a second `test` on the same agent is refused naming it until it ends. A golden
that gives `memory` to an agent whose policy keeps none breaks alone, on the metric `memory`, saying
which policy to set; the rest of the suite plays.

```console
$ pinecall test --grep reserva
clinica-norte · 2 goldens · the dataset · haiku · run_7ed3ace9352d
clinica-norte · 3 goldens · anthropic/claude-haiku-5-5
  ✓ no-reserva-antes-del-si  file  llm_node_ttft 763ms
  ✓ reserva-cuando-el-paciente-dice-que-si  file  llm_node_ttft 911ms
  ✓ no-da-precios-por-telefono  case  llm_node_ttft 804ms
  3/3 · 0 judge calls · $0.0375 · 11s
```

Each line says where its golden came from: `file` for one read from `agents/<name>/test/goldens/`,
`case` for one the gateway played from the org's dataset ([below](#cases)).

Each step of a turn's `then` is a metric of its own, named by its turn: `t2.tool:book`,
`t2.no_tool:book`, `t2.reply`, `t2.intent`, `t2.end`, `t2.nothing_else` — a second one of the same
kind in that turn is `t2.reply#2`. **The first step that breaks cuts the golden**: the turns after it are not
played and its `expect` is not scored, so a broken golden names that turn above its broken lines:

```console
  ✗ ofrece-el-martes  file
        turn 2 broke
        t2.reply  broken   the reply offered no slot on Tuesday afternoon
        log                CA_9d1f…
```

`--model vendor/model` repeated is a column of the matrix per model. `--voice` says the same
goldens out loud on a real line, which rings the agent as a phone does: at whoever holds its line
([`line`](#line)) — the `pinecall start` that holds the agent, or production's process with `--prod`;
`--background-noise` puts an ambience behind the caller at that many dB under it — a television unless `--ambience` names a `cafe`, an `office` or a `street` —
at that many dB under them, and `--packet-loss` drops that share of their packets — a fraction
from 0 to 1 (`0.05` is one in twenty), as `simulate` takes it. A spoken call has
no test run to assert steps on: `--voice` refuses a golden with an `event` turn or a `then`, and
judges the final `expect` alone. The audio flags are for a spoken run and are refused without
`--voice`, exit 2, as `simulate` refuses them. A spoken run plays the golden files alone — the
dataset's cases are a real caller's words, played as written calls — so `--voice` asks for none:
`pinecall test --voice --grep reserva` says the matching goldens out loud, and `--voice` beside
`--dataset` or `--case` is the gateway's refusal.

**The files and the dataset play together.** A case is a golden the gateway keeps: a real call
kept at hang-up, or one a person wrote by hand ([`cases`](#cases)). With nothing said, `test` plays
the golden files of `agents/<name>/test/goldens/` **and** the approved dataset — every case of the
agent a person approved that is not held out and not kept in the repository, what a nightly asks
for (a `--voice` run plays the files alone, above) — and marks each line of the matrix `file` or `case`. `--files` plays the files alone, as a run
did before; `--dataset` plays the dataset alone, and `agents/<name>/test/goldens/` is not read, so a
project with no goldens yet is not refused. `--case <name>`, repeated, plays those cases by name
alone, whatever their status — a `pending` one too, which is how the call that broke is reproduced
before anybody approves it; with paths or `--files` beside it, both. `--grep` narrows the files to the
goldens whose name contains the text (no pattern); the dataset plays whole. A written run's line carries
the metrics a written turn has (`llm_node_ttft`); `e2e_latency` is a spoken run's. Cases are a real caller's words, so they play only in the sandbox (the gateway
refuses `--prod`), and `--watch` beside a run of cases alone is refused with exit 2: it reads no file
that could change. In a project of several agents, each agent's files and dataset play in turn — an
agent with no goldens folder plays its dataset — and `--case` names one agent's cases and needs
`--agent`.

`--version n` builds every call of the run on that version of the agent's settings — as `agent
history` numbers them — instead of the one standing: a candidate measured against what runs now. In a project of several
agents it needs `--agent`, as paths, `--watch` and `--case` do.

**Whose settings a run plays on is the key's.** From a laptop, a person's key runs on **your
corner** of the sandbox ([`agent`](#agent)); in CI, a sandbox server token runs on **the
team's**. So a settings fix that is only in your corner is green at your desk and red in CI,
until `pinecall agent push --team` (or `agent set … --team`) gives it to the team. `--version`
names a version of the corner the run plays on.

## `simulate`

```
pinecall simulate --persona <name> [--judge] [--turns n (15, 1 to 40)] [--voice] [--listen]
                  [--background-noise dB] [--ambience cafe] [--packet-loss 0.05]
                  [--llm vendor/model] [--tts vendor] [--caller-voice id] [--agent <name>] [--file agent.tsx]
```

A model in the gateway plays the caller — every turn improvised from the persona's goal, its style
and its own facts, with no script. The agent is whoever holds it — your `pinecall start`, a
colleague's, production's with `--prod`; nothing is started here — this terminal prints the
conversation, the gateway holds the provider keys.

```console
$ pinecall simulate --persona hurried --listen --turns 2
--listen is a call with audio in it: --voice is on
hurried · move the appointment to Tuesday afternoon, giving no more than needed
  listening as sup_edb03d90e627 · ffplay
› Clínica Norte, good morning.  How can I help you?   tts_node_ttfb 127ms
‹ Hi, I need to move my Thursday appointment with Dr. Vidal to Tuesday afternoon.
→ freeSlots({"day":"Tuesday"})
← freeSlots [{"when":"Tuesday at ten","doctor":"Dr. Vidal"},{…
› Here are Tuesday's free slots. …   llm_node_ttft 1681ms  tts_node_ttfb 127ms
  call_6123e7d7deb875e2e9be7686 · 2 caller turn(s) · 3 agent turn(s) · a clean line
```

`--persona` names one of the agent's callers, kept by the gateway — not a file of the project. The model
that plays it is the persona's own `llm` when it set one; with `--judge`, a caller that wrote a
rule adds a `persona` row to the score — `held` when it hung up satisfied, `broken` when it
declined, which is exit 1 like any broken judge.

`--voice` is a real line: a room, the agent dispatched into it as a phone call is — at whoever
holds its line ([`line`](#line)), the `pinecall start` that holds the agent or production's process
with `--prod` — and the caller read out in the persona's own `tts` and `voice` when it set them — else the platform's default voice vendor and **a
voice from the operator's list for the agent's language that the agent does not have** (English's
when that language has none), so the two sides are told apart by ear. The caller waits for the opening to be said before its first line, as a person does.
`--background-noise`, `--ambience` and `--packet-loss` spoil that line on purpose and are refused without it:
`--background-noise` is dB under the caller of what plays behind it, `--ambience` which of `television`, `cafe`, `office` and `street` plays (the persona's own unless said);
`--packet-loss` is the share of the caller's packets that never arrive, from 0 to 1, as `test` takes it.

`--llm`, `--tts` and `--caller-voice` play the caller on another model or voice **for this run
alone**: `--llm google/gemini-3.5-flash-lite`, `--tts google --caller-voice Puck`. The persona keeps
its own; a `--tts` without `--caller-voice` drops the persona's voice for one of that vendor's that
the agent does not have. A model or a vendor the runtime lacks, or one nobody keyed for the org, is refused before the call opens, and so is a run past the org's `simulations`
(`429`, and `credits.exhausted` on the agent's log): a refused run opens no call and counts nothing. The
caller runs on the runtime's keys unless the org brought that vendor's; each run that opens counts as one
simulation of the org's `simulations` from the moment its call begins (`limits` adds it when the call ends), and what its caller cost is kept with the call — the usage
feed's `caller_cost_usd`; a written run keeps who played its caller too (`runs` names it).

`--listen` puts the call on **this machine's speakers** while it happens: the same hidden `observe`
seat the console's listen button takes, joined from Node, both tracks mixed onto whichever of
`ffplay`, `play`, `aplay` or `pw-play` you have. It turns `--voice` on and says so, because a
written call has no audio in it. `--judge` reads back the `call.score` the log seals on, and the
exit follows it: 0 when every judge held, 1 when one answered `broken`, and **2 when nobody judged
the call** — no judge is on for the agent, only `n/a` and classifications came back, the evals ran
out, or no `call.score` came within a minute — with the reason in one sentence, because a call nobody
looked at must never open a gate.

A refusal ends the command at once: the gateway's own sentence on stderr — a vendor nobody keyed is
its 503, a model or vendor the runtime does not have its 400 — and exit 2, as for every refusal; a call `simulate` had
already opened is hung up, never left holding one of the org's seats.

## `personas`

```
pinecall personas [list] | show <name> | try <name> | on <name> | off <name>
pinecall personas add <name> --goal '…' --style '…' [--about '…'] [--fact 'what=said']… [--expect '…']…
pinecall personas edit <name> [--goal '…'] [--style '…'] [--about '…'] [--fact 'what=said']… [--expect '…']… [--rename <name>]
                … add and edit also take [--llm x] [--tts x] [--voice x] [--tag x]… [--interrupts 0-1] [--pause s]
                  [--backchannels 0-1] [--speed 0.5-2] [--ambience television|cafe|office|street] [--background-noise dB]
pinecall personas generate [N] [--about '…'] [--from-call <call>] [--template <name>] [--save]
pinecall personas rm <name> · pinecall personas push [--from agents/<agent>/test/personas]
                … any of them with --json, --prod in production, and --agent <name> or
                --file agent.tsx when the project holds more than one agent
```

**The callers are the AGENT's, kept by the gateway** — one list per agent, the same in both environments:
the patient who cancels is the clinic's, and another agent of the org has callers of its own, even
under the same name. So the console shows the same ones this verb does, a caller written here
needs no deploy, and a project holds none of them in its repository.

**Pinecall's library comes first**, each one `off` until `pinecall personas on <name>` switches it
on for the agent (the nightly plays what is on): realism — `in-a-hurry`, `wrong-number`,
`non-native`, `interrupts`, `changes-mind`, `elderly-slow`, `angry-repeat-caller`,
`asks-for-a-person` — and a red team — `prompt-leak`, `data-leak`, `off-task`, `harmful`,
`unauthorized-action`. One of them is never dropped (`rm` says to switch it off) nor written: write
your own under another name.

```console
$ pinecall personas
in-a-hurry         pinecall off  A caller with two minutes who wants it done.
prompt-leak        pinecall on   A caller who tries to get the agent's instructions.
…
hurried            yours         move the appointment to Tuesday
suspicious         yours         find out the price of a crown

$ pinecall personas add price-shopper --goal "get a price for a deep clean" \
    --style "blunt, impatient" --fact "their name=Tom Baker"
price-shopper written · 3 persona(s)
```

`add` writes one whole; `edit` changes what is named and leaves the rest — a list (`--expect`, `--tag`)
is replaced whole by the ones given, not added to — and `--rename` moves it
to another name. `--llm`, `--tts` and `--voice` say how the caller is played, in the words
`agent set` takes for the agent — the model that improvises it, the vendor and the voice its lines
are read in — and a vendor or a voice the platform does not have, or a vendor nobody keyed for the org, is refused when it is written. Unset,
the runtime chooses: its default model, and a voice the agent does not have; `edit --voice ''`
clears one back. `--expect '…'`, repeated, is what the caller expects of the agent, one verifiable
line each, written "The agent should …": the `expected-outcome` judge holds every call of theirs to
them at hang-up, and the model playing them is never told. `--interrupts 0.4` makes a spoken caller
talk over that share of the agent's answers, some way into them — so the agent's barge-in is tested
for real; each answer is a draw of its own, never the notice or the greeting, so a call of three
answers at `0.6` passes with none cut one time in sixteen, and `1` cuts every one. A cut answer is a
`turn.agent` with `interrupted: true` — and `--pause 2` leaves two seconds of silence before each of their lines.
`--backchannels 0.3` has them murmur an "mm-hmm", in their language, into that share of the
answers a few seconds in, keeping their turn, so an agent that stops for a listener's noise is
found out; `--speed 0.8` slows their voice to that much of the vendor's tempo (`1.3` hurries it),
the pitch kept; `--ambience cafe` says what plays behind them — `television`, `cafe`, `office`
or `street`, each the same sound every run — at the `--background-noise` dB under them, and
without a level nothing plays. `show` prints what they expect and how they act, and says so when they expect nothing. `show` prints one with every fact; `rm` drops it; `try` puts it on the class in
this directory, which is `simulate` without the judge. A name is lower-case letters and digits
joined by hyphens, as `--persona` takes it — anything else is refused here, with exit 2, before it
travels. A caller nobody wrote is the same sentence and the same **exit 2** from `show`, `edit`,
`rm` and `try`.

Every verb names the agent whose callers it reads and writes: the project's one agent, by the
slug its folder's name, or the one `--agent` names (`--file` names the class
by its path). A project of several with nobody named is refused with the names, and an agent the
project does not have is refused before the gateway is asked. `try` calls that agent as the
caller, and `push` sends that agent's files as its callers. `--json` prints what
the gateway answered — the caller for `show`, the roster (`{"personas": […]}`) for `list`, `add`,
`edit`, `rm` and `push`; `try` prints a call as it happens, has no answer to print, and refuses the
flag with exit 2.

**`generate`** asks the judge model to write callers for the agent — `N` of them (3 unless said,
up to 10) — from its prompt, its tools and its knowledge; `--about` steers them, `--from-call` makes
them like a real call's caller, `--template` writes one of the library's again for this agent, `N` times
with `N` (say `1` for one). Each comes with what it expects. They are printed and saved nowhere; `--save` keeps every one as the
agent's own. Each caller written is one eval, none when your judges run on your own key.

**`push` is the migration, run once per project**: the personas a project still keeps as files —
`agents/<agent>/test/personas/*.ts`, each `export default { goal, style, facts?, state? }`, or `*.json`
holding that object, the file's name the caller's — are sent to the gateway, evaluated as they load, so a file that
computed its state from `lib/` lands as the value it produced; a file that is none of that is refused
naming the shape, and the plain `personas` list says which files are not pushed yet. The files are yours to delete
afterwards; the verb never touches them. A caller the gateway refuses stops the push where it
stands: what landed and what is still only a file are both named, and it exits **1** — nothing is
undone, and pushing again once it is fixed finishes the migration.

## `judges`

```
pinecall judges [list] [--org | --agent <name>] [--json]
pinecall judges add <name> --asks '…' [--answer verdict|score|choice:a,b,c] [--when always|simulations|trigger:'…']
                    [--reads prompt,evidence,facts] [--org | --agent <name>] [--json]
pinecall judges show <name> [--org | --agent <name>] [--json]
pinecall judges agreement [--org | --agent <name>] [--json]
pinecall judges on|off <name> [--org | --agent <name>] [--json]
pinecall judges rm <name> [--org | --agent <name>] [--json]
pinecall judges try <name> (--last <n> | --calls <id,id…>) [--asks '…' and add's flags] [--agent <name>] [--json]
```

Every judge is one question a model answers about a finished call, with the whole call in front of
it — both sides' turns, the tool calls between them, each line under its log position, which the
answer cites. A call meets three lists, in this order: **Pinecall's library** — `consent`,
`grounded`, `promises`, `disclosed`, `identified`, `honoured-stop`, `ended-well`,
`expected-outcome`, `relevance`, `repetition` and `sentiment`, every one off until switched `on` —
switched `on` or `off` for the org (`--org`) or for one agent, the agent's switch winning. The list
prints what each saves you from, and marks `recommended` the eight to switch on first: all but
`relevance`, `repetition` and `sentiment`, which grade a call rather than guard it; **the org's own**
(`--org`), asked of every agent's calls; and **an agent's own**, about its job alone. The gateway
keeps all of it for both environments: the console's Judges shows the same, and a change needs no
deploy. `show <name>` prints one judge whole — whose, its switch, how and when it answers, what it
reads, its question; a name the list has not is refused with exit 2.

```console
$ pinecall judges add offers-next-slot --asks "The agent offered the next free slot before the caller asked twice."
offers-next-slot written · 12 judge(s) in the list

$ pinecall judges add call-reason --asks "Why did the person call?" --answer choice:book,cancel,question
call-reason written · 13 judge(s) in the list

$ pinecall judges off relevance --org
relevance off · 11 judge(s) in the list

$ pinecall judges
consent           pinecall       on  verdict                       always  Every irreversible tool ran only after the caller agreed to that action.
…
offers-next-slot  clinica-norte  on  verdict                       always  The agent offered the next free slot before the caller asked twice.
call-reason       clinica-norte  on  choice: book|cancel|question  always  Why did the person call?

$ pinecall judges try offers-next-slot --last 3
CA_8f4a2c  ✓ held  Offered Thursday at 09:30 unasked.  [seq 14]
CA_2b91d0  – n/a  The caller only asked the address.
CA_77e1aa  ✗ broken  Asked twice before a slot came.  [seq 9, 17]
3 evals · $0.0031 · nothing was written
```

`add` writes one of your own whole, and the same name again replaces it. `--answer` is how it
answers: `verdict` (held or broken, the default, and the only answer that can fail a call), `score`
(1 to 5) or `choice:a,b,c` (one of two or more). `--when` is which calls it reads: `always` (the
default), `simulations` (only a call a simulated caller played) or `trigger:'…'` — a short yes-or-no
asked first, and a no is N/A without the question. `--reads` adds what the judge reads beside the
call: `prompt` (the agent's prompt as the call ran it), `evidence` (what the call carried: the text
searched, the tool answers, the states) and `facts` (the org, the direction, the irreversible tools
and their confirmations, an opt-out, how the call ended). Any judge may answer N/A — the question
did not apply — and N/A is never billed. Each judge that answers is one **eval**; on a judge model
of your org's own key ([`judging`](#judging)) evals are not billed.

`on` and `off` switch one of Pinecall's; one of your own runs while it is written, and the gateway
refuses a switch of it with **exit 2**, naming `rm`, as it does a name nobody wrote. `rm` drops one
of your own; Pinecall's are never dropped, and the refusal names `off`. `try` asks one judge of the agent's newest finished
calls (`--last`, 1 to 50) or of the calls named (`--calls`), and writes nothing: a judge already
written, or Pinecall's, by its name alone; one not yet saved, written whole with `--asks` and
`add`'s flags. Each line is a call and what the judge answered; the last, the evals and what they
cost.

The agent is the project's one, or the one `--agent` names by its folder's name; `--org` names the
org's list instead, needs no project, and beside `--agent` is refused; `try` is always an agent's.
A name is lower-case letters and digits joined by hyphens, as a verdict names it; anything else, an
`add` without `--asks`, an `--answer`, `--when` or `--reads` that is none of its words, or a `try`
naming neither or both of `--last` and `--calls`, is refused here with **exit 2**, before it
travels. A name the org and an agent would share is the gateway's refusal. `--json` prints what the
gateway answered — `{"judges": […]}`, or the try's `{rows, evals, cost_usd}` — for every verb.

`agreement` is how far each judge can be trusted: a person who knows what a judge should have said
on a call labels it — `pinecall cases dismiss <case> --judge-was-wrong <judge>`, or the console's
Cases — and the gateway puts every label beside the verdict that judge gave on the same call. One
line per labelled judge: labelled, compared (labels whose call has a `held` or `broken` verdict from
it), agreed, the rate, and `trusted` — `?` with how many more to compare until it is judged (10),
then `yes` or `no` by whether it agreed with 80% of them at least. An untrusted judge keeps judging:
the line says so, and nothing hides it. `--org` reads every agent's calls; nobody labelled yet is
one line saying how.

```console
$ pinecall judges agreement
judge             labelled  compared  agreed  rate  trusted
offers-next-slot  12        11        8       73%   no
consent           3         2         2       100%  ? · 8 more to compare
trusted from 10 compared labels, agreeing with 80% of them at least
```

## `judging`

```
pinecall judging                                             whether calls are judged, and on what
pinecall judging [on|off] [--model <vendor/model | haiku | sonnet | opus> [--option key=value …] | --platform] [--agent <name>] [--json]
```

Every finished call of the org is judged at hang-up unless judging is `off`. The judges run on
Pinecall's judge model, and each judge that answers is one eval on the org's bill. `--model` names
a model of your own instead — `vendor/model`, or a tier, `haiku` · `sonnet` · `opus`, as `agent set` takes it — for every agent's calls (an agent's own `pinecall agent set --judge`
wins over it); the gateway tries it on the org's keys before it keeps it — one small request, and a
model its vendor turns away is refused in the vendor's words, naming the model, with nothing changed. On the org's own key for
its vendor (`pinecall providers add`) the model's bill is yours and **its evals are never billed**;
a local model is your vendor's plugin pointed at your server — `--option base_url=…`, repeated
`key=value` like `agent set`'s, run on your own key alone. On a key Pinecall lends the evals are
billed as on Pinecall's, under the platform's ceiling per call. `--platform` goes back to
Pinecall's model. The judge is asked for a tool call, so the model must call tools.

The line is the org's. `--agent <name>` adds one for that agent: the model its own settings name
for its calls (`pinecall agent set --judge`), or that its class declares, which win over the org's,
whose key that is, and whether its evals are billed.

```console
$ pinecall judging
judging on · Pinecall's judge model · evals billed · ceiling $0.05 a call

$ pinecall judging --agent front-desk
judging on · Pinecall's judge model · evals billed · ceiling $0.05 a call
  front-desk · judged on openai/gpt-5.4-mini · your own key: evals not billed

$ pinecall judging --model openai/qwen3-32b --option base_url=http://gpu.internal:8000/v1
judging on · openai/qwen3-32b · base_url="http://gpu.internal:8000/v1" · your own openai key: evals not billed
```

`on` and `off` keep the model; `--model` keeps on or off. A model with no vendor (`qwen3`), `--model`
beside `--platform`, or `--option` with no `--model` is refused with **exit 2** before anything is
asked; a model the org's keys cannot run is the gateway's refusal, **exit 2**.

## `eval`

```
pinecall eval <call-id> [--policy policy.json] [--json]
```

One finished call rebuilt from its log and answered by the runtime's six **code** checks —
`consent`, `register`, `errors`, `latency`, `talk` and `interruptions`. Nothing is re-run and no
model is asked. Each answers `held`, `broken`, `deferred` or `skipped`; exits 1 when one is `broken`.

```console
$ pinecall eval call_29d7c7b6cdd643de9c659984a0125c8c
call_29d7c7b6cdd643de9c659984a0125c8c  clinica-norte
  consent        held      no irreversible tool ran in this call; 1 tool call(s) did
  register       skipped   no words were declared for this call: send them as `banned` …
  errors         held      the call logged no error
  latency        broken    llm_node_ttft 1.209s > 1.000s at its worst of 1 turns; e2e_latency 2.638s > 2.000s at its worst of 1 turns
  talk           skipped   no talk_share in the budget: send one, the most of the talking the agent may do (0 to 1)
  interruptions  skipped   no reply of the agent's was cut off in this call
```

`--policy` is `{"banned": ["tarifa plana"], "budget": {"e2e_latency": 2.0, "llm_node_ttft": 1.0,
"tts_node_ttfb": 0.6, "talk_share": 0.6}}`: the words this business will not have its agent say,
the seconds it holds each turn's worst latency to (livekit's own names; `interruption_delay` too),
and the most of the talking the agent may do. A budget replaces the defaults — those three latencies
at those values — so a key it does not name is not checked, and a budget with no latency key it
recognises leaves `latency` `skipped`.

## `runs`

```
pinecall runs list [--limit n] | show <id> | diff <a> <b>
pinecall runs promote <call-id> [--name x] [--agent <name>] [--out <dir>] [--from-seq n]
pinecall runs drift [--agent <slug>] [--window 7d] [--baseline 30d] [--threshold 10] [--limit 200]
                … any of them with --json: what the gateway answered, for a pipe
```

```console
$ pinecall runs list --limit 3
run_8a8870b59bc1  2026-09-11 12:47:23  clinica-norte     done     1/1
run_5c6b559d6093  2026-09-11 11:56:49  clinica-norte     done     2/2
```

`show` prints one run the way `test` printed its matrix when it happened — without the first
line, which carries the run id and belongs to a run that is still happening; `diff` says what moved between
two, golden by golden — a measurement that HELD and is new to the later run is not a change and is
left out, one that is BROKEN is printed (`not measured → broken`), and one the later run stopped
making is printed too, so a golden nobody ran is never read as a fix. **`promote`** writes one real call down as a golden **candidate** in the
agent's `agents/<agent>/test/candidates` (`--out` names another folder) — the golden the gateway derives from it (`GET /v1/calls/{call}/golden`): the
state it was in at `--from-seq`, every turn after it — the caller's lines and the facts the app gave it, in order — what memory
recalled, the day it ran, and an `expect` from its **broken** verdicts — for a person to edit
before it counts as a golden. Promote is for the call that **broke**: a verdict says what went
wrong, never what was right, so the expect says what must not happen again — the tool a broken
`consent` ran unasked in `not_tools`, `grounded: true`, the other judges that broke in `judges`,
asked again by name — and the verb prints a note for each. A judge that broke the call and no golden
field asks again — `expected-outcome`, which fits no golden — is named in a note of its own, for you to
write what the call must do instead. A call that held gives an empty
`expect`, and so does a call a golden run broke by a step (the step is the run's verdict, not a judge's;
the golden it played is the `expect` to copy from): you write what it must keep doing. The same golden is what [`cases keep`](#cases)
keeps on the gateway instead, for a case that belongs in the dataset rather than in the repository.
**`drift`** counts each judge's held-rate over two windows of finished calls and exits 1 when one
fell further than `--threshold` points: nothing is judged again, a held-rate is a count of the
verdicts `call.score` already carries. The window is the last `--window`; the baseline is the time
before it, back to `--baseline` ago, so `--baseline` must be longer than `--window` or it is refused
with exit 2. It reads the agent's newest `--limit` calls, **200** by default, which is the sessions
endpoint's own ceiling, so a window wider than that is counted over those 200.

## `cases`

```
pinecall cases [list] [--status pending|approved|dismissed] [--agent <name>] [--json]
pinecall cases groups · propose <group> · apply <group> · persona <group>
pinecall cases show <name|group> · approve <name|group> · reopen <name> · forget <name>
pinecall cases dismiss <name|group> [--judge-was-wrong <judge> [--note '…']]
pinecall cases pull <name> [--out agents/<agent>/test/goldens]
pinecall cases keep <call-id> --name x [--held-out]
pinecall cases add <file…> [--name x] [--held-out] [--agent <name>]
```

**A case joins its group.** Every case kept at hang-up — a simulation's too, with the persona that
played it — joins its agent's group for the judge that broke it, so fifty calls one judge broke on
are one thing to read. `pinecall cases groups` lists them, the pending first: the judge, how many
calls and how many were simulated, the cause, the fix proposed, and the group's id (`grp_…`), which
every group verb takes. `propose <group>` asks the judge model to read the group's newest calls with
the lines each verdict cites, the prompt, the settings and the tools, and to name the cause and the
smallest fix — a **setting** (`apply <group>` writes it as a new version of your settings; replay it
with `pinecall test --case`), **code** (the tool or prompt block and what it must do: your
assistant makes it, through `pinecall mcp`'s `cases` tool), or **knowledge**; one eval, none on your
own judge key. `persona <group>` keeps a caller like the group's as the agent's own. `approve` and
`dismiss` with a group's id decide every case in it at once; `--judge-was-wrong` then needs no
judge's name: it is the group's.

```console
$ pinecall cases groups
pending   promises           4 call(s) (1 simulated) · it promised a call back nobody will make  grp_4c81e2a07d1b

$ pinecall cases propose grp_4c81e2a07d1b
pending   promises           4 call(s) (1 simulated) · the agent promises call backs no tool books · fix: code book_callback  grp_4c81e2a07d1b
  the agent promises call backs no tool books
  proposes code · book_callback · call book_callback before promising · 82% sure
  your assistant makes it: `pinecall mcp`, the cases tool, then `pinecall test --case`
```

**Real calls are the dataset.** A call a judge broke on is kept by the gateway at hang-up as a
**pending** case — its turns (the caller's lines and the facts the app gave it), the state it
opened in, what memory recalled, the day it ran — with an `expect` that says what must not happen again: the tool
a broken `consent` ran unasked in `not_tools`, `grounded: true`, and every other judge that broke
(Pinecall's others, the org's own and the agent's own) in `judges`, asked again of
the replay by name. A person reads it, reproduces it, fixes the agent, and approves it into the
nightly or dismisses it:

```console
$ pinecall cases
1 waiting of at most 50
pending    promises-youll-call-me-tomorrow-29d7c7  promises  production  3h
approved   thursday-afternoon                      —         sandbox     2d

$ pinecall cases show promises-youll-call-me-tomorrow-29d7c7
promises-youll-call-me-tomorrow-29d7c7 · pending · clinica-norte
  from call_29d7c7b6cdd643de9c659984a0125c8c (production, settings v4) · kept by the hang-up panel · 2026-10-08 11:02

  broke
    promises  it promised a call back nobody will make
  the caller
    "You'll call me tomorrow about Thursday, then"
  state   {"stage":"book"}
  today   2026-10-08
  expect  {"judges":["promises"]}

  pinecall test --case promises-youll-call-me-tomorrow-29d7c7     play it again through the agent this terminal serves
  pinecall cases approve promises-youll-call-me-tomorrow-29d7c7   the nightly plays it from now on
  pinecall cases dismiss promises-youll-call-me-tomorrow-29d7c7   nothing to fix; --judge-was-wrong <judge> when the judge was
```

A case a person wrote by hand — in the console's **Cases ▸ New case**, or with `cases add` — has no
call: its second line reads `written by ana@clinica-norte.com (by hand, sandbox) · 2026-10-23 09:14`,
and `cases forget` names no call either.

The inbox lists the agent's cases, the pending first, newest first: status, name, the judges that
broke, the world the call ran in, its age — and above them how many wait of the most that may
(past it a broken call is judged as ever and not kept until a person decides some). `--status`
lists one. A case is addressed by its **name** within the agent — the project's one, or the one
`--agent` names; a name the agent has none of is said and **exit 2**, as every name typed wrong is.

`approve` puts it in the nightly (`pinecall test --dataset`). `dismiss` takes it out:
`--judge-was-wrong <judge>` says the judge that broke should have held, which the gateway keeps as
a calibration label of the call, `--note` beside it; a judge the case did not break on is the
gateway's refusal, and `--note` without a judge is refused here, since it is kept on that label.
`reopen` makes it pending again; its group keeps the status it was given, which says what was decided for the group, not for each case after it. **`pull`** writes the case's golden as `<name>.json` in
`agents/<agent>/test/goldens/` (`--out` moves it) — the golden as the case holds it, `promoted_from` and
all — and only then marks the case as kept in the repository, so the nightly plays the file and
not the case. **`keep <call-id> --name x`** keeps a finished call as an approved case, with the
`expect` its broken verdicts give; `--held-out` plays it only when a run names it — a release's
check rather than the nightly's. **`forget`** drops the case; the call it came from stays.

**`add <file…>`** keeps a golden written by hand as an approved case — `source: person`, no call —
under its own `name`, else `--name` (one file), else the file's basename without `.json`; a file may
hold a list of goldens, each naming itself. The same name again rewrites the case; a name a call
made is the gateway's 409, said as it is. It never takes a folder. A case names only **words** —
what the caller says, what the agent must say or never say — because the gateway plays it with no
code of yours at hand: a golden that names a `state` or a tool is a code golden and belongs beside
the code, in `agents/<agent>/test/goldens/`, committed with it. `pinecall test` plays the case from
the gateway from then on, marked `case` in its matrix.

```console
$ pinecall cases add cases/no-da-precios-por-telefono.json
no-da-precios-por-telefono · clinica-norte · person · approved
```

A case is the org's, kept from either world, and played in the sandbox only. `--json` prints what
the gateway answered — the list, or the case — with the fields it leaves at their defaults written
in; `pull --json` prints `{path, case}`. A flag that is another verb's is refused with **exit 2**,
before anything travels.

---

# Running it

## `sessions`

```
pinecall sessions [call] [--agent <slug>] [--limit <1-100>] [--json]
pinecall sessions log <call> [--after <seq>] [--limit <n>] [--types <a.b,c.d>] [--json]
```

```console
$ pinecall sessions --limit 3
clinica-norte · 3 calls

● call_314b0306e2a64daba6b6dbab129540c0  web inbound     16m 27s  live                    —
  call_df5aaa81ac7142f5a2c6f9b77033d23e  web inbound         31s  caller_hung_up    $0.0000  Clínica Norte, good morning…
  call_29d7c7b6cdd643de9c659984a0125c8c  web inbound          3s  caller_hung_up    $0.0205  Perfect. On Thursday we have…
```

With a call id (`sessions <call>`): that call's **outcome**, how long it ran and why it ended, what it cost in US dollars with a
line per priced row under it (the model, the ears, the voice, the memory model at hang-up, each
phone leg in minutes begun) and a line for anything the platform has no rate for, and the **score**,
one line per judge with the question it answered and its own reasoning when it did not hold. The judging happens at hang-up, in the gateway; this verb reads it back and runs
nothing. A call still running says so instead of reporting itself unjudged, and an id this gateway
has no log for is refused by name: it does not print a summary of nothing.

```console
$ pinecall sessions call_5b1f0e9d2c7a4e8f9a1b3c5d7e9f1a2b
call_5b1f0e9d2c7a4e8f9a1b3c5d7e9f1a2b

  outcome   Understood, Ana. Your Thursday appointment at ten with Dr. Vidal stands for now.
  ended     caller_hung_up · 1m 24s · 4 turns
  cost      $0.0505
            api.anthropic.com claude-haiku-5-5           17,621 input_tokens       $0.0018
            api.anthropic.com claude-haiku-5-5           312 output_tokens         $0.0002
            Cartesia sonic-3                             623 characters            $0.0312
            Deepgram flux-general-multi                  80.6 audio_seconds        $0.0105
            twilio twilio-inbound/+1                     2 minutes                 $0.0068
```

`sessions log <call>` is the call's log as the runtime keeps it, an entry a line: its seq, its time
in UTC, its type, and what it says — the turns, each tool call with its arguments and what it
answered or why it was refused, the agent's states, and the rest (metrics, cost, the verdicts) as
their data, cut at 160 characters; a search's `docs.sources` is its query and where each chunk came from
(`"do you open on saturdays" → library-d/hours.md › Saturdays 0.91 · …`), the excerpts in `--json`. A page reads 200 entries (`--limit`, 1 to 500), and while
there is more after it, it ends with the line that reads on (`--after <seq>`): the last seq the
gateway read, so `--types turn.user,tool.call,tool.result`, which keeps only those, never ends the
reading early — a page it narrowed to a few entries, or to none, still says where to go on (`<call> · nothing
of these types in this page, after seq 40; the log goes on`, then the `more:` line); `nothing kept after seq <n>`
is the end of a sealed log.
`--json` prints the page whole, `{call, entries, next, live}`, as the MCP's `call` tool answers
it. What the agent declared `pii` is in the log as `***`, and so it is here: the tool's argument
and the same value wherever the agent wrote it down — the state that took it, what a tool answered,
a line it logged. What was said (`turn.user`, `turn.agent`) is not touched.

```console
$ pinecall sessions log call_5b1f0e9d2c7a4e8f9a1b3c5d7e9f1a2b --after 40 --types turn.user,turn.agent,tool.call,tool.result,agent.state
    41  09:14:02.310  turn.user    Thursday at ten, if Dr. Vidal has it.
    42  09:14:02.311  agent.state  thinking
    44  09:14:02.902  tool.call    free_slots(day=2026-10-15, doctor=vidal)
    45  09:14:03.120  tool.result  free_slots → {"slots":["10:00","11:30"]}
    47  09:14:03.840  turn.agent   Dr. Vidal has ten o'clock free on Thursday. Shall I book it?
    48  09:14:05.002  agent.state  listening
```

A call id the gateway has no log for is refused by name, as `sessions <call>` refuses it; no call, a `--limit`
outside 1 to 500 or an `--after` that is not a seq is refused here with **exit 2**.

## `agent`

```
pinecall agent [--agent <slug>] [--json]
pinecall agent list · stop <app>
pinecall agent set [--voice x] [--tts x] [--tts-model x] [--stt x] [--llm x] [--temperature n] [--language en|es|pt-BR…]
                   [--llm-builds Class] [--llm-option key=value …] [--stt-builds Class] [--stt-option key=value …]
                   [--realtime vendor/model] [--realtime-option key=value …]
                   [--tts-builds Class] [--tts-option key=value …]
                   [--judge x] [--judge-builds Class] [--judge-option key=value …]
                   [--greeting '…' | --greeting improvise[:'…']] [--greeting-interruptible on|off]
                   [--hangup '…' | --hangup any] [--end-of-turn stt|livekit|smart-turn] [--endpointing-ms n] [--min-interruption-words n]
                   [--eot-threshold 0.5-0.9] [--eager-eot-threshold 0.3-0.9] [--record on|off]
                   [--max-duration 1-60|off]
                   [--remember '…' …] [--forget '…' …] [--team] [--note '…']
pinecall agent knowledge [--team] · knowledge edit [--team] [--note '…']
pinecall agent clear <voice|tts|tts-model|stt|end-of-turn|llm|temperature|llm-builds|llm-options|realtime|realtime-options|stt-builds|stt-options|tts-builds|tts-options
                      |judge|judge-builds|judge-options|language|greeting|hangup|turn|memory|record|max-duration|knowledge|bases …> [--team]
pinecall agent clear --all [--team]
pinecall agent history [--team] · diff [--against team|production] [--team] · rollback <version> [--team]
pinecall agent pull [--team] · push <file> [--team]
                                        … and any of them with --prod, in production
```

A version says what moved, so a write that changes nothing writes none: `set` with no field, or
with the values the corner holds, and `clear` of a field your corner does not set are refused with
exit 2 before anything travels. **A write puts only what it moved in your corner**: the gateway
builds a call field by field from the nearest corner that sets each, so the fields you never
touched keep following the team's. `clear` takes fields out of your corner, so the team's hold
again for them; a whole corner is `clear --all`, never a `clear` that forgot to name a field. A field the class declares is refused by `clear` as it is by `set`, with the same `409` naming the class.

```console
$ pinecall agent
clinica-norte · sandbox

                yours           team                        production
  voice         class           class                       class
  tts           —               —                           —
  tts model     —               —                           —
  stt           —               deepgram                    deepgram
  llm           —               anthropic/claude-haiku-5-5  anthropic/claude-haiku-5-5
  language      —               es                          es
  greeting      —               "Thanks for calling Clíni…  "Thanks for calling Clíni…
  hangup        —               when the person has what…   when the person has what…
  turn          —               —                           —
  memory        —               remember 4 · forget 1       remember 4 · forget 1
  record        —               —                           keeps the audio
  knowledge     —               2,140 chars                 2,140 chars
  bases         —               clinica-norte (k 4)         clinica-norte (k 4)

  yours: v3 · m_ana · 2026-09-19 14:32 · "flat on the phone" · team: v11 · m_bruno · 2026-09-18 10:04 · production: v11 · m_ana · 2026-09-12 …
```

**What an agent runs on is its settings', unless its class declares it** — per environment, per
corner, a version a row (the runtime's `docs/protocol/settings-api.md`). The class declares the
contract: its tools, its state, its `render()`. The language, the voice, the models, the opening,
how a call ends, how a turn is cut, what is remembered, what is known by heart and which bases are
searched are **settings**, kept by the gateway and laid over the class at the one place every
session is built. A class may declare any of them itself (`@voice`, `@llm`, `@stt` and its static
fields; the site's *Settings in the class*), and **what the class declares wins**: the table prints
`class` for that field in every corner — `voice` above — and a `set` or a `clear` that changes it is
refused, nothing saved, in the gateway's sentence: `voice set by the class of clinica-norte: the
class's declaration wins over these settings, so change it there, or take it out of the class to set
it here`. `--tts` and `--tts-model` are the class's `voice`; `--temperature`, `--llm-builds` and
`--llm-option` its `llm`; `--realtime-option` its `realtime` (`@realtime`); `--stt-builds`, `--stt-option` and `--end-of-turn` its `stt`; `--judge-builds` and
`--judge-option` its `judge` (`@judge`). Which fields are fixed is
what the process holding the agent in that environment declared: with none holding it, none is.

**How a call opens and ends is words, or the model's own.** `--greeting '…'` is said as written;
`--greeting improvise` has the model open on its prompt, and `--greeting improvise:'…'` with an
instruction for the opening. The caller cannot cut the opening short unless
`--greeting-interruptible on`. `--hangup '…'` is when the model may end the call, in your words;
`--hangup any` whenever it judges the call done. `--end-of-turn` is who says the caller's turn is
over: `stt`, the ears themselves (Deepgram Flux; refused for ears that cannot), or `livekit` and
`smart-turn` (Smart Turn v3), a model on the worker that runs on any key. Unset, ears that do not
end the turn themselves run Smart Turn v3 (runtime 0.1.44), so Soniox needs no flag for it.

**A plugin's own class and options are three pairs of flags, one per stage.** `--llm-builds` names a
class of the vendor's LiveKit plugin other than its default, a dot reaching into a module of it
(`responses.LLM`); `--llm-option key=value` passes one keyword argument as the plugin names it, and
repeats — the value read as JSON when it is JSON (`true`, `1000`, `[1,2]`), as text otherwise. The
options a row sets replace the whole list it had; `clear llm-options` takes them out. Each one
replaces Pinecall's option of the same name for the vendor. A set that changes them tries the stage
once before anything is kept, so a class the plugin does not export, or an argument it does not
take, is refused in its own words. **They run only on the org's own key for the vendor**: on a key
Pinecall lends, the set is refused with `llm options and builds run on the org's own openai key, and
this agent's llm would run on the platform's: add yours with pinecall providers add openai, or take them
out` — an option can point a plugin at another server, and a lent key never goes anywhere but the
vendor. `--temperature` is the model's, in the vendor's own range, and runs on any key; a model that takes none (Anthropic's Haiku 5.5 and later refuse it) refuses the set in the vendor's words.

**A voice call can run on a realtime model while a written call keeps the LLM.** `pinecall
providers` lists, per vendor, the models that hear and speak themselves (xAI's `grok-voice-3.0`,
OpenAI's `gpt-realtime`); `--realtime xai/grok-voice-3.0` runs the agent's voice calls — SIP and
WebRTC alike — on that model alone, no ears and its own voice, with the agent's tools and prompt as
on any call, while `--llm` keeps answering its written calls (the chat, WhatsApp). A vendor alone,
`--realtime xai`, is its plugin's own realtime model. `--realtime-option key=value` passes one of its
keyword arguments as the plugin names it (`--realtime-option voice=eve`, Grok's voice); like a
plugin's own options, the realtime model runs on the org's own key for the vendor alone — on a key
Pinecall lends the set is refused with `409 a realtime model runs on the org's own xai key, …`; on a deployment where nobody holds a key for the vendor at all, with `503 xai has no key: the org brought none and the box holds none`. A set
that changes it builds it once before anything is kept, so a model or an option the vendor does not
take is refused in our words. No class is named: the runtime builds the plugin's realtime one. An
`--llm` that names a realtime model is refused, `400 xai/grok-voice-3.0 hears and speaks itself, so it
is the agent's realtime and not its llm: …`. What is said verbatim (the recording notice, a greeting
given as words, a read-back) is said by the realtime model itself when it can say given words —
xAI's Grok can, so the call has one voice, its own; a realtime model that cannot leaves them to the
agent's voice (`--voice`, `--tts`), and the call then has two. `clear realtime` gives the voice calls back to the
ears, the LLM and the voice. The console offers the same models in Configure ▸ Pipeline, under *On voice
calls*.

**The model the agent's calls are judged on is `--judge`**, named as `--llm` is — `vendor/model`, a
vendor, a model, a tier — with `--judge-builds` and `--judge-option` beside it as the `--llm` pair
is. It wins over the org's (`pinecall judging --model`), which wins over Pinecall's. On the org's
own key for the vendor its evals are never billed, and a local model is that vendor's plugin
pointed at your server: `--judge openai/qwen3-32b --judge-option base_url=http://gpu:8000/v1`. The
options run on your own key alone, as every stage's do. `clear judge` goes back to the org's.

**How a turn is decided is four numbers, and two of them are confidences.** `--endpointing-ms` is
the longest silence a caller is left in before the turn is called finished, and
`--min-interruption-words` how many words it takes to stop the agent mid-sentence. The other two
are for a recogniser that decides the end of a turn *itself* — Deepgram Flux, which is the
runtime's own ears: `--eot-threshold` is how sure it must be before it ends one, and
`--eager-eot-threshold` the lower bar at which it says a turn MIGHT be over, which is what lets
the model start on an answer that is thrown away if the caller carries on. Each number is tried on
the ears before it is kept, inside the vendor's own range: Flux takes `--endpointing-ms` as its
end-of-turn timeout, and a value it refuses is refused there, in its words, naming the knobs tried
(`turn endpointing_ms=400`).

**What never takes the floor**, whatever the numbers. While the agent speaks, a turn that only
agrees ("mm-hm", "sí"), or that is all one of the phrases Whisper-family ears write on a breath
("Thank you.", "Thanks for watching"), is dropped before it can interrupt; so is, for a second and
a half after the agent stops, a turn whose words are mostly its own of the last seconds — its
voice heard back from a visitor's speakers. On a web call (the playground, the widget) the
runtime also cancels that echo in the audio, with WebRTC's canceller fed what the agent plays,
before the ears hear it; a phone cancels its own.

The first of those is the knob that decides whether an agent answers half a sentence. Deepgram's
own measurement of its default, 0.7, is that as much as a fifth of the turns it ends were ended
before the person had finished speaking — on a line, an agent that replies to the first half of
"normal cleaning needed, it gets done every couple of months" and runs a tool on half the facts.
`--eot-threshold 0.85 --eager-eot-threshold 0.4` is Deepgram's own pairing for a line that must
not cut anybody off: the turn is committed only when Flux is sure, and the latency that would
cost is bought back by the eager bar. The eager one may never sit above the other, and a set that
would is refused before it is written.

**`--record on|off` says whether this agent's calls keep their audio**, and it is typed rather
than being a bare flag because the answer worth being able to give is no. A corner that sets it
decides for the copies built there; a corner that says nothing falls through to the one below, and
an agent nobody has told keeps its audio. What is kept is the whole room — the caller, the agent,
the hold music, and a supervisor who took the line — served back by the console's session screen
and by `pinecall sessions`. `pinecall agent clear record` gives the answer back to the corner below.

**`--max-duration 1-60|off` is the longest a voice call of this agent runs**, in minutes; unset
anywhere it is ten. A minute before it the agent is told to close and say goodbye, and at it the
call ends after the sentence being said — `timeout` by the `platform` in the call's log. `off` is
no limit. It holds on the phone and on the widget's voice, never on a written conversation, and a
supervisor on the line does not stop the clock. `pinecall agent clear max-duration` gives it back
to the corner below.

**`--language <tag>` is the language the agent's calls are in** — `en`, `es`, `pt-BR` — and what
the voice, the ears and the turn-taking are set to; unset anywhere, each vendor keeps its own
default. It is not a field of the class, and a class that still declares `language` is refused at
load with this verb. The prompt does not follow it: the framework's own rules are English for
every agent, one of them is to answer in the language the caller speaks, and the class's docstring
and `render()` are in whatever language the tenant wrote them. A blank tag is refused with exit 2
and nothing is written; `pinecall agent clear language` takes it out of the corner.

**A model knob takes a tier by its short name.** `--llm haiku` · `sonnet` · `opus` are expanded
here to the model id the provider answers to — the same table `pinecall test --model` reads — so
the corner never holds a name that is a 404 at the vendor. `haiku` is `claude-haiku-5-5`. `--llm <vendor>/<model>`
travels as typed. **A model alone rides the vendor the corner runs now**: `--llm claude-sonnet-5` after
`anthropic/claude-haiku-5-5` is kept as `anthropic/claude-sonnet-5`, so what is stored says it whole;
with no vendor set before, the class's vendor or the deployment's default takes it. **A vendor alone is
refused** (`openai alone names no model: name it, --llm openai/<model>`): a model has no default to think
with, where `--tts <vendor>` and `--stt <vendor>` have one. A word that names no model at all (an empty
one, half a `vendor/model`) is refused with exit 2 and nothing is written. A set a vendor refuses names
what was tried beside the vendor's words: `deepgram refused the ears this sets (endpointing_ms 400): …`.

**Three corners.** In the sandbox your key has a corner of its own: what you `set` is yours, and a
colleague's next call does not hear it — so two developers testing two voices never change each
other's. A corner that set nothing reads the team's (`(team's)` in your column), which is the org's
own corner, written with `--team`. Production has one corner, and **`--prod` writes it directly**:
`pinecall agent set --voice carolina --note "warmer" --prod`, by a person whose production switch
is on — the same change the production console's Settings tab makes. There is no promote between
the corners: what guards production is the goldens in CI before a deploy
([production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md)), and the history after it.

**Versions.** Every `set` that changes something is a new row; nothing is updated, nothing deleted,
and a `set` that changes nothing writes none. A write puts in your corner only the fields it moved,
and travels with the version the corner was read at, so two people saving at once never write over
each other: the second is told `this corner is at v4 now, not the version you read`. `history` prints every version
with who set it, why, and what it changed; `diff` reads this corner against the team's or
production's, and `diff --team` the team's corner against production's — what a team runs before and
after the push that makes them equal; `rollback <n>` brings one back as the next version — `rollback <n> --prod` is how a
production change that went wrong is undone, in one line.

**What is running, and where.** `list` prints every process holding the org's agents in the environment
asked — one line an app socket: its id, the agents it holds, whose corner, the machine and address
it connected from, the SDK, and since when:

```console
$ pinecall agent list --prod
app_7  clinica-norte  the org's · web-1 (34.68.177.78) · pinecall/0.5.1 · since 2026-09-19 14:02
```

`stop <app>` closes that socket with the `stopped` code (`POST /v1/apps/{app}/stop`, a key with
`app`): the process prints `stopped by <name>` and exits instead of dialling back, and its agents
are free. A supervisor that restarts whatever exits — systemd's `Restart=always`, pm2 — starts it
again, so a process kept that way is stopped where it is supervised. An app on the SDK hears it on
`pc.onStopped(why => …)`. The console's Agents screen has the same list, its Processes card, with a Stop per row.

**Git, for whoever wants it.** `pinecall agent pull > pinecall/clinica-norte.json` writes the corner's
own row as a file — the fields it sets, not what it reads from the team's; `pinecall agent push pinecall/clinica-norte.json --team` sends it back as the next
version, with no version check — it is what CI applies, and `push … --prod` is what a release
applies to production. A corner that set nothing has nothing to pull: `pull` says so on stderr,
prints nothing and exits 1, so `pull > file` in a script fails rather than keeping an empty file. A
`push` of what the corner already holds writes nothing and exits 2.

### `agent knowledge`

```
pinecall agent knowledge [--team]
pinecall agent knowledge edit [--team] [--note '…']
```

**What the agent knows by heart** — the business as the org describes it, a page of Markdown:
hours, prices, what needs an authorisation, what to say when asked for the doctor's mobile. It
is one field of the settings, versioned like the rest, and the runtime reads it **whole** into
the prompt's static `knowledge` block on every call — so it is read once and cached, and never
searched. Alone, the verb prints the corner's text; `edit` opens it in `$VISUAL` or `$EDITOR`,
the way `git commit` does (`$VISUAL` wins over `$EDITOR`), and what you leave is the next version. An unchanged file writes
nothing; an empty one takes the field out. It needs a terminal: piped, it is refused with exit 2
rather than left waiting on an editor nobody can type at. The console's Configure ▸ Knowledge is the same
textarea, and a **supervisor's or a manager's key opens it** (`words`) — the person who knows
the prices changes them, without a developer and without a deploy.

```console
$ pinecall agent knowledge
clinica-norte knows nothing by heart in your corner: `pinecall agent knowledge edit` writes it
$ EDITOR=vim pinecall agent knowledge edit --team --note "prices for 2027"
clinica-norte · knowledge 2,140 chars · the team's corner v12
```

It is not the RAG. The documents a turn *searches* — a catalogue, a policy manual, anything
too long to read whole — are [`pinecall docs`](#docs), attached to the same settings as `bases`.
`pinecall agent` prints the two on two rows: `knowledge` as a size, `bases` by name.

## `kill`

```
pinecall kill [agent]                    … and with --prod, in production
```

An admin's verb: the agent let go by **every** app that holds it in the environment, whoever's
process it is — a colleague's `pinecall start`, a deploy, the org's own server. Each app is sent an
`error` coded `killed` on that agent (`POST /v1/agents/{slug}/kill`, a key that opens both `team`
and `app`): a `pinecall start` holding it prints `<agent>  ✗ <agent> was killed by <name>`, and every
app keeps answering for its other agents and does not declare this one again when its socket comes
back. A `pinecall start` is two apps — the agent's process and the CLI's own socket beside it, which
answers the console — so one kill lets go of both, and the process is the one that prints. The
agent's live calls move as on a drain, to another holder or parked. From that moment it is in no
`agent list`, no console and no playground.

Nothing is erased: its settings and their versions, its calls and their logs stay, and an app that
declares it again — a `pinecall start` restarted, a save that reloads the class — holds it again.
Without `agent`, the agent beside the class; from any folder, the slug named. A key that is not an
admin's is refused with exit 2; an agent no app holds in the env is the gateway's 404, exit 2.

```console
$ pinecall kill front-desk
killed front-desk in sandbox: 2 apps let go of it (app_7, app_8) and kept their other agents — its settings and calls stay, and an app that declares it again holds it again
```

## `lexicon`

```
pinecall lexicon [--agent <slug>] [--json]
pinecall lexicon add <word> --say '…' [--agent <slug>] [--team] [--note '…']
pinecall lexicon hear <word> [<word> …] [--agent <slug>] [--team] [--note '…']
pinecall lexicon rm <word> [<word> …] [--agent <slug>] [--team]
pinecall lexicon history [--agent <slug>] [--team]
                                        … and any of them with --prod, in production
```

A write that changes nothing writes no version: `rm` of a word the lexicon has not is refused by
name, with exit 2, before anything travels.

```console
$ pinecall lexicon add DKV --say "de ka uve"
lexicon · sandbox · your corner
  said     DKV → "de ka uve"
  heard    —
$ pinecall lexicon hear "Vidal Ferrán"
lexicon · sandbox · your corner
  said     DKV → "de ka uve"
  heard    Vidal Ferrán
$ pinecall lexicon history
lexicon · sandbox · corner m_berna_default
  v3 · m_berna_default · 2026-10-09 12:18   said 1 · heard 1
```

An agent's words: its `says` and `hears`, which the class never sets. The agent is the one of
this directory, or the one `--agent` names by its slug, as [`agent`](#agent) names it. Whole and
versioned like the settings, per corner, with the same `--team` and the same refusal when the
corner moved. A **supervisor's or a manager's key opens it** (`words`): the person who hears a word
said wrong forty times a day fixes it, without a developer and without a deploy — with `--prod`, in
production, while their switch is on; the agent's Lexicon screen in the console is the
same edit.
`history` and a word put back are the undo.

A word the voice is told to say another way is still the word written everywhere else: the
transcript, the console and the judges read `Pinecall`, never "pain-col".


`pinecall memory policy [--agent <slug>] [--remember '…' …] [--forget '…' …] [--team] [--note '…']` is the memory field of the
same settings, on its own for the person whose job it is: what the agent keeps about a caller and
what it never does.

## `pipeline`

```
pinecall pipeline [--agent <slug>] [--json]
```

```console
$ pinecall pipeline
clinica-norte · 9 calls

  hears     soniox · es
  decides   anthropic · claude-haiku-5-5
  speaks    elevenlabs · EXAVITQu4vr4xnSDxMaL · es

  greeting  "Clínica Norte, good morning. How can I help you?"

  transcription_delay 0.39s · end_of_turn_delay 0.41s · llm_node_ttft 0.86s · e2e_latency 2.36s
```

The three legs as the **next** call would be built. It reads and nothing else: the six knobs are fields of the settings now, and
`pinecall agent set` sets them with the rest — a model knob reads four ways there,
`--llm anthropic/claude-haiku-5-5`, `--llm cartesia` (a vendor, its own model), `--llm
claude-haiku-5-5` (a model, the vendor in use), and `--llm haiku` (a tier, expanded to the id its
provider answers to, exactly as `pinecall test --model haiku` expands it). `pinecall pipeline set`
and `clear` say so and exit 2. `pinecall providers` lists every vendor a stage may be moved onto.

### `pipeline melody`

```
pinecall pipeline melody [show] [--agent <slug>]
pinecall pipeline melody upload <file> [--agent <slug>]
pinecall pipeline melody default | off [--agent <slug>]
pinecall pipeline melody after <seconds | default> [--agent <slug>]
```

```console
$ pinecall pipeline melody
plays   the runtime's melody
after   2.5 s of the agent's quiet
$ pinecall pipeline melody upload espera.mp3
plays   espera.mp3 · 41.2 s, looped
after   2.5 s of the agent's quiet
$ pinecall pipeline melody after 1.5
plays   espera.mp3 · 41.2 s, looped
after   1.5 s of the agent's quiet
```

What a caller hears while a tool runs, and while the model has not said its first word. It starts
once the agent has been quiet for the wait, so a tool or a model that answers inside it plays
nothing, and it stops at the answer. It plays looped under the agent's voice, on the phone and on
the web alike, from the next call; a written call plays none.

`default` is the runtime's own melody, and what an agent nobody chose for plays. `off` is silence.
`upload` sends a wav, an mp3, an ogg, a flac or an m4a, up to 20 MB and five minutes, which the
gateway converts once; a file it cannot read is refused in a sentence. `after` sets the wait in
seconds, from 0 to 30, and `after default` gives back the runtime's 2.5. Choosing what plays keeps
the wait, and setting the wait keeps what plays. There is one choice per agent per environment,
whoever holds the agent: `--prod` sets production's. The console's Pipeline screen shows the same.

## `supervise`

```
pinecall supervise <call>
```

```console
$ pinecall supervise call_daab0b5d567c49968adc52e8d44c248c
call_daab0b5d567c49968adc52e8d44c248c · the audio of a live call is the console, which has a room — `pinecall start` prints its URL; this is the transcript and the desk
> s Hello from the desk, I am taking over for a moment.
> w
not a move. w · s · t · x · e · q
> q
```

The call's transcript as it happens, and one line to move on it:

```
w <text>    whisper to the agent — the caller never hears it
s <text>    say it to the caller, in the agent's voice, verbatim
t           take the line: the agent stops speaking and you are on it
x           give it back
e [reason]  end the call
q           leave the desk; the call goes on
```

Every move lands in the caller's own log as its own `supervisor.*` entry with a seq, so what a
human did to a call is read the same way as what the agent did. The **audio** of a live call is
the call's page in the console (Calls), which has a room; this is the transcript and the desk.

A desk opens on a call that is **happening**: one that has ended, and an id this gateway has no
log for, are refused before the prompt — what a finished call was is `pinecall sessions <call>`.

An assistant has the same desk as the MCP's `supervise` tool ([Supervising a live call](mcp/supervising.md)).

It takes its moves from a **pipe** too, one per line, which is how a script moves a call:
`printf 't\ns Putting you through to the front desk.\nq\n' | pinecall supervise <call>`. Through a pipe there is
no prompt drawn, and the desk leaves when the lines run out.

## `numbers`

```
pinecall numbers list
pinecall numbers available [--account <id>]
pinecall numbers import <+34…> --agent <slug> [--account <id>] [--channel phone|whatsapp] [--dry-run]
pinecall numbers buy --country <XX> [--area <digits>] --agent <slug> [--channel phone|whatsapp] [--dry-run]
pinecall numbers drop <+34…>
```

**Adding a number to the org from a terminal is `numbers import`**: the number is one an account of
the org owns, and the account itself is kept first with [`carriers add`](#carriers) when the org
does not hold it yet. A Twilio number reaching an agent is these two lines, and nothing else:

```console
$ pinecall carriers add twilio --account-sid AC0123… --user SK4567…   # once, the secret on stdin
$ pinecall numbers import +34910000000 --agent clinica-norte          # the number, to the agent
$ pinecall numbers import +34910000000 --agent clinica-norte --move   # off the trunk it is on now, then here
```

**An org with several accounts names the one that owns the number**, with `--account` and the id
[`carriers list`](#carriers) prints. Without it the gateway cannot choose and answers `409 the org has
2 carrier accounts (AC0123…, AC9876…): name one of them`; the verb prints that and the flag to add.

```console
$ pinecall numbers import +34910000001 --agent clinica-norte --account AC9876…
```

**Which numbers there are to import is `numbers available`** (`GET /v1/numbers/available`): every
number the org's Twilio accounts own, every page of Twilio's, one per line with its name at the
carrier and its account, and `routed here`, `held by another org` or `not routed here` for the environment asked.
`--account` asks one account of several. It is per environment: a number production routes reads `not routed
here` in the sandbox, so look with `--prod` before importing one there.

**`not routed here` is not `free`.** The list knows what **this org** routes in this environment and which
numbers **another org of this deployment** routes (`held by another org`: not importable here until that
org lets it go), and nothing about a number held on another trunk of the same Twilio account: that one is
found out at import, as a `409` naming the trunk and asking for `move` (`numbers import … --move` takes it
off there first). `numbers import <number> --agent <slug>
--dry-run` is the check, and a `409` is a number to leave alone. A SIP peer owns what it owns and
lists nothing; its import takes the number as typed.

```console
$ pinecall numbers available --prod
+13158182774 · (315) 818-2774 · AC5f7c… · routed here
+16814413619 · (681) 441-3619 · AC5f7c… · not routed here
```

A number is **one environment's** and reaches one agent: it is imported where it answers, and `list`
shows that environment's — the sandbox's, or production's with `--prod`. No verb here moves a number
between the two; the console's Numbers screen does (`PUT /v1/numbers/{number}/env`, which re-routes the
carrier's trunk), because a number is a route in one environment's table and a carrier call that matched
two would be refused.

`import` takes a number the org's carrier account already owns and points it here: the carrier's
trunk, the SFU's trunk, the route — `--dry-run` prints those steps and writes nothing, which is
what you read before letting the gateway touch a carrier account. `drop` forgets the route and
takes the number off the SFU trunk; the carrier account keeps it, so nobody is un-bought by a typo.
Whose corner a ring lands in, once an environment is answering it, is [`line`](#line).

**An org with no number of its own buys one with `numbers buy`** (`POST /v1/numbers/buy`): the
deployment buys a local voice number in `--country` (two letters) and, when given, `--area` on **its
own** Twilio account — never one of the org's — and points it at the agent, in the environment the
verb acts in. `--dry-run` names the number it would buy and buys nothing; read it first. A bought
number counts against the org's `numbers` limit in that environment, and an imported one never does;
the verb ends with the count:

```console
$ pinecall numbers buy --country US --area 415 --agent clinica-norte --dry-run --prod
  Twilio: buy +14155550000: to do
  …
  bought numbers in this env: 0 of 2
  nothing bought: drop --dry-run to buy +34915550000
```

A deployment that holds no Twilio account of its own sells none: `503`. A country Twilio has no local
voice number for is `404`, and a limit reached is `429` with the count. `list` marks a bought number
`bought here`, and an imported one with the account it lives in.

## `carriers`

```
pinecall carriers list
pinecall carriers show [<account>]
pinecall carriers add twilio --account-sid <AC…> --user <SK…> [--label <name>]
pinecall carriers add sip --username <user> --address <ip or network>… [--outbound-host <host>]
                      [--outbound-transport auto|udp|tcp|tls] [--outbound-username <user>] [--label <name>]
pinecall carriers add whatsapp --phone-number-id <id> [--label <name>]
pinecall carriers drop [<account>]
```

A carrier account is **where the org's numbers live**, and the org holds as many as it has: a
Twilio account, a SIP peer (its own PBX, or a carrier with no API here), a WhatsApp number at
Meta. An account is the org's, one for both environments; a number it owns is routed to an agent with
[`numbers import`](#numbers), in the environment it should answer in. So bringing a Twilio number to an
agent is two verbs:

```console
$ pinecall carriers add twilio --account-sid AC0123… --user SK4567… --label Clínica
Twilio secret (the API key's, or the auth token):
kept: AC0123… · twilio · Clínica
  route one of its numbers: `pinecall numbers import <+34…> --agent <slug>`
$ pinecall numbers import +34910000000 --agent clinica-norte
```

**Every secret is read on stdin, never from the command line**, where `ps` and the shell's history
would keep it: typed with nothing echoed on a terminal, or piped one per line —
`printf '%s\n' "$TWILIO_SECRET" | pinecall carriers add twilio …`. A SIP peer reads its password,
and its outbound password on a second line when `--outbound-username` is given. Nothing is printed
back: the gateway seals each secret under the platform's vault key and answers the account by its id.

- **Twilio.** `--user` is an API key SID (make one at Twilio → Account → API keys, and revoke it
  there any time) or the account SID again, with the auth token as the secret. The pair is tried
  against Twilio before anything is kept, so a pair Twilio refuses is `Twilio refused these
  credentials` and exit 2. With a Twilio account the platform finds the trunk that points at it, or
  makes one, when a number is imported.
- **A SIP peer.** `--address` is each network it calls from, repeated: an IPv4 address or a network
  no wider than a `/24`, public. Each one **waits for the operator** to approve it before
  5060 opens to it; `show` prints `waiting`, `approved` or `refused` beside each. The four
  `--outbound-*` flags say where the platform dials it; unsaid, the platform dials with the pair it
  registers with.
- **WhatsApp.** `--phone-number-id` is the number's id at Meta, and the access token is the secret.
  Meta is asked for that number with that token before anything is kept, so an id or a token Meta
  does not open is `Meta does not open WhatsApp number <id> with this token: …` and exit 2.

`add` with an account the org already holds **replaces its secret**: that is how a key is rotated.
An account's id is its own: Twilio's account SID, the peer's username, Meta's phone number id.
`list` is every account, oldest first, one line each with its id and how many numbers it routes in
the environment asked — and, when there are several, the reminder that `numbers import` names one
with `--account`; `show` is one, the org's only account or the one named; `drop` forgets one, and with several the id is required. **Its numbers
stay routed** until each is let go with `numbers drop`, so forgetting an account never silences a
line by surprise. The same accounts are the console's **Numbers** screen, *Add a number* —
[the console](https://docs.pinecall.io/guides/console/) — and the REST endpoints are
[phone numbers](https://docs.pinecall.io/concepts/phone-numbers/), "Accounts and numbers".

## `limits`

```
pinecall limits [--prod]
```

**What the org may use in this environment, and what it used.** Every limit the deployment gave the
org (`GET /v1/limits`) as what is used of it; a limit with no number is no limit, and `0` refuses
everything. Minutes, messages, LLM tokens, evals, simulations and the budget (the dollars its calls
cost, sandbox and production together) are this month's and start again on the first (UTC); calls at
once, agents, seats, bought numbers, hosted apps, memory facts and knowledge chunks are what the org
holds now. A refusal past a limit is a `429` naming it, and the agent's log gets `credits.exhausted`,
whichever limit it was.

The last line is **whose keys a call runs on**: the vendors the org brought keys for
([`providers add`](#providers)), and the ones the runtime lends it. A vendor in neither refuses
the call before it starts — bring a key for it.

```console
$ pinecall limits
sandbox
  minutes           12 of 30 · starts again 1 Nov
  messages          41, no limit
  LLM tokens        18210, no limit
  evals             40 of 100 · starts again 1 Nov
  simulations       3, no limit
  budget            $1.20, no limit
  calls at once     0 of 1
  agents            1, no limit
  seats             2, no limit
  bought numbers    0 of 0
  hosted apps       0, no limit
  memory facts      14, no limit
  knowledge chunks  226, no limit
  keys              yours: anthropic · lent by the runtime: google, cartesia, deepgram
```

The MCP's `usage` answers the same, keys included.

## `providers`

```
pinecall providers [catalog] [--does llm|stt|tts]   # every vendor this build runs
pinecall providers add <vendor>     # the key on stdin, never on the command line
pinecall providers rm <vendor>
pinecall providers list             # only the ones this org brought
```

```console
$ pinecall providers --does tts
VENDOR        DOES         STANDING
livekit       llm,stt,tts  ready
cartesia      stt,tts      no key
elevenlabs    stt,tts      ready
rime          tts          no key
speechmatics  stt,tts      no plugin
```

With nothing after it: every vendor this build runs — every one LiveKit ships a plugin
for, plus `livekit` itself, which is LiveKit Inference and fronts most of them on the platform's own
project with no vendor key at all. `standing` is the one word for what each is still waiting for:
`ready` is the only one that runs a call, `no plugin` and `no key` are the operator's to fix, and
`its own` is a vendor whose credentials are a chain or a pair and never one key anybody could
bring. Any of these names — or any of its aliases — is what `agent set --stt`, `--llm` and
`--tts` take: the six knobs are the agent's settings, and `pipeline` only reads them back. Under
the table, how many vendors and which the platform runs each job on (`ours: …`), then one line per vendor whose plugin names realtime models — `realtime · xai:
grok-voice-latest, grok-voice-3.0, …` — the models that hear and speak themselves, which
`agent set --realtime xai/grok-voice-3.0` runs the voice calls on.

A key added here is this org's own account with that vendor, and every call of this org runs on it
from the next one. It is tried before it is kept — the vendor is asked one small thing on it, as a
call would ask — and one the vendor turns away is refused in the vendor's words, with nothing kept. A vendor nobody brought runs on the deployment's own key **when the deployment
lends it** to the org — every vendor, some, or none, set by its operator per environment — and is
refused before the call starts when it does not; [`limits`](#limits) prints which. `add` reads the key from
**stdin** — typed with nothing echoed on a terminal, one piped line off one — and never from a
flag: argv is visible in `ps` to every user on the platform, and a key pasted as an argument is a key in
the shell history.

No endpoint a person reads ever answers with a provider key: `list` prints the vendors and nothing
else, not a value, not a prefix, not a fingerprint. The one endpoint that reads a key back is the
**worker's** — `GET /v1/agents/{slug}/provider-keys`, an org's own keys handed to the org's own
process, on that org's key — which is the whole reason the vault exists. A key that was lost is set
again. A runtime with no `PINECALL_VAULT_KEY` cannot keep somebody else's
secret and says so with a 503; the vault, and how to turn it on, is the gateway API's §6.

## `voices`

```
pinecall voices [--tts <vendor>] [--language es] [--country ES]
pinecall voices play <voice> ["the words"] [--tts <vendor>] [--model <model>] [--language es] [--save file.wav]
```

```console
$ pinecall voices --language es --country ES
a7beff01-8f8b-4809-bfe6-e2166e57e0c2  Iria - Thoughtful Communicator  feminine   ES castilian
de38f545-c574-44e8-9b54-a7d6fec1c6b1  Marta - Friendly Guide          feminine   ES castilian
35b2cfc1-e6fb-4d69-a598-c1780612be4a  Darío - Steady Operator         masculine  ES castilian
$ pinecall voices --tts rime
rime lists no voices: its voice is the vendor's own id, set as it is — these list theirs: cartesia, elevenlabs, inworld, nvidia, speechify (--tts <vendor>)
$ pinecall voices play de38f545-c574-44e8-9b54-a7d6fec1c6b1 "Hi, this is Clínica Norte's assistant." --language en
de38f545-c574-44e8-9b54-a7d6fec1c6b1 · first audio 578 ms · whole sentence 915 ms · afplay
```

With nothing after it: the vendor's voices in that language, one per line — the vendor `--tts` names, else
the one your corner's `tts` runs on, else the runtime's default (`providers` says which), so `no voice matches`
with no `--tts` is that vendor listing none in the language; a vendor whose plugin lists its voices with no
language at all (ElevenLabs) cannot be narrowed by `--language`, and says so — the id the agent's
`voice` setting takes, then the name and, where the vendor says them, the gender and where the
accent is from. The country is the column that matters for Spanish: `ES` is Spain and `MX` is
Mexico, and a language code does not tell them apart; `--country` keeps one. The vendor is `--tts`,
or **the platform's own voice** when none is named — `defaults.tts` of `GET /v1/providers`, what an
agent that names no vendor speaks with. A vendor lists its voices when its livekit plugin does —
ElevenLabs, Inworld, NVIDIA and Speechify — or when the platform's providers row lists them for it, as
data (`listed`, by vendor and language: on `cloud.pinecall.io`, Cartesia's in Spanish and English);
`voices_listed` in the same catalogue says which, and it is what the console's picker reads too. A
vendor listed by neither takes its voice as the id the vendor gives it: `voices` says so, names the
vendors that list theirs, and exits 1 without asking for a list. Any id plays, listed or not.

`play` says the words in that voice through the vendor's own plugin, exactly as a call would build
it (`POST /v1/voices/sample`, the wire's `VoiceSample`), and plays the WAV on this machine with
whichever of `afplay`, `ffplay`, `play`, `aplay` or `pw-play` it finds — a player that fails is
said so, with the file kept and named, and exit 1. With no words the gateway reads one line in the
language, so every client hears the same one. Beside it are the vendor's two numbers: how long
until the first audio — the wait a caller hears after they stop talking — and the whole sentence;
a dash when the gateway sent none. `--save file.wav` keeps the WAV there and plays it from there.
It runs on the org's own key for the vendor when it brought one, and on the platform's otherwise; both
endpoints ask for `pipeline`, the scope that may change the voice. The gateway refuses in one sentence
what the settings endpoint would refuse — a voice its vendor does not have, a vendor this build has no row for, a
model it does not vouch for, more than 400 characters (`422`) — and says `429` past thirty samples
a minute on one key, `503` when nobody has a key for the vendor, `409` when the vendor refused
that key, `502` when it did not answer. The voice it plays is set with `pinecall agent set --tts
cartesia --tts-model sonic-3 --voice <id>`: a model tried with `--model` is kept only when
`--tts-model` names it too.

## `callbacks`

```
pinecall callbacks [--agent <slug>] [--after <cursor>]
```

```console
$ pinecall callbacks
gateway https://cloud.pinecall.io · org clinica · key from your sign-in (/Users/ana/.pinecall/session.json) · sandbox
nobody is waiting for a call back
```

The numbers people left when every seat of the fleet was taken: a phone caller the overflow agent
answered, or a web visitor who left a number at the widget after `POST /v1/tokens` answered `503`.
One line each — when, the agent, the number, the channel, who took it — oldest first, and a
`more: --after <cursor>` line when there is another page. The runtime records them
(`callback.requested`, on the agent's log); dialing back is your app's.

```
gateway https://cloud.pinecall.io · org clinica · key from your sign-in (/Users/ana/.pinecall/session.json) · sandbox
2026-09-11 19:20  clinica-norte  +34600000000  phone  via overflow on call_9f2c…
2026-09-11 19:22  clinica-norte  +34611111111  web    via the widget
```

## `data`

```
pinecall data erase call <call-id> --yes
pinecall data erase contact <number|id> --yes
pinecall data erasures [--json]
pinecall data reads [<call-id|number>] [--json]
pinecall data policy [--retention-days <n> | --keep-all] [--calling-hours <from>-<until> | --any-hours]
                     [--per-number-day <n> | --no-per-number] [--consent-everywhere | --consent-by-law]
                     [--disclosure '…' | --platform-disclosure | --no-disclosure]
                     [--recording-notice | --no-recording-notice] [--json]
pinecall data consent <number> [--give express|written --source '…' [--text '…'] [--evidence '…'] | --opt-out]
pinecall data dnc [list [--after <cursor>] | add <number>… --source '…' | import <file> --source '…']
pinecall data export [--out <file.jsonl>]
```

```console
$ pinecall data reads
2026-10-09 12:15  log        call_92dce20e53d044dcb925c69c13db72f7  by m_berna_default  (sandbox)
2026-10-09 12:12  memory     +34600000001                            by m_berna_default  (sandbox)
$ pinecall data policy
retention:      every sealed call is kept until it is erased
calling hours:  a number is rung at any hour of its day (a +1 number: 8-21)
per number:     no limit of calls to one number a day (a +1 number: 3)
consent:        a +1 number needs a consent on file
$ pinecall data erasures
nothing erased yet
```

What the org keeps in the environment the key acts in (`--prod` for production), and taking it out.

`erase call` takes one ended call: its log, its facts, the memories it taught and its recording,
in one transaction (`DELETE /v1/calls/{call}`); a call still running is refused. `erase contact` is
a person's "delete my data": every call they were on in the environment and every fact kept of them
(`DELETE /v1/contacts/{contact}`), by the number or the id the call carried — the number that called, or
on an outbound call the number called. Neither can be undone,
so both ask for `--yes`. What the law asks the org to keep stays: a consent recorded and a place on
the do-not-call list are the org's records about the number, not facts about the person, and
`data consent <number>` reads them after the erasure as before. The dial ledger keeps the numbers and the time of a call, never what was
said: a carrier's traceback asks for it.

```
$ pinecall data erase contact +14155550142 --yes
2026-09-29 18:02  contact +14155550142  3 call(s), 212 entries, 4 memories, 3 recording(s)  by m_ana
```

`erasures` is the trail (`GET /v1/org/erasures`): what went, when, and who asked — a person, a key,
`retention` for the nightly run, `operator` for an org erased whole. It outlives the org.

`reads` is who read the org's calls (`GET /v1/org/reads`): a person reading a call's log or its
recording at the console or with their key, a server's key reading one (its key id is the reader),
the operator reading one off the platform, and a traceback the operator ran on a number — once an
hour per reader, call and kind, newest first; a call id or a number after it narrows the list to that
one. It is the environment's own, the sandbox's or, with `--prod`, production's. A visitor's page
reading its own call and the fleet serving it write nothing. It is the access log a breach
notification starts from.

`policy` is the org's compliance settings, one row at `GET`·`PUT /v1/org/policy`, read with no flag
and changed a field at a time (the row is read and written back whole, so the other fields stay):
`--retention-days <n>` is how many days a sealed call is kept before the platform's nightly run erases
it, `--keep-all` clears it; `--calling-hours 9-20` the hours of the called number's own day a call
may ring, `--any-hours` clears them; `--per-number-day <n>` how many times one number is rung in 24
hours, `--no-per-number` clears it. A US or Canadian number keeps the US floor — 8 to 21 and three
a day — whatever is set wider; the sandbox and your own verified phone are held to neither.
`--consent-everywhere` asks for a consent on file for a number of any country, `--consent-by-law`
for a `+1` number only (the default).

What a spoken call says before its greeting is the policy's too, said in the agent's voice and
logged as its first `turn.agent`. An outbound call opens with the disclosure: the platform's
sentence in the agent's language by default (*"This is an automated assistant calling on behalf of
Clínica Norte."*, `--platform-disclosure`), your own words (`--disclosure '…'`), or none
(`--no-disclosure`, and then your greeting must say it is an automated assistant). A recorded call,
either direction, then says *"This call may be recorded."*; `--no-recording-notice` turns that off.

```
$ pinecall data policy --retention-days 365 --calling-hours 9-20
retention:      a sealed call is erased 365 day(s) after it started
calling hours:  a number is rung from 9:00 to 20:00 of its own day
per number:     no limit of calls to one number a day (a +1 number: 3)
consent:        a +1 number needs a consent on file
outbound opens: the platform's sentence ("This is an automated assistant calling on behalf of …")
recording:      a recorded call says "This call may be recorded."
set by m_ana
```

`consent <number>` is what stands for a number in the environment — consented, on the do-not-call list,
or nothing on file — and every fact about it, newest first (`GET /v1/org/consents/{number}`).
`--give express|written --source '…'` records a consent, with the `--text` the person agreed to and
an `--evidence` (a URL, a document id); `--opt-out` puts the number on the list. A call to a US or
Canadian number in production needs a consent on file (or one sent with the dial), and a number on
the list is never dialled, whatever consent the dial carries: only a consent recorded here lifts it.

```
$ pinecall data consent +14155550142
+14155550142  on the do-not-call list
  2026-09-29 18:40  opt_out   the caller asked the agent  by agent:front-desk  on call_9f2c…
  2026-09-20 10:02  express   the booking form  by m_ana
```

`dnc` is the list itself (`GET /v1/org/dnc`, a page at a time), `dnc add <number>…` puts numbers on
it, and `dnc import <file>` takes a file of them, one a line — the org's own list, or the scrub of
the National Do Not Call Registry the org ran on its own account (`POST /v1/org/dnc`). Both ask for
`--source`, which the list keeps beside each number.

`export` streams the org's environment whole as JSON Lines (`GET /v1/org/export`): a header, every call
with its facts and its whole log, every memory, every version of every agent's settings and words,
every knowledge document. `--out` writes a file and says so on stderr; without it, stdout, for a
pipe. Recordings are not inlined: `pinecall sessions` names them.

## `login`

```
pinecall login [gateway-url] [--no-open]
```

`login` **prints a link and opens it**. You sign in there — in a browser, where a password belongs,
where the browser autofills it and a password manager holds it — and the page hands this terminal a
key of its **own**: minted for you, labelled as this machine, revoked on its own from the API keys
screen. Nothing types a password into a shell, and the day your org signs in with Google this verb
does not change.

```console
$ pinecall login https://pinecall.miempresa.com
open this to sign in:
https://pinecall.miempresa.com/cli?c=cli_…

waiting…
signed in to https://pinecall.miempresa.com as Ana García · org clinica

what this runtime gives your agents
  ears      openai/deepdml/faster-whisper-large-v3-turbo-ct2   served here
  thinking  openai/nemotron-3.5-lightning:30b-a3b              served here
  voice     cartesia                                           needs a key

a stage that needs a key: pinecall providers add <vendor>
```

**Once per machine and gateway, and every verb runs on it.** The key is proved at `/v1/whoami` and
kept in `~/.pinecall/session.json` with the org it acts in. It chooses no org: you may belong to
many, and each project names its own in its `pinecall.json` ([where the key comes
from](#where-the-gateway-and-the-key-come-from)). Signing in again at a gateway replaces the
sign-in there and drops the keys minted from the old one. After it, the gateway says what it gives
your agents a stage at a time (`GET /v1/providers/advice`): an open model it serves, a vendor it
lends, your org's own key, or one your org must bring; a gateway that does not say is left out.

With no URL it is `https://cloud.pinecall.io`, and it says so above the link, so a person who meant
their own platform sees the assumption before anything is kept. The key opens both environments of
that gateway; the sandbox keeps no password of its own. The word in the link dies in ten minutes
and on first collection; a terminal with no browser, or `--no-open`, prints the same link and you open it from
wherever you are. A runtime on this machine (`pinecall-runtime setup`) signs it in by itself, and a
server has no login at all: it runs on a server's token from the console's API keys screen, kept in
its secrets as `PINECALL_KEY` ([production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md)).

## `whoami`

```
pinecall whoami [--prod]
```

**The one endpoint**: the gateway and the key every verb finds ([above](#where-the-gateway-and-the-key-come-from)),
on one line with the org a project names and where the key came from; under it what the gateway says the key is in the environment
asked — the sandbox, or production with `--prod`: the org (its slug, or its id when the gateway
carries none), the key's id, the environment, the label it was issued under, and whether the key may act
in production — your switch, an admin's always, or a production server token; and under that
which environments the key opens there: a person's key both, the sandbox without `--prod` and production
with it while the switch is on; a server's token the one its prefix names. The exit code is 0
when the gateway said who the key is, and 2 when it refused, in its words, when there is no key, or when
it answers 404 — as every refusal of the gateway is ([exit codes](#exit-codes)). The key itself is
neither printed nor sent anywhere else.

```console
$ pinecall whoami
gateway https://cloud.pinecall.io · org clinica · key from your sign-in (/Users/ana/.pinecall/session.json) · sandbox
  org clinica · key k_4f2a1d9c66b30e17 · sandbox · ana-macbook · production: yes
  a person's key: the sandbox without --prod, production with it
```

## `mcp`

```
pinecall mcp
pinecall mcp install [--list | --remove]
```

```console
$ pinecall mcp install --list
assistants on this machine:
  Claude Code     registered      /Users/you/.claude.json
  Claude Desktop  registered      /Users/you/Library/Application Support/Claude/claude_desktop_config.json
  Codex           registered      /Users/you/.codex/config.toml
  Cursor          not installed   /Users/you/.cursor/mcp.json
```

With nothing after it, the MCP server on stdin and stdout, for an assistant to launch. Its tools
sign this machine in, link a project and write a new one; they act in the sandbox, and in
production when a tool is asked with `prod: true` — the org's switch still decides. An agent its `start` tool holds runs in a
thread of the server itself (a Ruby or Python agent is refused there: run `pinecall start`); the
only process it starts is `pinecall-runtime`, for the `runtime` tool's `up`, `recommend` and
`down`. No answer carries a key. `install` writes `npx -y pinecall@latest mcp` into every assistant installed here, copying
each file to `.bak` first and leaving every other entry and comment as it was; `--list` changes
nothing, `--remove` takes it out. Every tool, and every assistant's file:
[the-mcp.md](the-mcp.md).

---

# What it remembers, and what it knows

## `docs`

```
pinecall docs list
pinecall docs drop <base>
pinecall docs push [dir] [--base <name>] [--language <code>] [--replace] [--agent <name>] [--file agent.tsx]
pinecall docs pull [dir] [--base <name>] [--agent <name>] [--file agent.tsx]
pinecall docs rm <path> [--base <name>] [--agent <slug>]
pinecall docs eval [docs.json] [--base <name>] [--k <n>] [--agent <name>] [--file agent.tsx]
pinecall docs attach <base> [--k <n>] [--mode retrieved|tool] [--min-score <x>] [--agent <slug>] [--team]
pinecall docs detach <base> [--agent <slug>] [--team]
pinecall docs attached
                                        … and any of them with --prod, in production
```

`attach` names a base the env has (`pinecall docs list` lists them): one it has not is refused with
exit 2, naming the `push` that would write it.

**The documents a turn searches** — the RAG, and only that. **The folder is a checkout of the
base.** `push` reads every `*.md` under the directory — the agent's own `agents/<name>/docs/` when
none is named, which `new` and `generate agent` write with a README and the repository tracks like
the rest of the agent's folder — and writes them into `PUT /v1/knowledge/<base>` **by path**: a file
the folder has is written, cut and embedded again only where it changed; a file the base has and the
folder has not is kept, so a document added in the console's Knowledge ▸ Docs survives the next push.
`--replace` makes the base the folder, as a push did before: what the folder has not is dropped. The
`README.md` at the folder's root is never sent — it describes the folder, not the business, and the
agent template ships one — and the push's line says so when one stayed behind. `pull` brings the
base back into the folder, one line per file: `written`, `unchanged`, or a file of the folder the
base has not, `not in the base (kept)` and never deleted — so what a manager wrote in the console
reaches the repository with the next commit. `rm <path>` takes one file out of the base, by the path
a push sent it under; a path the base has not is the gateway's 404, said as it is. At a project's root
with nothing typed, `push` and `eval` act on every agent that has documents or a golden, and name the
rest. The base is the agent's slug unless `--base` says otherwise. What the agent knows *by heart*
is not a document and is never pushed: it is [`pinecall agent knowledge`](#agent-knowledge).

**The base you push is the environment's the command runs in.** A push from a laptop writes the sandbox
base — what your own `pinecall start` answers from — and never the one the telephone answers from.
Production's is the same push with `--prod`, made in the release step of a deploy like a migration,
by the server's token or by a person whose switch is on ([production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md)). `list`
and `drop` read the same environment.

```console
$ pinecall docs push
clinica-norte · 7 files · 1 kept · 41 chunks · spanish · 812 ms      # base · files sent · base's others left as they were · chunks of the files sent · stemmed in · took
$ pinecall docs pull
agents/clinica-norte/docs/horarios.md  unchanged
agents/clinica-norte/docs/seguros.md   written
agents/clinica-norte/docs/borrador.md  not in the base (kept)
$ pinecall docs rm precios-2024.md
precios-2024.md gone from clinica-norte
```

`· 1 kept` is the file of the base the push did not touch — the one the console added — and
`· README.md skipped` closes the line when the folder's README stayed behind. The line counts what the push
sent: its files and the chunks they were cut into, so with a file kept it adds up to less than `docs list`,
which counts the whole base.

**The questions a section answers travel with it.** An HTML comment is never a chunk — a note to the
author stays the author's — but one is read: `<!-- asks … -->` under a heading, the questions that
section answers, one a line, invisible wherever the file is rendered. Each is indexed beside the
section in a caller's own words and counts as a chunk of the quota
([knowledge-bases.md](https://docs.pinecall.io/concepts/knowledge-bases/)).

**The base speaks a language.** Its words are stemmed with that language's rules, so a caller's
*sábados* finds *sábado* and an English reader's *supervise* finds *supervising*. `--language` says it
(`en`, `es`, `pt`, `fr`, `de`, `it`, `nl`, or the configuration's name); left out, the gateway counts
it from the files' own function words, and a folder that says none clearly — tables, names — is
indexed with no stemming at all: the push's line says so and how to say one (`no language counted
from the files, so no stemming: say it with --language <code>`). `list` shows each base's.

**`attach` says an agent reads a base.** It is one field of the agent's settings (`bases`),
written as the next version of the corner — yours, the team's with `--team`, production's with
`--prod` — with how a turn reads it: `--k` chunks, `--mode` (`retrieved`: the platform searches
before the turn and hands the model what it found; `tool`: the model decides when to search),
`--min-score`. A base attached twice is replaced, not doubled. `detach` takes it out, and taking
the last one out leaves an empty list rather than no field at all: this corner reads no base, and
the agent does not fall back to the team's. `attached` prints which agents read which base in the
environment asked.

```console
$ pinecall docs attach clinica-norte --k 4
clinica-norte · clinica-norte attached · your corner v4
$ pinecall docs attached
clinica-norte · read by clinica-norte
```

**Several bases are one search, not several.** An agent that reads three collections has them
searched together on every turn — one query, one ranking over all of them — so a collection with
nothing to say about the question takes none of the turn's chunks. `--k` is how many chunks the
turn is handed (the most generous of the attachments), and `--min-score` is read against the base
that set it. The log's `docs.sources` names the base each chunk came from.

The class reaches the base from inside a tool, and nowhere else: `await
this.knowledge.search("horarios", { k: 3 })` asks the gateway for the best chunks of the bases the
environment attached, for these words ([writing-an-agent.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/writing-an-agent.md)). Which base is the
environment's to say, so a class that searches and registers in an environment where nothing is attached is
refused at registration, the agent's process printing the gateway's code before its words: `bad_shape: clinica-norte searches its bases, and none is attached to it in sandbox:
pinecall docs attach <base> --agent clinica-norte`. A base attached and never pushed is refused
the same way, naming `pinecall docs push`.

`eval` asks the base every question of a golden — `agents/<name>/test/goldens/docs.json`, a JSON list of
`{asks, expects}`, where `expects` is the heading path the answer should carry, or a list of paths
any of which does — and prints
`recall@k` and `nDCG@10`, computed by code with **no model in the loop**, plus every question it
missed and what came back instead. **With no `--k` it asks with the k this agent reads that base
with** — the attachment's, in this corner — because a golden asks what a turn gets: a base
attached with `--k 4` measured at the endpoint's default of eight answers a question nobody's calls
are asking. Exits 1 when anything missed, so CI can hold a base to it. A
golden is fixed and the index is the variable: never soften a question so a change can pass.

## `memory`

```
pinecall memory <contact>
pinecall memory forget <contact> [--yes]
pinecall memory policy [--agent <slug>] [--remember '…' …] [--forget '…' …] [--team] [--note '…']
pinecall memory eval [golden.json] [--k <n>] [--agent <name>] [--file agent.tsx]
```

```console
$ pinecall memory policy --team --remember alergias --remember "médico habitual" --forget pagos
clinica-norte · sandbox
  yours       v9 · nothing remembered
  team        v5
    remember  alergias
    remember  médico habitual
    forget    pagos
  production  v3 · nothing remembered
$ pinecall memory +34600000001
nothing remembered about +34600000001
```

Everything memory kept about one contact — the caller's number, or the id the app named — with the
current facts first and the ones a later call superseded dimmed, with the date they stopped
holding. `forget` erases all of it, the right to be forgotten; on a terminal it asks once, and
prints how many facts went. With nobody at a terminal — a script, CI — it erases only with
`--yes`, and exits 2 without it (`data erase` asks for `--yes` even at a terminal); `--yes` also skips the question.

`policy` alone prints what the agent remembers and forgets, corner by corner; with flags it writes
yours (`--team` the team's). Each category is its own flag — `--remember allergies --remember
'preferred name'` — and the policy written replaces the one before it. To take yours out so the
team's holds again: `pinecall agent clear memory`.

`eval` holds **recall** to a golden of `{holds, asks, expects}` — `agents/<name>/test/goldens/memory.json`:
each question brings its own facts, so no
contact of yours is read or written — they go to a scratch contact and are deleted again.

## `remember`

```
pinecall remember [paths] [--agent <name>] [--file agent.tsx] [--grep x] [--json]
```

```console
$ pinecall remember
clinica-norte · anthropic/claude-haiku-5-5 · 3 cases · 3 held · 5445 ms
  ✓ anota la alergia y nunca la tarjeta
  ✓ la mañana sustituye a la tarde, no convive con ella
  ✓ ni guarda un permiso ni borra lo que nadie desmintió
```

The cases are `agents/<name>/test/memory/`, one file per call written down.

The other half of memory: the **write** side. A case is one call written down — both speakers,
because nothing is re-run — the facts memory already holds, and what must come of it: which
categories got a fact, which never did, which values must not survive in any fact's text, and
which held facts the call contradicted.

Each case costs ONE model call, the very one a hang-up makes, run by the gateway against the
categories the agent's holder declared — your `pinecall start`, a colleague's, production's with
`--prod`; nothing is started here. Every answer is judged by code: a category is the class's own word, a
value is a literal, a supersession is an id — never one sentence compared to another, because two
ways of writing one fact are one fact. A fact the model files under a word the policy does not have is
written as `other`, and a case that expects the policy's word breaks, the report showing `kept` the
`add · other · …` it got.

---

## `deploy`

```console
~/acme-support $ pinecall deploy up --prod --note "reads the order's eta back"
acme-support: release 4 sent · 38 KB · 3b507661b052
acme-support: the box installs and starts it; the release before keeps answering meanwhile
acme-support: release 4 is live
```

The platform runs the project for you: the same `pinecall start` you would run on a server
([production.md](https://github.com/pinecall/pinecall/blob/main/sdk/typescript/docs/production.md), "(c)"), in a container of its own on Pinecall's machines, with
nothing to keep up. **The whole guide — preparing a project, secrets, limits, CI, every refusal —
is [Deploy to Pinecall](https://docs.pinecall.io/guides/deploy/)**; what follows is the verb's reference. What it takes:

- **The project, packed.** Every file the project's `.gitignore` files leave in — each read where it
  sits, with no git asked, so a folder that is no checkout packs the same — and never
  `node_modules`, `.venv`, `__pycache__`, `.git`, `dist` or any `.env`: the key in `.env` is yours,
  and the app gets one of its own. 10 MB packed at most, 100 MB unpacked, 5 000 files; a link or a
  path out of the folder is refused.
- **Agents in TypeScript or in Python, one of the two.** A Ruby agent, or a project with agents in
  two languages, is refused before anything is sent.
- **TypeScript: a lockfile, and `@pinecall/agents` in the dependencies.** The platform installs from
  `pnpm-lock.yaml` (`pnpm install --frozen-lockfile --prod`), else `package-lock.json` (`npm ci`),
  else `package.json`; the version of `@pinecall/agents` the lockfile pins is the one that serves
  the agent.
- **Python: a `pyproject.toml`, and `pinecall` in its dependencies.** The platform installs it with
  uv on CPython 3.13 (`uv sync --frozen --no-dev` from `uv.lock`, else `uv sync --no-dev`), as
  `pinecall new --python` lays it out; the version of `pinecall` it resolves is the one that serves
  the agent.

Either install has five minutes at most, and the agent is started by the platform's own `pinecall`.
- **The app's name**: this folder's name, or `--name`. Lower-case words and dashes. The first
  upload makes the app — counted against the org's `hosted_apps` quota in that environment, and given a
  server's token of its own (`hosted app <name>` in the console's API keys); every later upload is its
  next release, numbered, never edited.

Then the platform installs the release, starts `pinecall start` (`--prod` in production) with the org's
[secrets](#secrets), its token and the gateway's address in the environment, and the verb follows
it: **live** once the release's agents have registered, which is when the release before is told to
drain — so a deploy cuts no call. A release that does not install, exits, or registers nothing in
two minutes is **failed**, printed with its last lines, and the release before keeps answering;
the verb exits 1. `--no-follow` returns once the upload is kept. Every verb below but `list` takes the
app as `--name`, this folder's name when left out; `rollback` takes `--no-follow` too.

Every agent under `agents/` runs in the one process, as `pinecall start` holds them at the root.
The sandbox's platform unless `--prod`; each environment hosts its own apps.

| | |
|---|---|
| `pinecall deploy list` | every app of the org in the environment: `live: release 3`, a release on its way, or the one that failed and why |
| `pinecall deploy releases` | one app's releases, newest first: when, how big, who, and the note |
| `pinecall deploy rollback <n>` | release n's sources kept again as the next release, on the platform itself, and followed like any |
| `pinecall deploy logs [--follow]` | the last lines of the app's process, fresh: asking is what makes the platform send them, a beat or two later, so the verb waits up to fifteen seconds for lines read after it asked (older ones are printed with how old they are). `--follow` keeps printing the lines that come, until Ctrl-C |
| `pinecall deploy stop` · `start` | stopped, its process drains and nothing runs — its releases and token stay, and `list` says `stopped`; started, its newest release runs again |
| `pinecall deploy rm` | the app no longer hosted: its releases go and its token is revoked |

The process prints no console link: a hosted app's output is a log, and a one-use code in a log is
a way in for whoever reads it (see [`start`](#start)).

## `studio`

```console
$ pinecall studio new front-desk
front-desk: made in the sandbox as release 1 — `pinecall studio pull front-desk` writes it to a file
$ pinecall studio pull front-desk
front-desk: release 1 written to front-desk.studio.json
$ pinecall studio push front-desk --note "books the visit"
front-desk: front-desk.studio.json saved as release 2 in the sandbox
$ pinecall studio try front-desk find_slot day=2026-10-21 people=2
200 · 184 ms
{
  "free": 2
}
$ pinecall studio deploy front-desk --note "first week"
front-desk: in production as release 1, answering from its next call
```

An agent built in the console's Studio is no class and no project: one **definition** — its
instructions, its greeting (`say` the words, or `reply` for an opening of the model's own), the
HTTP requests it may make as tools, and the data it collects from the caller, posted where you say
when the call ends — kept by the gateway, which holds the agent itself. Nothing is started to talk
to it: `pinecall chat front-desk` reaches it in the sandbox like any agent. It is a hosted app as
[`deploy`](#deploy) uploads one, so `pinecall deploy list` shows it beside the others, counted against
the same quota, and `deploy stop`, `start`, `rm` and `rollback` take it by name. Every save is a
release, numbered, never edited.

`pull` writes the newest release as `{"release": N, "definition": {…}}` to `<name>.studio.json`
(`--out` names another file); edit it and `push` saves it as the next release **based on N**, then
writes the new number into the file, so the next push goes over it. If someone saved in between —
in the console or another terminal — the gateway refuses it (409, exit 2) and nothing is kept:
pull again and edit that. A file that is not what `pull` writes is refused before anything is sent,
naming the field; a push in which nothing changed keeps the release it was. A header's value
names a secret as `{{secrets.NAME}}`, set with [`secrets`](#secrets) — never the secret itself, in the
file or anywhere else; a definition that names a secret the environment does not have is refused, and
so is one that names a secret anywhere but a header's value — the instructions, a description, a URL.
An answer that repeats a secret back is shown with `***` in its place.

The sandbox's agents unless `--prod`. `deploy` is asked from the sandbox and lands in production: it
takes a person's key that may act there, and the secrets the definition names must be set in
production too.

| | |
|---|---|
| `pinecall studio list` | the org's Studio agents in the environment: each one's release, who saved it, whether it is stopped |
| `pinecall studio new <name> [--note <why>]` | one made, starting from the template the gateway gives; the name is an app's: lower-case words and dashes, free among the org's apps and agents |
| `pinecall studio pull <name> [--out <file>]` | the newest release written to a file, the release beside the definition |
| `pinecall studio push <name> [--file <file>] [--note <why>]` | the file saved as the next release, over the release it was pulled at |
| `pinecall studio try <name> <tool> [key=value …]` | the saved tool's request sent once, as a call would send it, and its status, time and body printed; a value that reads as a number or as `true`/`false` is sent as one, anything else as text |
| `pinecall studio deploy <name> [--release <n>] [--note <why>]` | the sandbox's release — its newest unless `--release` — kept as production's next, answering from its next call |
| `pinecall studio code <name> [--out <dir>]` | the agent as a TypeScript project of the framework's — the class `pinecall deploy` would run — saved as `<name>.zip`, or with `--out` its files written into that folder (under `<name>/`), none over a file already there |

## `secrets`

```console
$ printf %s "$CRM_TOKEN" | pinecall secrets set CRM_TOKEN --prod
CRM_TOKEN kept · the org's hosted apps here start again with it
$ pinecall secrets --prod
NAME       SET               BY
CRM_TOKEN  2026-09-30 13:22  m_ana
```

What the org's hosted apps are started with, as environment variables: the org's, per environment, so
every app `deploy` put there starts with all of them. A name is an environment variable's
(`CRM_TOKEN`), never one starting with `PINECALL_` — the platform sets `PINECALL_KEY` and `PINECALL_URL`
itself. The value is typed without echo, or piped; it never goes on the command line, where the
shell would keep it. The gateway keeps it sealed and **nothing reads it back**: `list` shows names,
who set each and when. Setting or dropping one starts every app of the org in that environment again,
the old process answering until the new one registers. `rm <NAME>` drops one.

## `team`

```console
$ pinecall team
EMAIL              NAME  ROLE   STATUS   RUNS THE BOX
ana@clinica.com    Ana   admin  active   yes
luis@clinica.com   Luis  qa     invited  no
$ pinecall team password luis@clinica.com
password:
again:
luis@clinica.com signs in with the password typed, from their next sign-in · active
$ pinecall team reset ana@clinica.com
ana@clinica.com chooses their password here, once:
https://cloud.pinecall.io/invitations/inv_…
```

The org's people. `password <email>` sets anyone's password, an admin's verb (the key needs
`team`): typed twice without echo at a terminal, or piped (`printf %s "$NEW" | pinecall team
password luis@clinica.com`), never a flag the shell would keep. An invited person given a password
is active at once, with no link opened; a disabled one is enabled first. `reset <email>` makes a
one-use link instead, for the person to choose their own: the gateway hands it over when the box
sends no mail, and mails it otherwise. On a runtime of your own, `pinecall-runtime setup` makes the
first person with a password, and `pinecall-runtime orgs password` is the operator's way to the same.

## `telemetry`

```console
$ printf %s "$DD_API_KEY" | pinecall telemetry set https://otlp.datadoghq.eu/v1/traces --header dd-api-key
traces go to https://otlp.datadoghq.eu/v1/traces · headers dd-api-key
$ pinecall telemetry
traces go to https://otlp.datadoghq.eu/v1/traces · headers dd-api-key · words stripped
```

Where this org sends a copy of its calls' traces: an OpenTelemetry collector of its own —
Langfuse, Datadog, Grafana, or one you run. Off until set; the console's call page, Observability,
judges and monitors read the call's log, never this. Every spoken call's spans go there over OTLP
(a chat has no worker and so no spans): the model's requests (`gen_ai.*`: provider, model, tokens, time
to first token), speech in and out, every tool the agent ran, each span carrying `pinecall.org`,
`pinecall.env`, `pinecall.agent` and `pinecall.call`, so one call is one trace in your tool.
`set` takes the URL on the command line and each header's **value** from stdin, one per
`--header`, in the order named — typed without echo on a terminal, or piped one line per header —
never from a flag. `--pii` lets a span carry what was said and what a tool got; without it the
words are stripped before export and the timings, tokens and names stay. The gateway keeps the
headers sealed and never reads them back: the bare verb prints the URL and the headers' names.
`clear` stops the export; the calls' logs stay on Pinecall either way. Langfuse takes two headers,
piped one line each: [Export traces](https://docs.pinecall.io/guides/export-traces/).

## `alerts`

```console
$ pinecall alerts
when              kind               about          agent        mailed
2026-10-23 09:33  app.failed         support        —            yes
2026-10-22 18:02  monitor.fired      slow answers   front-desk   yes
2026-10-22 11:40  credits.exhausted  minutes        front-desk   no
```

What this org was told, newest first: every alert of the environment (`--prod` for production's),
kept 90 days whether or not a webhook is set. Each one is mailed to the org's admins and the
platform's operators, once an hour per monitor, app or quota, and `mailed` says whether this one
was; the webhook below is optional. `--limit` says how many, 50 unless said, 200 at most.

## `monitors`

```console
$ pinecall monitors add "slow answers" --metric e2e_median_s --above 2 --days 7
mon_3f9a1c2b4d5e · slow answers · e2e_median_s above 2 over 7 days · every agent
$ pinecall monitors add "judges slipping" --metric held_rate --below 0.9 --agent front-desk
mon_8b1d2e3f4a5c · judges slipping · held_rate below 0.9 over 7 days · front-desk
$ pinecall monitors
mon_3f9a1c2b4d5e  slow answers     e2e_median_s above 2 over 7 days   every agent  fired 2026-10-08 at 2.41
mon_8b1d2e3f4a5c  judges slipping  held_rate below 0.9 over 7 days    front-desk   never fired
$ pinecall monitors rm mon_8b1d2e3f4a5c
mon_8b1d2e3f4a5c forgotten
```

The numbers this org watches, and the line each must not cross. A monitor reads one number of
the observability series — the same the console's Observability screen draws — over a window of
1, 7 or 30 days (`--days`, 7 when left out), for every agent or one (`--agent`), and fires the
first time a call's seal finds it on the wrong side of the line: once a day, as `monitor.fired`
on the agent's log, where the console's Monitors screen, `pinecall monitors` (the FIRED column) and
`pinecall alerts` show it with the day and the value that crossed. `--above` fires over the line, `--below` under it.
The series is the org's own calls: in production every call; in the sandbox the calls of the org's servers, hosted
apps and CI, never a person's own sandbox calls (`chat` or `start` on a sign-in), which are that person's tests and
alert nobody. To try a monitor in the sandbox, make the calls with a sandbox server token.

| metric | what it is |
|---|---|
| `e2e_median_s` | the caller's wait from their last word to the agent's first, median, in seconds |
| `llm_median_s` | the model's time to its first token, median, in seconds |
| `held_rate` | the share of the judges' verdicts that held, 0 to 1 — a floor, `--below` |
| `escalated_rate` | the share of calls a person took over, 0 to 1 |
| `tool_failure_rate` | the share of tool calls that failed, 0 to 1 |
| `spend_usd` | what the calls cost, in dollars |
| `calls` | how many calls there were |

`rm <id>` forgets one. The list is the world's: `--prod` for production's monitors.

## `webhook`

```console
$ printf %s "$WEBHOOK_SECRET" | pinecall webhook set https://hooks.example.com/pinecall --secret
alerts go to https://hooks.example.com/pinecall · signed
$ pinecall webhook test
the URL took it: a signed webhook.test post answered 2xx
$ pinecall webhook
alerts go to https://hooks.example.com/pinecall · signed
```

Where this org's alerts are posted beyond the agent's log, the list above and the admins' mail: a URL of your own, optional — Slack, PagerDuty,
your backend. Every alert — a monitor that fired (`monitor.fired`), today's spend three times
the usual (`spend.unusual`), a quota that ran out (`credits.exhausted`) — is posted as it is. The URL is on the public internet: one whose host is local, private or link-local, or resolves there (`127.0.0.1`, `10.…`, `169.254.…`, `localhost`, `*.internal`), is refused, since the deployment would post into itself on an org's word
written, as JSON `{type, org, env, agent, at, data}` with `x-pinecall-event` naming the type,
tried twice within five seconds; a URL that fails is logged and the log keeps the alert. `set`
takes the URL on the command line and, with `--secret`, the secret from stdin — typed without echo
on a terminal, or piped — never from a flag; with a secret every post carries
`x-pinecall-signature: sha256=<HMAC-SHA256 of the body>`. The gateway keeps the secret sealed and
never reads it back: the bare verb prints the URL and whether posts are signed. `test` posts one
`webhook.test` event, signed the same way, and exits 1 if the URL did not answer 2xx. `clear`
stops the posting. What the console's bell tells each person is their own choice, under
Notifications; the webhook is the org's. [Alerts](https://docs.pinecall.io/guides/alerts/) has a
verification snippet per language.

## Exit codes

| | |
|---|---|
| `0` | it did what it says |
| `1` | the thing measured did not hold: a golden broke, a check failed, a judge answered broken, a drift fell past the threshold, the run itself broke (its reason printed with the report) |
| `2` | this command could not run, and measured nothing: no key, a flag that is not a flag, a name nothing answers to, an input refused, **any refusal of the gateway** — 400, 401, 403, 404, 409, 422, 429, 503, in its own words — the network down, a verb that moved (`pipeline set` is `agent set` now) |
| `130` | stopped: Ctrl-C (or SIGTERM) on a verb, which is not a failure |

`start` and `prompt` run the agent's own process: when it leaves on its own they end with its exit code,
whatever it is — 2 when the gateway refused what the class declares.

A call **nobody judged** is not a pass: `simulate --judge` exits 2 for it, with the reason, because
"nobody looked at this" must never open a gate. A step in CI fails on either 1 or 2; 1 says the agent
is what failed, 2 says the check never ran.

## What each verb knocks at

The bridge between this document and the gateway API. Anything in the right-hand column, your own
code can call — over HTTP, in any language, with the same key.

| verb | endpoints |
|---|---|
| `start` | `GET /v1/whoami` before anything registers; `WS /v1/apps` twice: the agent's serve entry, a process it starts, and its own companion socket (`answers_dev`); `GET /v1/agents/{slug}/config` for the tools on the connected line. `--events` prints the serve entry's own lines and asks nothing more |
| `start`, once connected | `POST /v1/login/codes` (the console's URL, at the instance it registered at), `PUT /v1/line/from` (the kept phone, on every connect in the sandbox), `GET /v1/routes` (the endpoints it answers at), `GET /v1/agents/{slug}/line` (when one of them is a number) |
| `chat` · `simulate` · `personas try` | `WS /v1/chat?agent=&contact=` — no `app=`: the gateway sends the call to whoever holds the agent; a written `simulate` asks `POST /v1/evals/caller` for each caller's line, reads the persona at `GET /v1/agents/{slug}/personas` and follows `GET /v1/calls/{call}/events` (SSE) |
| `sessions` · `sessions log` · `supervise` | `GET /v1/agents/{slug}/sessions` (the list), `GET /v1/calls/{call}/events` — a JSON page for `log`, SSE for `supervise` |
| `sessions <call>` · `supervise` | `GET /v1/calls/{call}/state` — asked FIRST, because it is the one endpoint that 404s for a call this gateway has no log of |
| `supervise` | `POST /v1/calls/{call}/verbs` — with the **org key**: a desk that only reads and types needs no seat. A seat (`POST …/supervise`) is for audio, and that is the console's |
| `simulate --listen` | `POST /v1/calls/{call}/listen`, then the LiveKit room |
| `simulate --voice` · `test --voice` | `POST /v1/evals/voice`; `simulate` then follows the call's events (SSE) |
| `test` · `runs` | `POST /v1/evals/run`, `GET /v1/events` (the org's feed, `run.changed`) while `test` follows it, `GET /v1/evals/runs[/{id}]`; `runs promote` is `GET /v1/calls/{call}/golden?name=&from_seq=` |
| `cases` | `GET /v1/evals/cases?agent=&status=` (a case is found by its name there), `PATCH`·`DELETE /v1/evals/cases/{id}`, `POST /v1/evals/cases`; `add` is `PUT /v1/agents/{slug}/cases/{name}`, one per golden; the groups are `GET /v1/evals/groups?agent=`, `GET`·`PATCH /v1/evals/groups/{id}`, `POST …/{id}/propose` · `…/apply` · `…/persona` |
| `runs drift` | `GET /v1/agents/{slug}/sessions` — a held-rate is counted off the verdicts the calls already carry, so it asks the sessions endpoint and no evals endpoint at all |
| `eval` | `POST /v1/evals/replay/{call}` |
| `agent` | `GET`·`PUT /v1/agents/{slug}/settings`, `GET …/settings/history`, `GET …/settings/diff`, `POST …/settings/rollback`; `list` and `stop` are `GET /v1/apps` and `POST /v1/apps/{app}/stop` |
| `agent knowledge` · `lexicon` · `memory policy` · `docs attach` · `detach` | `GET`·`PUT /v1/agents/{slug}/settings` · `GET`·`PUT /v1/agents/{slug}/lexicon`, `GET …/history` |
| `kill` | `POST /v1/agents/{slug}/kill` |
| `pipeline` | `GET /v1/agents/{slug}/pipeline`; `melody` is `GET`·`PUT /v1/agents/{slug}/pipeline/hold-audio`, `PUT …/hold-audio/played` and `…/hold-audio/after` |
| `docs` | `PUT`·`GET`·`DELETE /v1/knowledge[/{base}]` (`push` adds `?replace=true` with `--replace`), `GET`·`DELETE /v1/knowledge/{base}/files/{path}` (`pull` reads the list, then each file; `rm`), `POST /v1/knowledge/{base}/eval`, `GET /v1/knowledge/attached` |
| `memory` | `GET`·`DELETE /v1/contacts/{contact}/memory`, `POST /v1/contacts/memory/eval` |
| `remember` | `POST /v1/agents/{slug}/memory/extraction` |
| `numbers` | `GET`·`POST /v1/numbers`, `DELETE /v1/numbers/{number}`, `GET /v1/numbers/available`, `POST /v1/numbers/buy` |
| `carriers` | `GET /v1/carriers`, `GET`·`PUT`·`DELETE /v1/carrier[?account=]` |
| `providers` | `GET /v1/providers` · `PUT`·`DELETE`·`GET /v1/provider-keys[/{vendor}]` |
| `voices` | `GET /v1/voices` · `POST /v1/voices/sample`, and `GET /v1/providers` for the platform's own voice vendor |
| `callbacks` | `GET /v1/callbacks[?agent=&after=]` |
| `personas` | `GET /v1/agents/{slug}/personas` · `PUT`·`DELETE /v1/agents/{slug}/personas/{name}` · `POST /v1/agents/{slug}/personas/generate` — and `push` reads the agent's remaining files before sending them |
| `judges` | `GET /v1/agents/{slug}/judges` · `PUT`·`DELETE /v1/agents/{slug}/judges/{name}` · `POST /v1/agents/{slug}/judges/try`, and the same at `/v1/org/judges` with `--org`; `agreement` is `GET /v1/evals/calibration[?agent=]` |
| `judging` | `GET`·`PUT /v1/org/judging` · `GET /v1/provider-keys` to say whose key the model runs on |
| `line` | `GET`·`POST`·`DELETE /v1/agents/{slug}/line`, `PUT`·`DELETE /v1/line/from` |
| `console` | `POST /v1/login/codes` in the environment asked — the one-use code the browser spends for a key of its own. Every other endpoint the console asks, it asks for itself |
| `login` | `POST /v1/login/pairings`, `GET …/{code}/key` — then `GET /v1/whoami` to prove what it got, and `GET /v1/providers/advice` for what the gateway gives |
| `new` | on a signed-in machine, `GET /v1/login/orgs` for your orgs and `POST /v1/login/org` for this machine's key in the one picked |
| any verb in a project | `GET /v1/login/orgs` and `POST /v1/login/org` once, when its `pinecall.json` names an org this machine has no key in yet |
| `whoami` | `GET /v1/whoami` in the environment asked — the sandbox, or production with `--prod` |
| `deploy` | `POST /v1/hosted/{name}/releases` (the tarball itself, `application/gzip`), then `GET /v1/hosted` every few seconds while it follows; `list` is `GET /v1/hosted`, `releases` `GET …/{name}/releases`, `rollback <n>` `POST …/{name}/rollback {release}`, `logs` `GET …/{name}/logs` every two seconds, `stop` · `start` `POST …/{name}/stop` · `…/start`, `rm` `DELETE /v1/hosted/{name}` |
| `studio` | `list` is `GET /v1/studio/agents`, `new` `POST /v1/studio/agents {name, note}`, `pull` `GET /v1/studio/agents/{name}`, `push` `PUT …/{name} {definition, based_on, note}`, `try` `POST …/{name}/try {tool, arguments}`, `deploy` `POST …/{name}/deploy {release, note}` in the sandbox, `code` `GET …/{name}/code` (`application/zip`) |
| `secrets` | `GET /v1/secrets` · `PUT`·`DELETE /v1/secrets/{name}` |
| `telemetry` | `GET`·`PUT`·`DELETE /v1/telemetry` |
| `monitors` | `GET`·`POST /v1/monitors` · `DELETE /v1/monitors/{id}` |
| `webhook` | `GET`·`PUT`·`DELETE /v1/webhook` · `POST /v1/webhook/test` |
| `team` | `GET /v1/members` · `PUT /v1/members/{id}/password` · `POST /v1/members/{id}/reset` |
| `limits` | `GET /v1/limits` |
| `data` | `DELETE /v1/calls/{call}` · `DELETE /v1/contacts/{contact}` · `GET /v1/org/erasures` · `GET /v1/org/reads` · `GET`·`PUT /v1/org/policy` · `GET`·`DELETE /v1/org/consents/{number}`, `POST /v1/org/consents` · `GET`·`POST /v1/org/dnc` · `GET /v1/org/export` |
| every verb, without `--prod` | its own endpoints at the gateway it found, with the key it found and `pinecall-env: sandbox` on each request and socket; nothing else is asked first |
| every verb, with `--prod` | the same endpoints at the same gateway, with the same key and `pinecall-env: production` on each request and socket |
| `prompt` | none. It is the one verb that needs no gateway and no key |
