# Architecture — `@pinecall/agents`, the package a tenant writes an agent in

What this package is, file by file, and where each piece meets the runtime
(`pinecall/runtime`), whose wire it speaks. Read it before changing anything;
the why behind a single decision is a page in `docs/decisions/` on the maintainer's laptop, and
how to build an agent is `docs/`.

**The thesis.** An agent is an object. Fields are state. Methods are capabilities. Docstrings are
prompts. Types are contracts. The prompt is `render(state)`. Tools are the only thing that changes
state. The log is the truth.

---

## 1. Three repositories, one product

| repository | language | what it owns |
|---|---|---|
| `pinecall/runtime` | Python, on livekit-agents | the wire, and its golden log; the real time: LiveKit rooms and SIP, STT/LLM/TTS, the gateway's doors, the log in Postgres, memory and retrieval, the judges, the box |
| **`pinecall/agents`** (this one) | TypeScript, Node ≥ 24 | the class a tenant writes, the prompt as a function of its state, and the serve entry the CLI starts it with |
| `pinecall/cli` | TypeScript, Node ≥ 24 | the `pinecall` CLI, for an agent in any language: every verb, the process it starts, the companion socket that answers the console |

The line between this package and the runtime is a **socket**. This package never imports the
runtime, never speaks HTTP to a vendor, never sees audio, and holds no key of its own beyond the
one the person typed. It sends **commands** and it reads **entries**; both shapes are the runtime's,
kept here in `src/wire/` (§14).

```
   a tenant's app.ts                    this package                     pinecall/runtime
   ───────────────────                  ────────────                     ────────────────
   class ClinicaNorte      ──mount()──▶  src/runtime/  ──WS /v1/apps──▶  gateway ──▶ LiveKit
     fields = state                      src/client/   ◀──entries─────   worker  ──▶ STT·LLM·TTS
     @tool  = verbs                                                      log     ──▶ Postgres
     render() = the view   ──render()─▶  prompt.set                       judges
```

## 2. The tree

`src/` is the package: seven directories, and `test/the-imports.test.ts` is what keeps them apart —
a directory earns its place there by having a line in that table (§13).

### `src/agent/` — the class a tenant extends

| file | what it is |
|---|---|
| `agent.ts` | the `Agent` base: the Proxy that turns an assignment into an authored change, the internals kept off the instance, `seal`, `collapse`, `restore`, `startIn`, `log`, `say`/`reply`, `this.call`, `this.knowledge`, `render()`, `remembers()`, the four hooks. `CONFIG_FIELDS` is the names that configure and are not state: `channelRules`, and the three door names a class no longer declares, kept on the list so an old class's `phone` stays out of the state |
| `knowledge.ts` | `Knowledge`: what a class reaches its bases through — `this.knowledge.search(query, {k})`, one verb the gateway answers for the call in hand |
| `searching.ts` | whether a class searches at all: its source read with oxc for a `this.knowledge` member expression — never a regex, because the words inside a string or a comment are not a search. What it answers travels as `uses_knowledge` in the declaration |
| `decorators.ts` | `@tool({…})`, which registers a method and wraps it so every write inside it carries its name; `@render(Prompt)`, which gives the class a prompt written beside it (`Prompt<T> = (agent: T) => Child`); and `@voice`, `@llm`, `@stt`, `@judge`, which set the class's static `voice`, `llm`, `stt`, `judge` in the wire's shape, with the plugin's `builds` and `options` (`Plugin`) |
| `opening.ts` | how a call opens and when it may end, as a class writes them: `improvise` (the model opens, on its prompt or an instruction), `Opening` (words, `{ text, interruptible }`, or improvised), `Ending` (words, or `true`); `runtime/environment.ts` turns them into the wire's greeting and hangup |
| `authors.ts` | who is writing the state right now: the `AsyncLocalStorage` the author rides, `withAuthor`, `withAuthorAsync`, `currentAuthor`, and `UnauthoredWrite` |
| `tools.ts` | the tool registry: `ToolOptions`, `ToolDeclaration`, the wire `ToolSpec` built and cached per class, `visibleToolsOf`, `DeclarationRefused` |
| `docstrings.ts` | a class's own source read with oxc: the JSDoc above the class, above each method, and the parameter names and types |
| `state.ts` | `snapshot` (fields + getters, never config, never methods), `diff`, `restore`, `collapse`, `Snapshot<T>` |
| `stages.ts` | `Stages<"a"|"b">`, `StageOf<T>`, and `lowerStage` — `stage:` is sugar over `when(state)` |
| `visibility.ts` | `@state` in its three spellings — bare, `{ pii: true }`, `{ visibility }` — which fields are the state (`declaredStateOf`) and who may see them (`visibilityOf`, plus `static visibility = {…}`) |
| `accepts.ts` | `static events = {…}`: which outside facts this class takes, and from whom |
| `view.ts` | `@view(Draw)` / `@view(Draw, "Cliente")`: the panel the class draws beside a conversation, and `viewOf`. `Who` is the conversation it is drawn about — `{ agent, contact, call }` |
| `lifecycle.ts` | the hooks as a type (`onCall`, `onEnd`, `onMemory`, `onEvent`) and `runHook`, which authors their writes |

### `src/views/` — JSX that renders to text

| file | what it is |
|---|---|
| `jsx-runtime.ts` | the element factory and the renderer: a tree of tags becomes TEXT, never DOM. `renderToText`, `renderInline`, `blocks`, `Fragment`, the `JSX` namespace |
| `jsx-dev-runtime.ts` | the same factory under the name a dev-mode transform imports |
| `components.ts` | the tags a view is written in: `Rule`, `Rules`, `Protocols`, `Section`, `Example`, `p`, and `tagged` |
| `layout.ts` | the prompt as named blocks in two regions: `PROMPT_BLOCKS` (the four, in send order) and `layout` → `Blocks` |
| `built-in-rules.ts` | the framework's own words, in English for every agent: the standing rules (one is to answer in the caller's language), the protocols, and `channelRulesFor(channel, medium)` — how to write on a voice call, in a website's chat, or on WhatsApp |
| `render.ts` | `promptOf()`, `headerFor()`, `showPrompt()` (what `--show-prompt` prints) |
| `nodes.ts` | the OTHER destination of the same JSX: `renderToNodes` folds a tree of tags into `ViewNode[]` — a closed list of named nodes a console draws — for the panel beside a conversation |
| `panels.ts` | the tags that panel is written in, `@pinecall/agents/panels`: `Panel`, `Rows`, `Row`, `Stat`, `Table`, `Badge`, `Text`. One of them inside a `render()` is refused by name |

### `src/call/` — the live call as a value

| file | what it is |
|---|---|
| `call.ts` | `CallWorld`: the line, the room, the history, `say`/`reply` (which settle on the turn they land as), `send`, `participant()`, `invite`, `search()` — the gateway's search of the bases the world attached, answered as `Found[]`; a call nobody serves through a gateway refuses it with `NO_GATEWAY_TO_SEARCH` — the verbs that hand the call to a person (`transfer` and `attention`, which settle on the entry the runtime writes, and `hold`/`unhold`/`dtmf`/`callback`/`hangup`, which answer nothing) — `claim()`, which binds the call to the code a page shows, and `take()`, one entry folded in |
| `room.ts` | `Room` and `Participant` reduced from the room's own entries; `ParticipantHandle.mute()/remove()`; `invite` |
| `history.ts` | `History` and `Turn`: the finished turns, and the sentence a `collapse()` left in their place |

### `src/client/` — `@pinecall/agents/client`, the socket and nothing above it

| file | what it is |
|---|---|
| `client.ts` | `Pinecall`: one socket, the agents on it, `observe`/`history` over any log the key can read, and `search(call, query, k)` — one search of the bases the agent reads, run by the gateway for a call this client serves (`POST /v1/calls/{call}/lookup`), answered as `Found[]`. `env: "production"` names production for a person's key; a server's token needs none |
| `signed.ts` | what every request and socket carries: the key as a Bearer, and `pinecall-env` when a world was named; the `World` type |
| `connection.ts` | the WS to the gateway: the key at the door, backoff on the way back, a ping while it is up |
| `agent.ts` | one agent from the app's side: `open()` (register + configure), the tool calls it answers, the two commands it awaits |
| `calls.ts` | `Call` (everything read off the log; every method one command) and `CallBook` |
| `frames.ts` | one command frame, checked against the schema its type names |
| `listeners.ts` | who is listening for what, per agent and per call; `camelEvent` |
| `observe.ts` | reading a log, or the org's feed: the same URL as a JSON page and as SSE, folded by the wire's reducer |
| `sse.ts` | a server-sent stream over fetch: its frames from a cursor on, reconnecting with `Last-Event-ID` after a backoff, saying each time a connection opens — what `observe` and the CLI's waits stand on |
| `endpoints.ts` | one base URL, five doors — the apps socket, a call's log, an agent's log, the org's feed, a call's lookup — the only place a path is written |
| `testing/` | a gateway that is not there (`FakeGateway`, which also answers a search with what `finds()` was told and keeps what was `searched`), a log nobody stored, and the loopback address they use |

### `src/runtime/` — the bridge

| file | what it is |
|---|---|
| `connect.ts` | `mount()`: the class registered once, one live instance per call, and the sync that sends only what changed. `optionsFor` is the declaration read off a probe instance — the routes, the tools, whether it searches, the state fields, the events — and the first thing it does is refuse a field of the world's. Also `slugOf` |
| `recall.ts` | a `memory.ops` entry → the words this call has been told about the caller, which is what `remembers()` answers from |
| `environment.ts` | `ENVIRONMENT`: the settings a class may declare — `language`, `voice`, `llm`, `stt`, `judge`, `greeting`, `hangup`, `turn`, `says`, `hears`, `knowledge`, `docs`, `memory`, `record` — read off the class (`environmentOf`, its statics and what `@voice`/`@llm`/`@stt`/`@judge` set) into the declaration, where each wins over the agent's settings; and `refuseTheEnvironment`, which stops a class that declares one on the instance, where it would be a call's state |
| `dispatch.ts` | an outside fact off the wire, gated by the declaration and handed to `onEvent` — one at a time, in order |
| `run-tool.ts` | one tool call: the args checked against the spec, the method run through the instance, the result cut to its `preview` |

### `src/serve/` — the entry the CLI starts an agent with

`@pinecall/agents/serve`, a library entry and no bin: `main(argv, io)` with two verbs. Everything it
touches outside itself is an `Io` (two streams out, its environment, its stdin, its signals), so it
writes nowhere else and a test hands in its own.

| file | what it is |
|---|---|
| `index.ts` | `main`: `start` or `prompt`, a refusal (`CannotServe`, a class's `DeclarationRefused`, a flag `parseArgs` refused) is its sentence and exit 2; the is-entry guard |
| `start.ts` | `start --file <f> --slug <s> [--file --slug]… [--console] [--events]`: the door from `PINECALL_URL`, `PINECALL_KEY`, `PINECALL_ENV` and nothing else; each class loaded and mounted under its slug (`--console`: `takesUnclaimed: false`); its socket answers `view.render` and refuses every other dev verb, which are the CLI's |
| `prompt.ts` | `prompt --file <f> --slug <s> [--state field=json]… [--channel] [--medium] [--show-machine]`: the class opened in the state the pairs name, its prompt printed, and its machine under it when asked |
| `load.ts` | a tenant's class loaded with tsx and handed its own source (`loadAgent`); `loadServed` refuses a class whose `static slug` is not the one it is served as; `instanceFor` is one instance with a line to answer on, for the pages that print a prompt |
| `lines.ts` | `--events`: one line per wire entry, `{type, agent, call, data}` as the gateway wrote it, `agent.registered` first; without it a few lines for a person; `aLostSocket` |
| `leaving.ts` | asked to leave — SIGINT or SIGTERM, the end of its stdin, a stop from the org — then a drain unless a second signal says now, and the line that says where the calls went |
| `viewing.ts` · `machine.ts` | `view.render`: the class's view drawn as panel nodes; the state machine on one page |

Beside `src/`:

| | |
|---|---|
| `../../examples/typescript/clinica-norte` | one tenant, written the way a customer writes one, on the one layout |
| `test/` | mirrors `src/`, plus the three that pin the shape: the tree, the imports, the two public surfaces |
| `scripts/build`, `scripts/check` | what is published, and what CI runs |
| `docs/` | how to build an agent · `docs/decisions/` is the maintainer's notebook and **git-ignored** |

## 3. The entities

### The class, at runtime

| entity | where | fields |
|---|---|---|
| `Agent` | `agent/agent.ts` | the tenant's own fields, plus `doc()`, `tools()`, `visibleTools()`, `render()`, `remembers()`, `collapse()`, `restore()`, `startIn()`, `last()`, `log()`, `call`, `say()`, `reply()`, `on()`, and the four hooks |
| `Internals` | `agent/agent.ts` | `changes`, `log`, `listeners`, `logListeners`, `eventListeners`, `seq`, `sealed`, `target`, `call`, `last`, `recalled` — kept in a `WeakMap`, never on the instance, so they are not state |
| `Change` | `agent/agent.ts` | `seq`, `field`, `prev`, `next`, `author`, `at` |
| `LogEntry` | `agent/agent.ts` | `seq`, `name`, `data?`, `at` — what `this.log(name, data)` writes |
| `Snapshot<T>` | `agent/state.ts` | the state as a plain object: own enumerable fields **and getters**, minus the config names, minus methods |
| `FieldDiff` | `agent/state.ts` | `field`, `prev`, `next` |
| `Collapsed` | `agent/state.ts` | `summary`, `seq`, `at` — one sentence standing in for every change before it |

### What a class declares

| entity | where | fields |
|---|---|---|
| `ToolOptions<T>` | `agent/tools.ts` | `when(state)`, `stage`, `confirm`, `preview`, `pii`, `timeout`, `params` |
| `ToolDeclaration` | `agent/tools.ts` | `name`, `options`, `method`, `owner`, `spec` |
| `ToolSpec` | `src/wire/defs.ts` | `name`, `description`, `parameters`, `side_effect`, `confirm?`, `pii?`, `timeout_s?` — the wire's own shape, imported, never copied |
| `StateFieldSpec` | `agent/visibility.ts` | `name`, `visibility` (`public` · `tenant` · `pii`) |
| `EventSpec` / `EventDecl` | `agent/accepts.ts` | `name`, `from: ("app"|"participant")[]` |
| `EventMeta` | `agent/accepts.ts` | `source`, `identity?`, `seq` — `seq` numbered by **this call's** stream of events, not by the wire |
| `Call` (hook) | `agent/lifecycle.ts` | `id`, `contact`, `from?`, `channel?`, `medium?` |
| `MemoryOp` | `agent/lifecycle.ts` | `op: "remember"|"forget"`, `key`, `value?` |

### The call

| entity | where | fields |
|---|---|---|
| `CallWorld` | `call/call.ts` | `id`, `contact`, `from?`, `channel?`, `medium` (`voice` or `text`: the gateway's, else the one the channel implies), `today?`, `claimed`, `room`, `history`, `cause`, `numbered()`, `search()`, `claim()` |
| `Found` | `call/call.ts` | one chunk a search found, as the model reads it: where it came from, and its text |
| `Transferred` · `Attended` | `call/call.ts` | what a transfer and an ask for a person came to: `ok`, and who or why not |
| `Knowledge` | `agent/knowledge.ts` | `search(query, {k?})` — what `this.knowledge` is |
| `Room` | `call/room.ts` | `participants`, `caller`, `has(kind)`, `get(identity)`, `invite()` |
| `Participant` | `call/room.ts` | `identity`, `kind` (`caller` · `agent` · `supervisor` · `listener` · `sip`), `name?`, `joinedAt`, `speaking` |
| `History` / `Turn` | `call/history.ts` | `turns`, `length`, `summary`, `last` / `who`, `text`, `speechId`, `interrupted`, `at` |

### The prompt

| entity | where | fields |
|---|---|---|
| `Blocks` / `Block` | `views/layout.ts` | `blocks` in send order, each `name`, `region` (`static` · `dynamic`), `text`; `history` |
| `PROMPT_BLOCKS` | `views/layout.ts` | the four, in the one order they are sent: `identity` · `knowledge` · `tools` static, then `view` dynamic |
| `ENVIRONMENT` | `runtime/environment.ts` | the settings a class may declare, each winning over the agent's settings |
| `Child` | `views/jsx-runtime.ts` | what a `render()` hands back: an element, a string, a number, nothing, or an array of those |
| `Prompt<T>` | `agent/decorators.ts` | `(agent: T) => Child` — a prompt written beside the class, which `@render` hands the instance |

### The socket

| entity | where | fields |
|---|---|---|
| `Pinecall` | `client/client.ts` | `sdk`, `host`, `url`, `apiKey`, `env`, `agent()`, `connect()`, `close()`, `connected`, `on`/`onAny`/`onErrors`/`onStopped`, `observe`, `history` |
| `Agent` (client) | `client/agent.ts` | `slug`, `calls`, `config`, `app`, `open()`, `configure()`, `declare(tools)`, `command()`, `take(entry)`, `ping()` |
| `Call` (client) | `client/calls.ts` | `id`, `status`, `channel`, `medium`, `from`, `to`, `contact`, `claimed`, `state`, `today`, and one method per command |
| `CallBook` | `client/calls.ts` | `live`, `of(id, at)`, `forget(call)` |

## 4. The class a tenant writes

Two kinds of field live on the instance, and the difference is the whole model.

**Config** — the names in `CONFIG_FIELDS` (`agent/agent.ts`): `channelRules`, `phone`, `whatsapp`
and `web`. They configure the agent; they are not state. They are never diffed, never rendered by
a view, never in a snapshot, and assigning one does not go through the change recorder.

| field | becomes |
|---|---|
| `channelRules` | whether the `identity` block ends in `<channel>` (`views/built-in-rules.ts`): on unless the class sets it `false` |
| `phone`, `whatsapp`, `web` | **nothing.** A door is a row the org keeps (`pinecall numbers import`), never a field: `agent.register` sends `routes: []`. The three names stay on `CONFIG_FIELDS` so an old class's `phone` is still kept out of the state rather than becoming an authored change |

**The class is code; the world is environment.** Everything else an agent runs on is not the
class's to say: it varies between the sandbox and production, it is the org's to change without a
deploy, and it is kept **per world, per corner, versioned** in the agent's settings on the gateway
(the runtime's `docs/protocol/settings-api.md`). A class that still carries one of these fields is
refused at load, before a prompt is printed or a gateway is knocked at, with the verb that sets it
(`runtime/environment.ts`):

| field | is now | set by |
|---|---|---|
| `voice`, `llm`, `stt` | the settings' vendors and models | `pinecall agent set --voice · --llm · --stt`, or the Settings tab |
| `language` | the settings' `language`, the tag the voice and the ears are set to; the prompt's own rules are English either way | `pinecall agent set --language <tag>` |
| `greeting`, `hangup` | how the call opens and whether the model may end it | `pinecall agent set --greeting · --reply · --hangup` |
| `says`, `hears` | the agent's lexicon | `pinecall lexicon add <word> --say`, `pinecall lexicon hear` |
| `memory` | what is remembered about a caller and what never is | `pinecall memory policy --remember · --forget` |
| `knowledge` | **what the agent knows by heart**: Markdown, read whole into the `knowledge` block on every call | `pinecall agent knowledge edit`, or the Settings tab's Knowledge — never a file in the repository |
| `docs` | **the bases the agent searches** — the RAG — as the settings' `bases`, each with `k`, a mode and a score | the base written in Settings ▸ Docs (or started with `pinecall docs push` from a local `agents/<name>/docs/`), then `pinecall docs attach <base>`, or the Settings tab's Bases |

Knowledge and bases are two things and never one: what the agent knows by heart is a page the
org writes and the model reads entire; a base is a folder of documents chunked and embedded, of
which a turn sees the `k` best. The class reaches the bases through `this.knowledge.search()`
(`agent/knowledge.ts`): the gateway runs the search for the call in hand and logs what it found,
and a world that attaches no base to a class that searches refuses the registration at boot,
naming `pinecall docs` — not on a call, where the search would find nothing.

**State** — everything else the app puts on the instance, plus its getters. The rules, enforced in
code:

- **Tools are the only writers.** The constructor returns a `Proxy`; a write after `seal()` with no
  author throws `UnauthoredWrite`. An author is set by `@tool` (the tool's own name), by `runHook`
  (`hook:onCall`), by `dispatch` (`event:<name>`) or by `restore`.
- **The author rides `AsyncLocalStorage`,** never a module-level stack: one process serves many
  calls at once, and two tools awaiting at the same time must not read each other's name.
- **A getter is state.** `get identified() { return !!this.patient }` is exactly what a `when` asks
  about, so `snapshot()` walks the prototype chain — stopping at `Agent`, so the framework's own
  accessors never leak into the tenant's state.
- **`this.call` is a getter on the base class,** not a field: it never looks like state and never
  reaches a snapshot. A `render()` may read it — `this.call.channel` is how one class answers a
  phone call and a chat differently, `this.call.medium` whether the call is spoken or written —
  and it throws outside a call, so the pages that print a prompt give their instance a line of
  its own (`serve/load.ts:instanceFor`).
- **`render()` and `remembers()` are methods of the base,** so neither is state either. `render()`
  returns nothing by default; `remembers(text)` answers from what the runtime has recalled about
  this caller in this call, and false before anything has.
- **`@state` decides which fields are state at all.** A class that decorates none has every own
  field as state, as it always did. A class that decorates any means *these, and nothing else*: an
  undecorated field on it is the tenant's scratch space — no snapshot, no change, no author asked
  for, nothing on the wire. `declaredStateOf(ctor)` is that answer, read once per class, and the
  Proxy, `snapshot()` and `restore()` all ask it. A getter is derived and is always state.

## 5. From a method to a tool the model may call

```
@tool({ stage: "book", confirm: "…" })   →  register(prototype, {name, options, method})
  async book(chosen: string)                 lowerStage() turns `stage` into a `when(state)`
  /** docstring */                           the wrapper authors every write inside the method
                                          ↓
                        docstrings.ts (oxc) reads the class's own SOURCE:
                          the JSDoc above the method  → spec.description
                          the parameter list + types  → spec.parameters (JSON Schema)
                                          ↓
                        specFor() → ToolSpec, cached per prototype until the source changes
                                          ↓
                        mount(): every spec + its `run` → agent.register
                        sync():  the VISIBLE subset → tools.set, on every state change
```

What the declaration refuses, before a model ever sees it (`DeclarationRefused`):

- a tool with **no docstring** — without one no model can choose it;
- a tool name that is not one word a model can call (`/^[A-Za-z][A-Za-z0-9_]*$/`);
- `pii: […]` naming a parameter the tool does not have;
- `stage:` on a class that declares no `stage` field (the compiler says so first, via `StageOf<T>`).

`confirm` is what makes a tool `side_effect: "irreversible"` on the wire: the platform reads the
sentence back, hears the yes, and only then runs. `preview: n` cuts what the **model** sees of an
array result; the state field keeps every row.

## 6. The prompt: named blocks in two regions, in one order, always

`promptOf(agent)` → `Blocks`: every block in send order, each with its name, its region and its
text. Nothing may reorder them; the cut between the regions is where the cache is.

| block | region | what is in it | when it changes |
|---|---|---|---|
| `identity` | static | the class docstring · `<rules>` and `<protocols>` · `<channel>` for the call's channel and medium, all but the docstring from `views/built-in-rules.ts` | never during a call — a call's channel and medium never change, and it is the cached prefix |
| `knowledge` | static | nothing from the app: the runtime writes what the world says the agent knows by heart — the settings' `knowledge`, whole | never |
| `tools` | static | every tool's name and docstring, visible or not | never |
| — | the history | the runtime's turns and what a lookup answered; on the printed page, the summaries a `collapse()` left. Never sent by the app | when the app collapses |
| `view` | dynamic, LAST | what the class's `render()` said about this turn, and nothing else | on every state change |

The layout is the framework's, always: `PROMPT_BLOCKS` is the four in order, it travels once in
`agent.configure`, and every block is written by name with `prompt.set`. A class contributes one of
them — the view — as a `render()` method, or as `@render(ThePrompt)` with the prompt written beside
the class; the decorator is exactly `render() { return ThePrompt(this); }` and a class that
declares both spellings is refused when it is defined. Either way there is no view file to resolve,
no props to pass and no way for a tenant to declare a block of its own.

**Nothing this package writes is a hole for somebody else to fill.** There are no markers: what
memory recalled and what the knowledge base returned reach the model as `tool_result` blocks,
JSON-encoded, in the history where a lookup belongs — never spliced into the tenant's own words,
which carry operator authority. That rule, the vendor guidance it follows from and the tests that
hold it are a public contract, `runtime/docs/security/prompt-injection.md`. What a class reads back
is one question, `this.remembers(word)`, answered from the `memory.ops` entries this call has
already seen (`runtime/recall.ts`) — a fact of the call's state, never the fact's text — and one
verb, `this.knowledge.search(query)`, whose answer is a tool's result too.

`pinecall prompt` and `pinecall start --show-prompt` print exactly these blocks, each under
`── <name> (<region>) ──` with `── history ──` between the two regions, and the stage and the
visible tools beneath. Neither needs a gateway, a key or a network.

## 7. The call, and the six things a class may do to it

Everything on `this.call` was reduced from entries the client already receives; every verb is one
command on the wire. There is no LiveKit here and no escape hatch to it — a need the room cannot
express is a new command with a name.

| the class writes | the command | it lands as |
|---|---|---|
| `this.say(text)` / `call.say` | `agent.say` | `turn.agent` — the promise settles on it, or `false` after 30 s |
| `this.reply(instructions)` | `agent.reply` | `turn.agent` |
| `call.send(topic, data, {to})` | `room.send` | a payload in a browser; the log keeps its size, never the payload |
| `call.participant(id).mute()` / `.remove()` | `participant.mute` / `participant.remove` | removing the caller ends the call |
| `call.invite(to, {kind})` | `room.invite` | a second SIP leg, or a seat |
| `this.log(name, data)` | `call.log` | a `custom` entry with a `seq` like anything else |

And what the call learns, in `CallWorld.take()`: `participant.joined|left|speaking` fold into the
room; `turn.user` and `turn.agent` fold into the history, and `turn.agent` settles whoever was
waiting on a `say`; `call.claimed` sets `claimed`.

## 8. The bridge, step by step

`mount(Class, { pc, source, file, slug, last, takesUnclaimed })` is the only place
the class and the socket know about each other.

1. **At mount** — `describe(ctor, source, file)` gives the class its own text back (a docstring sits
   *above* the class, where `toString()` cannot see it, and parameter types are gone after
   compilation; the file name is what says whether that text is `.ts` or `.tsx`). One **probe** instance is built, refused if it still carries a field of the world's
   (`runtime/environment.ts`), read for its tools, its state fields and its
   events, and thrown away; the source is read once more for `this.knowledge`, so the declaration
   says whether the class searches (`uses_knowledge`).
   `pc.agent(slug, options)` declares it. Nothing is sent until `pc.connect()`.
2. **`call.started`** → `start()`: a fresh instance, `seal`ed; `setLast` and `setCall` hand it the
   store and its `CallWorld`; `runHook(onCall)`; then `startIn()` applies `call.started.state`, the
   state a golden, a persona or `?state=` asked for — after `onCall` so it is not overwritten,
   before the first render so the model never reads a state the call was not in.
3. **The opening send** — `call.setState(snapshot)`, then `sync()`. Only after that does the bridge
   start listening, so `onCall` writing five fields is one prompt and not five.
4. **On every change** — `state.set` with the field that moved; when the write came from an event,
   one `state.cause` line naming it; then `sync()`.
5. **`sync()`** renders and compares each block against what **this call** was last sent under
   that name: one `prompt.set <name>` per block whose text differs (a block never sent counts as
   empty, so an empty block is never sent), then `tools.set` only if the visible list differs.
   Re-sending identical text is a cache miss for nothing.
6. **A tool call** — the SDK routes it to the instance serving that call; unknown call, unknown
   tool and a failed tool all come back as one `tool.result` carrying `error`, because a turn that
   never gets one waits forever.
7. **An outside fact** — `dispatch.ts` checks the **pair** (name, source) against `static events`.
   An event declared `from: ["app"]` that arrives from a browser is somebody else's event with our
   name on it, and the hook never sees it (one warning per call and name, not one per second).
   Events run **one at a time, in wire order**, so `call.cause` names the event actually running.
8. **`call.ended`** → the listeners are dropped, `onEnd` runs, `this.call` is cleared.
9. **`call.attached`** → a call handed to this process mid-conversation (another process drained
   or died, or the gateway restarted): `adopt()` builds the instance, `restore()`s the state the
   gateway sent, runs no `onCall`, and sends the whole prompt and the tools. A call this process
   already serves keeps its instance and sends its whole prompt again.

## 9. `@pinecall/agents/client` — the socket alone

A second, smaller door for an app that has its own way of deciding what to answer: no `Agent`
class, no view, no CLI. It knows two things — the wire (`src/wire/`) and `ws`.

- **Registration is memory, not a database.** `open()` runs again on every reconnect. Many sockets
  may hold one agent at once; a call that named no app goes to the **newest** registration that
  takes unclaimed calls. A call is the AGENT's, not the socket's: when its socket leaves, the gateway
  hands it to another socket holding the agent, or keeps it for the next one, with `call.attached`.
  That is what makes a rolling deploy work and what makes `pinecall chat` a console: it registers
  with `takesUnclaimed: false`, its caller socket names `?app=<its own id>`, and it adopts nothing.
- **A drain is the other close that is not retried.** `pc.drain()` sends `agent.drain` for every
  agent (answered by `agent.draining`: how many calls were `handed` and `parked`), stops dialling
  back, and waits for the tools running to answer, up to `toolsMs`; `close()` follows.
- **A stop is the one close that is not retried.** Every other close is a blip and is redialled
  with jittered backoff for ever. An `error` coded `stopped` for no agent — a member of the org
  pressed Stop (`POST /v1/apps/{app}/stop`) — closes the connection for good and is handed to
  `onStopped`; the serve entry prints it and exits. An `error` coded `killed` on one agent — an
  admin killed it (`POST /v1/agents/{slug}/kill`) — drops that agent from the ones the client
  declares: the socket stays, a reconnect leaves it out, and the others go on. `agent.register` names the machine (`host`),
  so the gateway's list of processes (`GET /v1/apps`) says where each one runs.
- **A socket may answer the console instead of serving calls.** `answersDev: true` registers it as
  the one the console's dev verbs go to (with `takesUnclaimed: false` it takes no call), and it
  sends no `agent.configure`: a registration inherits the newest holder's declaration, which one
  sent from here would replace. `pc.onEntries` hands over every entry as the gateway wrote it, in
  snake_case and before any agent takes it.
- **Three commands are awaited** (`agent.register` → `agent.registered`, `agent.configure` →
  `agent.configured`, `agent.drain` → `agent.draining`), each answered by the event it lands as or by an `error` naming its id.
  Everything else is fire-and-read-the-log.
- **The log is read, never invented.** `observe()` and `history()` fold entries with the wire's
  reducer, so the runtime's golden log reduces to the same state here as there.
- **It reads nothing from the environment.** `new Pinecall({ url, apiKey, env? })` is given all
  three; `env: "production"` names production for a person's key (`pinecall-env`, `signed.ts`),
  and a server's token needs none. With `mount` from `@pinecall/agents`, that is how an app runs the agent
  inside its own server instead of under `pinecall start` (`docs/production.md`).
- `client/testing/` is the same surface with no network: a `FakeGateway` an app's own tests mount
  against, and a log nobody stored.

## 10. The CLI

The CLI is `../../cli`, a package of its own in this repository, and it never loads a class. It
reaches this package in two ways only: it imports `@pinecall/agents/client` and
`@pinecall/agents/wire`, and it starts `@pinecall/agents/serve` in a child process, resolved from
the tenant project's own `node_modules` — so the framework that serves an agent is the version the
project pinned, not the CLI's. The child's contract is `src/serve/` (§2): its door from `PINECALL_URL`, `PINECALL_KEY` and
`PINECALL_ENV`, `--events` on stdout, a drain when its stdin ends. Every verb is that package's
`docs/the-cli.md`.

## 11. The page

**The console is a folder of its own**: `../../console`, one browser program each instance of
the gateway serves — production's at its URL and the sandbox's at its own. It lived here while
`pinecall serve` put it on a laptop; that verb is gone and so is the page. What it is, screen by
screen, is `../../console/docs/the-console.md`, and how it is built is that folder's
`CLAUDE.md`.

What answers a console's dev verbs is the CLI's companion socket, beside the agent's process;
`view.render` alone is answered here, by the agent's serve entry, whose class draws the panel. The
page imports neither: it asks the gateway, and the gateway asks the app.

## 12. LiveKit: where it is, and where it is not

The runtime is built on livekit-agents. **This package is not**, and nothing in it imports
LiveKit: the page's rooms went to `../../console`, and `simulate --listen`'s speakers to the
CLI. The class, the views, the call, the bridge and the client know only the wire. A tenant never
imports LiveKit, and the class does not know it exists: `call.room` is reduced from entries, and
`room.invite` is a command, not an SDK call.

## 13. The import table, and the rules of the tree

`test/the-imports.test.ts`. Read top to bottom it *is* the architecture; a line nobody uses is a
line the test deletes.

| part of `src/` | may import |
|---|---|
| `wire/` | `zod` |
| `client/` | `wire`, `ws` |
| `agent/` | `call`, `views`, `wire`, `oxc-parser`, `zod` |
| `call/` | `agent`, `wire` |
| `views/` | `agent`, `wire` |
| `runtime/` | `agent`, `call`, `views`, `client`, `wire` |
| `serve/` | `agent`, `call`, `views`, `runtime`, `client`, `wire`, `tsx` |
| `src/index.ts` | `agent`, `call`, `views`, `runtime` |

`test/the-wire.test.ts` holds the SDK to its wire: every command of the registry is sent by the
file its table names (or is said to be nobody's here: dialling, the desk's verbs, the gateway's
own), and every event is folded by the file its table names or ignored with a reason. A wire entry
added without a row fails there, by name.

`test/the-tree.test.ts`, over `src/` and `test/`: no `.ts` at the repo root, no file
over **400 lines**, every file opens with a line saying what it is, and no two names in one
directory one letter apart (a Levenshtein pass over the basenames).

`test/index.test.ts` and `test/client/index.test.ts` pin the two public surfaces **by name**.
Adding an export means editing a list on purpose — which is the point.

## 14. The wire

The wire is the runtime's, and this package keeps what it speaks of it in `src/wire/`: the types
(`Entry`, `Event`, `Command`, `ToolSpec`, `AgentConfig`, `Camel<T>`, `CallScore`, …), the zod
schemas a frame is checked against, `eventOf` / `toCamel` / `isEventType`, and the log reducer
(`apply`, `initialState`), and nothing the package does not use. `EPHEMERAL_EVENTS` and
`TERMINAL_EVENT` say which entries are not durable and which one seals a log. No package of the
runtime's is read.

`test/wire/golden/` is the runtime's golden call log and the state it folds to, copied from its
`tests/wire/golden/`; `test/wire/the-log-folds-as-the-runtime-folds-it.test.ts` holds the reducer
to them, and the CLI's `test/runs/candidate.test.ts` reads the same log. A change of the runtime's wire
moves `src/wire/` and these two files by hand, in the same change.

## 15. The five rings, and where each of them runs

| ring | what it asks | where it runs |
|---|---|---|
| 0 | does the class behave? | `vitest`, in the tenant's own repo. No network, no key, no model — `@pinecall/agents/client/testing` gives it a gateway that is not there |
| 1 | does the agent hold its goldens? | `pinecall test`: the class served by a process this terminal starts (its language's serve entry), the conversations driven and judged by the gateway (the judges, the keys and the log are its) |
| 2 | does it hold on a real line? | `pinecall simulate --voice`: a model plays a persona in a room, read out in an ElevenLabs voice the agent does not have, in the agent's language, and waiting for the greeting before it says anything. `pinecall test --voice` sends the same goldens spoken, to `POST /v1/evals/run` with `voice: true` |
| 3 | what does one real call score? | `pinecall eval <call-id>`: one call re-evaluated by the runtime's code checks |
| 4 | what did every call score? | `call.score`, written by the runtime at hang-up with nobody watching; read here by `runs drift`, `runs promote` and the console's Evals screen |

The nightly is the repository's (`.github/workflows/nightly.yml`): rings 1 and 4 on real money,
against `https://cloud.pinecall.io`, driving this package's example and the Ruby SDK's.

## 16. Packaging: one distribution, no build between a change and a test

- `package.json` `exports` point at **`src/`**; `publishConfig` swaps them for `dist/` at publish
  time. So this checkout — and the example, which resolves `@pinecall/agents` through
  `node_modules` like any customer — imports the sources. Nothing is aliased and nothing is
  path-mapped anywhere: a path mapping would hand the serve entry a second copy of the framework.
- **The doors out:** `@pinecall/agents` (the framework and `mount`), `@pinecall/agents/client` (the
  socket alone), `@pinecall/agents/serve` (the entry the CLI starts), `@pinecall/agents/wire` (the
  runtime's shapes, which the CLI reads too), `@pinecall/agents/tsconfig.tenant.json` (the compiler
  flags an agent needs, so a tenant writes none) — plus `@pinecall/agents/views/jsx-runtime` for the JSX transform, `@pinecall/agents/panels` for the tags
  a `@view` is written in, and `@pinecall/agents/client/testing`.
- **Three tsconfigs:** `tsconfig.json` builds `dist/`; `tsconfig.lint.json` checks `src` and
  `test`; `tsconfig.tenant.json` is the
  preset a tenant extends (it carries `experimentalDecorators`, because oxc implements only the
  legacy decorators today — the day it ships the TC39 ones the flag leaves the preset and no
  tenant file changes — and `jsx: react-jsx` with `jsxImportSource: @pinecall/agents/views`). Those two
  facts are what let one `agent.tsx` carry `@tool` methods and a JSX `render()` at once: tsc, oxc
  and tsx each take both from the preset, and a tenant adds nothing. The one thing `.tsx` costs is
  the angle-bracket cast — `<Slot>row` is JSX there, so a class that wants one writes `row as Slot`.
- **Nothing here is a browser program any more**: `scripts/build` is `tsc` into `dist/`, and the
  page is built in `../../console` by the runtime's `scripts/console`, which copies it into the
  gateway as package data.
- `scripts/check` is build → lint → test, in that order, for the package and for every workspace
  package; CI runs exactly that.
