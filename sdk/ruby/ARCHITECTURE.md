# Architecture — `pinecall`, the Ruby package a tenant writes an agent in

What this package is, file by file, what each piece corresponds to in the TypeScript package it
was brought over from, and where it meets the runtime (`pinecall/runtime`), whose wire it speaks.

**The thesis.** An agent is an object. Fields are state. Methods are capabilities. Docstrings are
prompts. Types are contracts. The prompt is `render(state)`. Tools are the only thing that changes
state. The log is the truth.

---

## 1. Three repositories, one product

| repository | language | what it owns |
|---|---|---|
| `pinecall/runtime` | Python, on livekit-agents | the wire and its golden log; the real time: LiveKit rooms and SIP, STT/LLM/TTS, the gateway's doors, the log, the judges |
| `pinecall/agents` | TypeScript, Node ≥ 24 | the same class, for a team that writes TypeScript (`@pinecall/agents`) |
| `pinecall/cli` | TypeScript, Node ≥ 24 | the one `pinecall` CLI, for every language: it starts this gem's serve entry |
| **`pinecall/ruby`** (this one) | Ruby ≥ 3.2 | the same class, for a team that writes Ruby |

The line between this package and the runtime is a **socket**. This package never imports the
runtime, never speaks HTTP to a vendor, never sees audio, and holds no key of its own beyond the
one the person typed.

```
   a tenant's agent.rb                  this package                     pinecall/runtime
   ──────────────────                   ────────────                     ────────────────
   class ClinicaNorte      ──mount()──▶  lib/pinecall/bridge  ──WS──▶    gateway ──▶ LiveKit
     state = state                       lib/pinecall/client  ◀─entries─ worker  ──▶ STT·LLM·TTS
     tool  = verbs                                                       log     ──▶ Postgres
     views/clinica-norte.erb ─render()─▶ prompt.set                       judges
```

## 2. The tree

```
lib/pinecall.rb              the door: what a stranger who types `require "pinecall"` may reach
lib/pinecall/
  version.rb errors.rb       the version, written once; one error root, five words
  reading.rb                 the state as something you can ask questions of by name, this caller included
  agent.rb                   the base class: config, state, tools, the four hooks, this call
  agent/author.rb            who is writing right now — `Fiber[]`, per call, never a global
  agent/doc.rb               the comment above a class or a method, read back out of the source
  agent/state.rb             the `state` and `stage` macros, the store, snapshot · restore · collapse
  agent/tools.rb             the `tool` macro, the registry, what this state shows
  agent/spec.rb              one tool as the gateway receives it, and what is refused at load
  agent/config.rb            the four a class may still declare, and the world's twelve, refused at load by name
  agent/harness.rb           `judges on:` and `personas on:` filled in from the folders beside the class's file: `judges/*.md`, `test/personas/*.json`
  view.rb                    the ERB template and what it is rendered in
  rules.rb                   the framework's own words: the rules, the protocols, and the channel's
  blocks.rb                  the prompt as four named blocks in two regions: the layout, `render`, `show`
  panel.rb                   the console's panel beside a conversation: `panel`, its catalogue, the nodes it draws
  agent/knowledge.rb         `knowledge.search`: the bases attached, searched for the call in hand
  agent/searching.rb         whether a class searches at all, read off its source with Ripper's tokens
  call_world.rb              the live call as the class holds it: its verbs, and the entries folded in
  call_world/room.rb         who is in the room, a seat's two verbs, the turns
  call_world/answers.rb      what a verb waits for and what it gets: a transfer, a supervisor, a search
  bridge.rb                  `mount`: one instance per call, and the sync that sends what changed
  serve.rb                   `Pinecall::Serve.main`: the entry the one CLI starts — `start`, `prompt` — and `Pinecall.serve`
  serve/loading.rb           its flags, the class in a file, a state field by field
  serve/declared_docs.rb     the `docs/` folder beside a class that declares its base, pushed once the agent registers
  serve/held.rb              the agents a process holds, and leaving: a drain, then the socket, once
  serve/masking.rb           what `--events` prints of an agent's entries: the values it declared `pii`, masked
  serve/viewing.rb           `view.render`, the one console verb an agent's own process answers
  client.rb                  `Pinecall::Client`: one socket, the agents on it, observe · history
  client/connection.rb       the WS: the key at the door, backoff on the way back, a ping
  client/agent.rb            one agent from the app's side: registration, tool calls, listeners
  client/call.rb             one live call as the app holds it, and the book of them
  client/listeners.rb        who is listening for what
  client/observe.rb          reading a log: one page, and the stream after it
  client/rest.rb             one JSON request at a REST door, and the refusal as the gateway wrote it
  client/endpoints.rb        one base URL, its four doors: the apps' socket, two logs, a call's lookup
  testing.rb                 a gateway that is not there — what ring 0 mounts against
sig/                         the public surface as RBS. `rake rbs` is part of the gate
../../examples/ruby/clinica_norte/   the TypeScript example's agent in Ruby, in the CLI's layout: its agenda, its
                             view, its ring-0 suite, and the same eleven goldens (`rake ring1`)
test/                        mirrors lib/; `conformance_test.rb` holds the SDK to its wire: every
                             command sent by one method or said to be nobody's, every event folded
                             or ignored with a reason
```

## 3. What came from where: the TypeScript package, line by line

Every line of this table is a decision, not a translation. The right-hand column is what Ruby
gives that TypeScript does not, or what it takes away.

| in `pinecall/agents` (TS) | here (Ruby) | why it is different |
|---|---|---|
| `class X extends Agent { patient = null }` and a `Proxy` on the constructor | `state :patient` | TypeScript must catch an assignment to *any* field, so it needs a Proxy. Ruby declares its state, so the writer the macro generates **is** the recorder. What you cannot do by accident, you cannot do. |
| `CONFIG_FIELDS`: four names skipped on every write | config declared on the **class**, state on the **instance** | "config is not state" stops being a rule anybody has to remember and becomes where the words are written. There is no list. |
| `@tool({...})` decorator | `tool ...` above the `def`, caught by `method_added` | Ruby has no decorators; it has the hook Sorbet's `sig` uses. The declaration still reads top to bottom. |
| `docstrings.ts`: the class's own source parsed with **oxc** | `Method#source_location` + the comment block above it | Ruby keeps where every method was defined and the file is still on disk. No parser, no dependency, same two lines. |
| parameter types read out of the TypeScript signature | `Method#parameters` for the names, `params:` for the types | A Ruby signature carries no types. Names are free; anything that is not text says so once. |
| a tool takes positional arguments, mapped by name from the source | a tool takes **keyword arguments only**, refused otherwise | A model fills a JSON object by name. Filling by position is a thing only a human gets right. |
| `AsyncLocalStorage` for the current author | `Fiber[:pinecall_author]` | Ruby 3.2's fiber storage: inherited by the fibers a fiber starts, and per thread. Same guarantee, one line. |
| `zod` parses a command before it leaves | the generated shape table plus `Validate` | The schema already generated the table; walking it is thirty lines that cannot drift from zod or pydantic. |
| `Camel<T>`, `toCamel`, `toSnake` — a whole conversion layer | *nothing* | The wire is snake_case and so is Ruby. The layer does not exist here. |
| `render()`, a method on the class, returning JSX | an **ERB template** beside the class, `views/<slug>.erb`, rendered with the instance in scope | The same sentence — the object renders itself — in each language's own idiom. A TypeScript class renders in a method because JSX is an expression; a Ruby class renders in a view because that is what a view *is* here, and it costs no build step: `pinecall prompt` reads the file a person edited. |
| `ENVIRONMENT`, `environmentOf` and `refuseTheEnvironment`: the class's statics and what `@voice`/`@llm`/`@stt` set, read into the declaration; an environment field on the probe instance refused | `Config::ENVIRONMENT`, the same list, and a class macro per field that stores it on the class (`environment`), inherited and sent in `wire_config` | TypeScript keeps the class's own declarations as statics and decorators because an instance field is a call's state. Ruby's config words are calls in the class body, so each one is the declaration itself, read back by calling it with no argument. |
| `searching.ts`: the source parsed with oxc for a `this.knowledge` member expression | `Searching`: Ripper's tokens for `knowledge . search` or `call . search` | Ripper is in the stdlib and a string or a comment is one token of another kind, so a word in prose never counts. No dependency, the same answer as an AST walk. |
| a `Promise` per waiting verb, settled by the entry that answers it | a `Thread::Queue` per waiting verb (`CallWorld::Waiting`), popped with a ceiling | The tool that asked runs on its own thread, so blocking it is the honest shape: `transfer` returns when the log says how it went, or at 90 s. |
| `searching(query, k)` handed by the bridge, `pc.search` over `POST /v1/calls/{id}/lookup` | the same lambda, `Client#search` over the same door | The search is the gateway's for the call in hand; the class only asks. |
| `call.started.state` applied by `connect.ts` between `onCall` and the first render | the same, in `Bridge.start` | The state a call opens in is the wire's: whoever opened the call asked for it, and both SDKs apply it at the same moment. |
| `this.remembers("médico habitual")` inside `render()` | `remembers?("médico habitual")` in the template | The same question, asked of the runtime's answer, in each language's own punctuation. Neither prints the fact: a fact reaches the model as a `recall` tool result, in the history, and the view only branches on it. |
| `Blocks = { blocks }`; the layout is `Block[]` in send order | `Blocks = Data.define(:blocks, :history)`, `Block = Data.define(:name, :region, :text)` | Ruby keeps the history on the same value, because `pinecall prompt` prints it between the regions and a `collapse` is the one thing the app knows about the turns. |
| `src/serve/` — `main(argv, io)`, `start` and `prompt`, spawned by the CLI | `Pinecall::Serve.main(argv, out:, err:, env:, input:, signals:)`, the same two verbs, spawned by the same CLI through `ruby -r pinecall -e` | One CLI for every language: it never loads a class, so each SDK ships the entry that does and no executable. |
| `new Pinecall({ url, apiKey })` reads nothing | `Client.new(url:, api_key:, env:)` reads nothing | The environment is the entry's to read, once; a library that reads it picks the wrong key in a process that runs two. |
| `pc.drain()`, `pc.onEntries`, `pc.onStopped` | `client.drain`, `client.on_entries`, `client.on_stopped` | The serve contract is the same in both: the wire entry on stdout, a drained leave, a stop said once. |
| `pc.onConnected`, `agent.onDev` | `client.on_connected`, `agent.on_dev` | The same: after every agent on the socket registered, each time it comes up; a console's ask answered by a block that returns the answer or raises `DevRefused` |
| `@view(CustomerCard)`, the `@pinecall/agents/panels` tags, JSX rendered to nodes | `panel "Cliente" do \|who\| … end`, the block drawing on a `Panel::Drawing` | Ruby has no JSX: the block calls the catalogue's seven methods (`panel`, `rows`, `row`, `stat`, `table`, `badge`, `text`). The nodes are the same JSON, so the console draws them with the same parts; serve's `start` answers `view.render` with them |
| `Promise`, one event loop | one reader thread, one thread per call, one per tool call | The socket is never blocked by a hook or a tool. Everything belonging to one call is still serialised, which is what makes `call.cause` mean anything. |
| `WeakMap` internals kept off the instance | plain ivars behind declared readers | Nothing enumerates a Ruby object's fields by accident, so nothing has to be hidden from a snapshot. |
| `test/index.test.ts` pins the exports by name | `sig/pinecall.rbs` and `rake rbs` | Ruby's answer to a `.d.ts`: adding to the surface means editing the signature on purpose. |

What did **not** change, because it is the product and not the language: the four blocks of the
prompt, their two regions and their order, `recall` and `search` being tools whose answers reach
the model as tool results, `stage` as sugar over `when`, `confirm` being what makes a tool irreversible, `preview` cutting what the model sees and
not what the state keeps, the registration being memory rather than a database, and the four
rings.

## 4. The class a tenant writes

**Config** is declared on the class and is not state: it never changes during a call, is never
diffed, and no view renders it. The class is the contract; what it runs on is the world's.

| declared | becomes |
|---|---|
| `channel_rules false` | the `identity` block without its `<channel>` part: how to write for a voice, a website's chat, or WhatsApp |
| `phone`, `whatsapp`, `web` | nothing: accepted, so an old class still loads, and read by nobody. A door is a row the org keeps (`pinecall numbers import`) |
| `voice`, `llm`, `stt`, `judge`, `language`, `greeting`, `hangup`, `turn`, `says`, `hears`, `memory`, `record`, `knowledge`, `docs`, `judges`, `personas` | the environment the class declares, sent on `agent.configure` in the wire's shape; each one declared wins over the agent's settings, which may not set it while the class does. `builds:` and `options:` on `voice`, `llm`, `stt` and `judge` reach the vendor's plugin, on the org's own key alone; `greeting` takes words or `:improvise` / `improvise("…")` (`Config::Improvised`), `hangup` words or `true`, and `stt` an `end_of_turn:` |

**State** is declared with `state`, and the rules are enforced in code:

- **Tools are the only writers.** After `seal`, a write with no author raises `UnauthoredWrite`.
  An author is set by `tool` (its own name, and the model's id for the call), by `run_hook`
  (`hook:on_call`) or by `restore`.
- **The author rides `Fiber[]`,** never a module-level stack: one process serves many calls at
  once, and two tools running at the same time must not read each other's name.
- **A derived field is state.** `state(:identified) { !patient.nil? }` is exactly what a `when`
  asks about, so it is in every snapshot and nothing may assign it.
- **`call` is a method on the base class,** so it never looks like state and never reaches a view;
  outside a call it says so rather than handing back a nil.

## 5. From a method to a tool the model may call

```
# Reserva la hora que el paciente ya ha confirmado.     ← Doc.for_method reads this
tool stage: :book, confirm: "Le reservo {{proposed.cuando}}. ¿Lo confirmo?"
def book(chosen:)                                       ← method_added catches it here
```

1. `tool` stashes the options; `method_added` fires for the next `def` and declares it.
2. `Spec.lower` turns `stage:` into a `when`, refusing a stage the class never declared.
3. `Spec.build` reads the docstring, the keyword names and `params:`, and builds the wire's
   `ToolSpec` — then checks it against the wire's own shape, at load.
4. `mount` sends every spec; `sync` sends the **visible** subset on every state change.

What a declaration is refused for, before a model ever sees it (`DeclarationRefused`): no
docstring, a name a model cannot call, a positional argument, `pii:` naming a parameter the tool
does not have, `stage:` on a class that declares no stage, a stage that is not one of its own.

## 6. The prompt: named blocks in two regions, in one order, always

| block | region | what is in it | when it changes |
|---|---|---|---|
| `identity` | static | the class docstring · `<rules>` and `<protocols>`, English for every agent · `<channel>`, by the call's channel and medium (`call.started.medium`; a gateway that does not say gets it from the channel) | never during a call |
| `knowledge` | static | the page the agent knows by heart, from the world's settings, written by the gateway — the class sends nothing | never during a call |
| `tools` | static | every tool's name and docstring, visible or not | never during a call |
| *the history* | — | the turns and the lookups (the runtime's) and the `<!-- collapsed: … -->` summaries a `collapse` left | when the app collapses |
| `view` | dynamic | what the template says about the state right now | on every state change |

The static blocks are what the provider caches, and it caches them block by block: rewriting
`tools` (a `when:` opened) leaves `identity` and `knowledge` cache hits. That is why the layout is
a list of names and not two strings, and why a block is sent by name and only when its own text
changed. The whole layout travels once, in `agent.configure`, as `AgentConfig.prompt`.

**Every block is the tenant's own words, and nothing else is ever put in one.** What memory kept
from an earlier call and what the knowledge base returned reach the model as `tool_result` blocks,
JSON, in the history — the platform runs `recall` and `search` on the app's behalf, and neither
answer passes through this package at all. The rule and the vendor guidance behind it are
`runtime/docs/security/prompt-injection.md`; what a view may do with memory is ask it a question
with `remembers?`, which the runtime answers, and say a sentence of its own about the answer.

`pinecall prompt` prints one section per block, `── identity (static) ──` … `── history ──` …
`── view (dynamic) ──`, in send order. It needs no gateway, no key and no network.

## 7. The call, and what a class may do to it

Everything on `call` was reduced from entries the client already receives; every verb is one
command on the wire. There is no LiveKit in this repository at all. What the call is — `id`, `from`,
`to`, `channel`, `medium`, `direction`, `caller`, `metadata`, `today` — is the line `call.started`
carries, named as the wire and the TypeScript package name it (`caller` shadows `Kernel#caller` on
`CallWorld`, and nowhere else).

| the class writes | the command | it lands as |
|---|---|---|
| `say(text)` | `agent.say` | `turn.agent` — the call blocks until it lands, or 30s |
| `reply(instructions)` | `agent.reply` | `turn.agent` |
| `call.send_to(topic, data)` | `room.send` | a payload in a browser |
| `call.participant(id).mute` / `.remove` | `participant.mute` / `.remove` | removing the caller ends the call |
| `call.invite(to)` | `room.invite` | a second SIP leg, or a seat |
| `log(name, data)` | `call.log` | a `custom` entry with a `seq` like anything else |
| `call.transfer(to, mode:)` | `call.transfer` | `call.transferred` — returns a `Transferred`; `ok: false` after 90 s with no word |
| `call.attention(reason, wait_s:)` | `call.attention` | `attention.answered` — returns an `Attended`, or lapses `wait_s` + 15 s later |
| `call.hold` / `call.unhold` | `call.hold` / `call.unhold` | hold music, and back |
| `call.dtmf(digits)` | `call.dtmf` | tones on the line |
| `call.claim(code)` | `call.claim` | `call.claimed` sets `call.claimed`; a code that is not four digits never leaves |
| `call.callback(number, at:, note:)` | `call.callback` | `callback.requested`; `at:` is the wire's `when` |
| `call.opt_out(note)` | `call.opt_out` | the caller's number joins the org's do-not-call list |
| `knowledge.search(q, k:)` · `call.search` | `POST /v1/calls/{id}/lookup` | the chunks, as `Found`; logged by the gateway |

The call ending answers every verb still waiting (`the call ended before it was answered`).

## 8. The bridge, step by step

`Pinecall.mount(Class, client:, last:, takes_unclaimed:)`.

1. **At mount** — one **probe** instance is built, read for its tools and its config, and thrown
   away. `client.agent(slug, options)` declares it. Nothing is sent until `connect`.
2. **`call.started`** → a fresh instance, `seal`ed, given its `CallWorld`; `on_call` runs;
   `call.started.state` — the state a golden, a persona or `?state=` asked for — is applied after
   the hook so it is not overwritten, before the first render so the model never reads a state
   the call was not in. What the class logs is forwarded from before the hook, so a `log` in
   `on_call` lands in the call's log.
3. **The opening send** — `state.set`, then `sync`. Only then does the bridge start listening, so
   a hook writing five fields is one prompt and not five. When `on_call` wrote, that `state.set`
   names the fields it wrote and the hook as its cause.
4. **On every change** — `state.set` with the field that moved and who made the write, as the wire's
   `StateCause`: the tool and the model's id for its call, the outside fact (its name and the seq of
   its entry), or the hook (`on_call`, `on_memory`); then `sync`. A write the wire has no word for
   (a restore) says nothing.
5. **`sync`** renders every block and compares each against what **this call** was last sent:
   `prompt.set <name>` only for a block whose text differs (a block never sent counts as empty, so
   an empty one costs nothing), `tools.set` only if the visible list differs. Re-sending identical
   text is a cache miss for nothing. A view (or a `when`) that raises fails its own call: one
   `render.failed` entry with the exception's class and message goes to the call's log, the model keeps
   the view it had, and the process goes on. A hook that raises fails its call the same way, through
   `hooked`: one `hook.failed` entry naming the hook (and the event, for `on_event`), the call goes on
   with what the hook wrote, `on_event` still clears `world.cause`, and `on_end` still closes the log
   and says `call.done`.
6. **A tool call** — routed to the instance serving that call, run on a thread of its own; an
   unknown call, an unknown tool and a tool that raised all come back as one `tool.result`
   carrying `error`, because a turn that never gets one waits forever; except `end_call`, the
   platform's own, whose call and result it writes itself, so the app answers none.
7. **An outside fact** — the pair (name, source) is checked against `accepts`. Facts run one at a
   time, in the order they arrived, on that call's own thread.
   **The view again** — on the caller's turn (the view answers the turn being taken), on
   `call.claimed` (the caller can see the page), and on `memory.ops`, whose recalled facts become
   what `remembers?` answers from: none of them is a state change, so nothing else would render.
8. **`call.ended`** → nothing may render for this call any more; `on_end` runs, and the log stays
   open one hook longer so a farewell line still lands; then the bridge sends `call.done`, which the
   gateway's seal waits for (three seconds at most) before it closes the call's log to lines.
9. **`call.attached`** → a call handed to this process mid-conversation (another process drained
   or died, or the gateway restarted): a sealed instance is `restore`d to the state the gateway
   kept, no `on_call` runs, and the whole prompt and the tools are sent. A call this process
   already serves keeps its instance and sends its whole prompt again.

## 9. `Pinecall::Client` — the socket alone

A second, smaller door for an app with its own way of deciding what to answer: no class, no view,
no CLI. It knows the wire (`lib/pinecall/wire/`) and `websocket-driver`.

- **Registration is memory, not a database.** `open` runs again on every reconnect. Many sockets
  may hold one agent at once; a call that named no app goes to the newest registration that takes
  unclaimed calls. That is what makes a rolling deploy work.
- **Three commands are awaited** (`agent.register` → `agent.registered`, `agent.configure` →
  `agent.configured`, `agent.drain` → `agent.draining`). Everything else is fire and read the log.
- **The declaration goes up on its own thread**, because the answer arrives as an entry and a
  thread waiting for that entry is a thread not reading it. (That was a real deadlock; the socket
  test is what found it.)
- **The key travels as `Authorization: Bearer`**, never in a URL, because a URL ends up in a log.
- **It reads nothing from the environment.** `Client.new(url:, api_key:, env:)` is given all
  three; `env` names the world in `pinecall-env`, on the socket and on a REST request alike. Neither
  the client nor its connection prints the key: `inspect` says the door and the agents, since a log
  line or an exception prints what `inspect` says.
- **One REST door of its own:** `client.search(call, query, k:)`, the gateway's lookup for a call
  this client serves, through `Client::Rest`; a refusal comes back as `Refused` carrying the
  gateway's own `detail`. The org's bases, memory and keys are the one CLI's verbs.
- **Leaving.** `drain` asks every agent to drain and waits for the tools running, up to 30 s;
  a stop from the org (`error` coded `stopped`, for no agent) closes the socket for good and goes
  to `on_stopped`, and the close frame the gateway sends behind it is answered into a socket this
  side already closed, which is no error; an agent killed (`error` coded `killed`, on that agent) is
  dropped from the agents the client declares, so a reconnect leaves it out and the others go on,
  and goes to `on_killed` with its slug and the gateway's sentence; `on_entries` hands over every
  entry as the gateway wrote it.

## 10. The serve contract

The one CLI (npm `pinecall`) starts this gem's entry for the two verbs that need the class:

```
ruby -r pinecall -e 'exit Pinecall::Serve.main(ARGV)' -- start --file agents/x/agent.rb --slug x [--console] [--events] [--prod]
ruby -r pinecall -e 'exit Pinecall::Serve.main(ARGV)' -- prompt --file agents/x/agent.rb --slug x [--state field=json]… [--channel c] [--medium voice|text] [--show-machine]
```

- **The door is the environment's, and nothing else:** `PINECALL_URL`, `PINECALL_KEY`,
  `PINECALL_ENV` (`--prod` forces production). Missing → one sentence, exit 2. Never an argv.
  `PINECALL_HOST`, when set, is the machine it registers as, this one's hostname otherwise: a
  hosted app's runner names its host, and the gateway knows the release by it.
- **The slug is the folder's**, `--slug`; a class whose `slug "…"` says another is refused.
- **`--events`:** one line per wire entry, `{"type","agent","call","data"}` with `data` as the
  gateway wrote it, `agent.registered` first (the listener is in place before the socket opens). A
  value the agent declared private is not printed: the arguments its tools list under `pii` and the
  state fields declared `pii` are masked by name, and the values of those arguments, once a tool call
  carried them, wherever else the agent wrote them down (a state field, a tool's answer, a logged
  line) — whole tokens only, and never a value shorter than three characters. What was said is never
  masked (`Serve::Masking`, as the TypeScript and Python entries do).
- **`--console`:** `takes_unclaimed: false` — a console's process takes only the calls it opened.
- **Leaving:** SIGINT, SIGTERM or the end of its stdin (the CLI that started it is gone) drains,
  then closes; a second signal closes at once, and the end of stdin after a signal is the same ask
  (the CLI sends both); a stop from the org closes without draining. A
  trap only pushes onto a queue: the main thread does the leaving. `Held#stop` is what drains and
  closes, and the one line on stderr saying where the calls went is its own, so `Pinecall.serve`'s
  `held.stop` says it as the serve entry does.
- **An agent an admin killed** (`pinecall kill`) is one line on stderr, `<slug>  ✗ <the gateway's
  sentence>`, and the process goes on holding its other agents; stdout stays the wire's.
- **The console's verbs** are answered by the CLI's companion; the one this process could answer,
  `view.render`, is refused 404 `a Ruby agent draws no panel`, by the client's default handler.

## 11. The four rings, and where each of them runs

| ring | what it asks | where it runs |
|---|---|---|
| 0 | does the class behave? | `minitest`, in the tenant's own repo. No network, no key, no model — `pinecall/testing` is the gateway that is not there |
| 1 | does the agent hold its goldens? | `pinecall test`: the one CLI, this gem's serve entry holding the class. `rake ring1` runs the example's, the same eleven the TypeScript example holds, and the CLI repository's nightly runs it |
| 2 | does it hold on a real line? | `pinecall test --voice` and `pinecall simulate --voice`, the same way |
| 3 | what does one real call score? | `pinecall eval <call-id>` |
| 4 | what did every call score? | `call.score`, written by the runtime at hang-up |

## 12. The wire

The wire is the runtime's, and `lib/pinecall/wire/` (`Pinecall::Wire`) keeps what this gem speaks
of it: the frames (`Entry`, `Command`, `Event`), the registries, the shapes the validator walks
(split by family: parts, the agent's config, metrics, the events, the commands, the doors), the
validator and the reducer. No gem of the runtime's is read. Every command's data passes through
`Codec.plain` before it is validated, so a `Data` or a `Struct` — in a tool's return, a state field,
a logged line, a payload — leaves as its fields, wherever it sits in an array or a hash, and not as
the `inspect` string `JSON.generate` would make of it. `test/wire/golden/` is the runtime's
golden call log, and `test/wire/reduce_test.rb` holds the reducer to the state it folds to.

## 13. Packaging

- **A library, no executable.** The verbs are the one `pinecall` CLI's (npm); it starts
  `Pinecall::Serve.main` through `ruby -r pinecall -e` (bundler when the project has a `Gemfile`).
- **`sig/` ships with the gem.** Ruby's type story is RBS, and `rake rbs` is part of the gate.
- **`rake check`** is the tests, the example's own suite, then the signatures. Ruby has nothing to
  compile.
