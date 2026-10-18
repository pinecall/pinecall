# Architecture — `pinecall`, the Python package a tenant writes an agent in

What this package is, file by file, what each piece corresponds to in the TypeScript package
and in the Ruby gem it is brought over from, and where it meets the runtime (`pinecall/runtime`),
whose wire it speaks.

**The thesis.** An agent is an object. Fields are state. Methods are capabilities. Docstrings are
prompts. Types are contracts. The prompt is `render(state)`. Tools are the only thing that changes
state. The log is the truth.

---

## 1. Four repositories, one product

| repository | language | what it owns |
|---|---|---|
| `pinecall/runtime` | Python, on livekit-agents | the wire and its golden log; the real time: LiveKit rooms and SIP, STT/LLM/TTS, the gateway's doors, the log, the judges |
| `pinecall/agents` | TypeScript, Node ≥ 24 | the same class, for a team that writes TypeScript (`@pinecall/agents`) |
| `pinecall/ruby` | Ruby ≥ 3.2 | the same class, for a team that writes Ruby |
| `pinecall/cli` | TypeScript, Node ≥ 24 | the one `pinecall` CLI, for every language: it starts this package's serve entry |
| **`pinecall/python`** (this one) | Python ≥ 3.11 | the same class, for a team that writes Python |

The line between this package and the runtime is a **socket**. This package never imports the
runtime, never speaks HTTP to a vendor, never sees audio, and holds no key of its own beyond the
one the person typed.

## 2. The tree

```
src/pinecall/
  __init__.py                the door: what a stranger who types `import pinecall` may reach
  _version.py                the version, written once; a tag that says another is refused
  errors.py                  one root, `PinecallError`, and what is refused under it, by name
  agent.py                   `Agent`: the state's verbs (seal · snapshot · restore · start_in · collapse), the log
  _author.py                 who is writing right now — a `ContextVar`, per task, never a global
  _state.py                  the fields a class declares, `state(...)`, the stage, every write and who made it
  _config.py                 the world's twelve settings, refused at creation with the verb that sets each; the slug
  _tools.py                  `@tool`, the tools a class declares, what this state shows, running one
  _spec.py                   one tool as the gateway receives it: the arguments' model, its schema, what is refused
  _doc.py                    a docstring as the model reads it: one line, and what `Args:` says of each parameter
  _running.py                a tenant's method run under its author: a `def` or an `async def`, from a loop or not
  _accepts.py                the outside events a class accepts, and from whom; what reaches `on_event`
  _searching.py              whether a class searches its bases, read off its own file with `ast`
  _rules.py                  the framework's words: the rules, the protocols, the channel's; word for word TS and Ruby
  blocks.py                  the prompt as four named blocks in two regions: `Line`, `render`, `show_prompt`
  _view.py                   the Jinja view beside the class, rendered with the state in scope, tidied
  panels.py                  the console's panel beside a conversation: `@panel`, `Who`, `Drawing` and its nodes
  client.py                  `Client`: one socket, the agents on it, drain, the stop, `search` for a call
  _connection.py             the socket: the key at the door, full-jitter backoff, a ping, 1008 not retried, frames in order
  _agent_socket.py           one agent on the socket: register then configure, one tool.result per tool.call, dev asks
  _calls.py                  one live call as the app holds it, and the book of them
  _listeners.py              who is listening for what; a listener's failure said, never raised
  _endpoints.py              the gateway's doors from one base URL, and the key as a Bearer header
  call.py                    `CallWorld`: the call's line, room and turns, a verb per command; `Line`, `CallLine`
  _answers.py                what a verb that waits answers: `Answer`, settled by its entry, its ceiling, or the end
  _room.py                   who is in the room, a seat's two verbs, the turns
  bridge.py                  `mount`: one instance per call, its jobs in order, the state and only the blocks that moved
  testing.py                 `Gateway`: a gateway that is not there, for ring 0, from a plain `def test_…`
  serve/                     `python -m pinecall.serve`: the entry the one CLI starts — `start`, `prompt` — and `hold`
    _loading.py              its flags, the class in a file (its folder a package), a state field by field
    _starting.py             `start`: hold the agents named, the console's `view.render`, leaving
    _prompting.py            `prompt`: the page offline, and `--show-machine`
    _viewing.py              `view.render`, the one console verb an agent's own process answers
    _held.py                 what a process holds, and leaving: a drain, then the socket, once
    _lines.py                the wire entry a line for the CLI, a line for a person, the drain line
  observe.py                 reading a log: one page (`history`), or the stream from a cursor on (`observe`)
docs/                        the pages a person writing an agent reads: README · writing-an-agent · the-view
  py.typed                   the package is typed (PEP 561)
  wire/                      the runtime's wire, copied (§4)
    _names.py                the runtime's domain words the wire is written in: Json, Env, Channel, Medium…
    frames.py                `WireModel`, `Entry`, `Command`: closed models, read and written by wire key
    parts.py                 the shapes shared by events and commands: ToolSpec, ToolResult, Cost, the literals
    commands.py              every command, `COMMANDS` and `command_of`
    events.py                the agent's and the control's events, `EVENTS` and `event_of`
    events_call.py           a call's life: ringing to summary, a confirm, a supervisor
    events_turn.py           inside a conversation: the turns, a tool call, the state, an outside fact
    room.py                  who is in the room and what they publish
    metrics.py               livekit-agents' metric blocks, as they are
    scores.py                `call.score` and its judgments
    state.py                 the state a log reduces to
    reduce.py                the fold: a log's entries into that state, the runtime's own
tests/                       mirrors src/ one to one
  test_init.py               the door, pinned by name
  rules/test_the_tree.py     the ceiling, the opening line of every module, the mirror
  rules/test_the_wire.py     every command sent by one module or nobody's, every event folded or ignored with a reason
  wire/golden/call-log.json  the runtime's golden call log, shared with the TypeScript and Ruby packages
  fakes/project.py           a project of one agent written into a folder, as the CLI lays one out
  fakes/gateway.py           a gateway that is not there: a real socket, the lookup and log doors on 127.0.0.1
  wire/entries.py            entries of one made-up call, for the reducer's tests
../../examples/python/clinica_norte/   the TypeScript and Ruby example in Python, in the CLI's layout: its agenda, its Jinja view,
                             its ring-0 suite (`make examples`, part of check) and the same eleven goldens (`make ring1`)
scripts/wire_drift.py        `make drift`: what the runtime's wire says that this copy does not
```

## 3. What came from where

One row per piece, against the TypeScript package and the Ruby gem. Every row is a decision, not a
translation; the rows land with the code they describe.

| in `pinecall/agents` (TS) | in `pinecall/ruby` | here (Python) | why it is different |
|---|---|---|---|
| `test/index.test.ts` pins the exports by name | `sig/pinecall.rbs` and `rake rbs` | `__init__.py` re-exports `X as X` with `__all__`, `tests/test_init.py` pins the list | Adding to the surface means editing the pin on purpose. pyright strict reads `X as X` as a re-export. |
| one error root | `Pinecall::Error` | `PinecallError`, named by the door (`__module__ == "pinecall"`) | A traceback names what a person imports, not the private module that defined it. |
| `src/wire/`, zod schemas written by hand from the runtime's | `lib/pinecall/wire/`, a shape table and `Validate` | `wire/`, the runtime's pydantic models **copied**, `make drift` comparing them field by field | The runtime is Python: the same models are the same contract, and nothing is translated. |
| `class X extends Agent { patient = null }` and a `Proxy` on the constructor | `state :patient` | `patient: dict \| None = None`, an annotation; `__init_subclass__` puts a descriptor in its place | Python declares its fields the dataclass way, so the annotation is the declaration and the descriptor it becomes **is** the recorder: no Proxy, no macro. |
| `CONFIG_FIELDS`: four names skipped on every write | config declared on the class | a `ClassVar` (`slug`, `channel_rules`) or an unannotated class attribute is config; an annotation is state | Where the words are written says what they are, as in Ruby. |
| a getter on the prototype is a derived field | `state(:x) { … }` | a public `@property` is a derived field; a `cached_property` or a `_name` is a collaborator, never state | The decorator a Python reader already knows says which is which. |
| `Stages<"a" \| "b">`, a string type | `stage :a, :b` | `stage: Literal["a", "b"] = "a"`; a write outside the Literal raises `NotAStage` | The annotation is the declaration a tool's `stage=` is checked against, and pyright checks every write before it runs. |
| `AsyncLocalStorage` for the current author | `Fiber[:pinecall_author]` | a `ContextVar` | Per task, copied into the tasks it starts and into `asyncio.to_thread`: the same guarantee, in the standard library. |
| `ENVIRONMENT`: statics and `@voice`/`@llm`/`@stt` read into the declaration; an environment field on the probe instance refused | a class macro per field, stored on the class and sent | `@voice`, `@llm`, `@stt`, `@judge` and `@knowledge` (`_config.py`), the rest class attributes (`greeting` words or `improvise`, `hangup` words or `True`, read by `_opening.py`), read by `environment_of` into `config_of`; `__init_subclass__` refuses one annotated as state, and `knowledge` as an attribute, which would hide `self.knowledge.search` | A class attribute is the class's in Python, so the plain spelling is the declaration; only an annotation that is not `ClassVar` makes a field state. |
| the instance built by the constructor, fields set by the Proxy | `initialize` | the state is opened on its first use, not in `__new__` | A subclass with its own `__init__` needs no `super().__init__()`, and pyright strict sees one constructor signature. |
| `@tool({...})`, a decorator | `tool ...` above the `def`, caught by `method_added` | `@tool(...)`, or bare `@tool`; it marks the function, and the class reads its marks once, when it is created | Python has decorators; the class still refuses a bad tool on the file's import, not at the first call. |
| `docstrings.ts`: the class's source parsed with oxc | `Method#source_location` and the comment above | `inspect.getdoc`, one line up to the first Google section; a parameter's description from `Args:` | A docstring is part of the object in Python: no source to read, no parser. |
| parameter types read off the TypeScript signature | `params:` for the types, keyword names from `Method#parameters` | the annotations, through a pydantic model built per tool: its JSON Schema is what the model reads, and it validates what the model sends | One model is the schema and the check, so the two cannot disagree; a `Literal` is an enum, a `BaseModel` a nested object, `"3"` for an `int` is converted. |
| a tool takes positional arguments, mapped by name | keyword arguments only | any parameter a caller can pass by name; `*args`, `**kwargs` and positional-only are refused | A model fills a JSON object by name. |
| a `Promise` per tool call | a thread per tool call | an `async def` tool runs on the loop, a `def` one on a thread (`asyncio.to_thread`), both authored | A blocking CRM call in a tool never blocks the socket; a tenant writes whichever they have. |
| `static events = { name: { from: [...] } }` | `accepts "name", from: [:app]` | `accepts = {"name": ["app"]}`, a `ClassVar` on `Agent`, merged over the parents' | A class attribute is where Python writes what a class is; the base's `ClassVar` is what pyright reads a subclass's dict against. |
| `searching.ts`: oxc's AST for `this.knowledge` | `Searching`: Ripper's tokens | `_searching.py`: `ast.walk` for a call of `.search` on `knowledge` or `call` | The standard library parses Python; a word in a string or a comment is not a call. |
| `render()`, a method returning JSX | an ERB template beside the class, `views/<slug>.erb` | a Jinja template beside the class, `views/<slug>.jinja`, or `view_template` on the class | The same sentence — the object renders itself — in Python's idiom for a page of prose with holes in it. `StrictUndefined` makes a name nobody declared raise, as Ruby's `NameError`; `trim_blocks` and `lstrip_blocks` are ERB's `-%>`. |
| `this.remembers("…")` inside `render()` | `remembers?("…")` in the template | `remembers("…")` in the template | The same question, in Jinja's punctuation. The view never sees a fact, only the answer. |
| the channel read off `this.call` | off `call?` | off `Line(channel, medium, claimed)`, passed to `render` | The prompt needs three facts of the call, not the call: the bridge builds a `Line` from `call.started`, a test or `pinecall prompt` passes one, and with none it is a phone call's. |
| `@view(CustomerCard)`, JSX rendered to nodes | `panel "Cliente" do \|who\| … end`, drawing on `Panel::Drawing` | `@panel("Cliente")` on a method `(self, who, draw)`; `with draw.panel(…)` nests | A `with` block is Python's way of saying "inside this". The nodes are the same JSON, so the console draws them with the same parts. |
| `Promise`, one event loop; `ws` | one reader thread, a thread per call and per tool; `websocket-driver` | asyncio: a reader task, a task per tool call and per ask, one writer task; `websockets` | One loop, as TS. Frames leave in the order `send` was called: the loop and a tool's thread append to one deque, and only the wake-up crosses with `call_soon_threadsafe`, so a frame the loop sends never overtakes one a thread sent before it. |
| `#ask` and a `Promise` settled by the entry | `ask` and a `Thread::Queue`, the declaration on its own thread | `_ask` and a `Future`, the declaration awaited from the dialling task | A task waiting for an entry must not be the task reading them. |
| `fetch` for the lookup door | `Client::Rest` | `httpx` | Anthropic's SDK's choice for HTTP; one request per search. |
| `FakeGateway` (`src/client/testing/gateway.ts`) | `test/client/fake_gateway.rb` | `tests/fakes/gateway.py`, on aiohttp | A real socket, a real handshake, a real POST: the client is tested as it runs. aiohttp is a dev dependency only. |
| a `Promise` per waiting verb | a `Thread::Queue` per waiting verb, popped with a ceiling | an `Answer`: a `concurrent.futures.Future` an `async def` awaits and a `def` waits for with `.result()` | A tool is either, and the same verb must serve both; the future is thread-safe and the loop settles it. |
| `this.call`, set by the bridge | `call`, a method that raises outside a call | `call`, a property that raises outside one; `serving(call)` hands it | It never reads as a field, and a test hands an instance its call in one line. |
| the hooks, `async` | `on_call`, `on_end`, `on_event`, `on_memory` | the same four, each a `def` or an `async def`, under `hook:<name>` | A hook that reads your CRM may well be async; one that writes two fields need not be. |
| `inOrder`, a promise chain per call | a thread per call running its jobs | an `asyncio.Queue` per call and one task draining it | The opening, an outside event and the end of one call never overlap, which is what makes `call.cause` mean anything. Tool calls are not queued: they run side by side, as in both. |
| `onMemory`, declared and never called | `on_memory`, declared and never called | `on_memory(ops, call)`, called after a `memory.ops` re-renders the view | The hook says what it is for; here it is. |
| `src/serve/` — `main(argv, io)` | `Pinecall::Serve.main(argv, out:, err:, env:, input:, signals:)` | `pinecall.serve.main(argv, out=, err=, env=)`, run as `python -m pinecall.serve` | One CLI for every language: it never loads a class, so each SDK ships the entry that does and no executable. |
| `mount({pc})` and `new Pinecall` in your own process | `Pinecall.serve(Klass, url:, api_key:)` | `await pinecall.hold(Klass, url=, api_key=)` | A function named `serve` on the door would hide the module `pinecall.serve` the CLI runs. |
| `FakeGateway` for ring 0 | `Pinecall::Testing::Gateway`, threads it waits on | `pinecall.testing.Gateway`, a `Client` with no socket and a loop of its own it runs until the agent settles | A tenant's test is a plain `def test_…`: no pytest plugin, no `async`. |
| the wire's `ZodError` | `Wire::WireError` | `WireError`, a `PinecallError` | A frame that does not fit is the package's error like any other; its message says what did not fit. |
| `toCamel` / `toSnake` | nothing | nothing; `from_` is the one alias (`from` is reserved), as the runtime spells it | The wire is snake_case and so is Python. |

## 4. The wire

The wire is the runtime's (`runtime/pinecall/wire/`), and `src/pinecall/wire/` is a copy of
it, changed in four ways and no more:

- the runtime's domain words (`Json`, `JsonObject`, `Env`, `Channel`, `Medium`, `Direction`,
  `EventSource`, `QuotaName`) live in `wire/_names.py`, since this package has no `domain`;
- a PEP 695 `type X = …` is `X: TypeAlias = …`, the 3.11 spelling; the recursive `Json` is a
  `TypeAliasType`, which pydantic and pyright both read;
- the runtime's `DeclarationRefused` is `WireError`;
- `events.py` is three modules under the 400-line ceiling (`events`, `events_call`, `events_turn`);
  `events.py` re-imports the other two, so `EVENTS` is still one registry.

The reducer is the runtime's too: `wire/reduce.py` is `runtime/pinecall/log/reduce.py`'s fold —
`reduce`, `apply`, `initial_state` and their helpers — and none of what the runtime counts with it
(usage, medians, phone legs). `tests/wire/golden/call-log.state.json` is the state the golden log
folds to, and the fold reaches it from any cut, through a gap carrying a snapshot, and past an
entry this version cannot read (one line of `errors`, the fold going on).

Every model is closed (`extra="forbid"`): a key nobody declared means the gateway speaks a newer
wire than this package, and it is refused by name. A field this package needs lands in the
runtime's wire first, then here by hand. `make drift` reads both with `ast` — every class's
fields with their types and defaults, every alias, every registry key — and names what differs;
it needs `../../runtime`, so it is not part of `check`. `tests/wire/golden/call-log.json` is the
runtime's golden log, and every entry of it reads as the model its type names.

## 5. `Client` — the socket alone

A second, smaller door for an app with its own way of deciding what to answer: no class, no view.
It knows the wire, `websockets` and `httpx`.

- **Registration is memory, not a database.** `open` runs again on every reconnect. Many sockets
  may hold one agent; a call that names no app goes to the newest that takes unclaimed calls,
  which is what makes a rolling deploy work. A console's companion registers with
  `answers_dev=True` and declares nothing: a registration inherits the newest holder's
  declaration, and one sent from there would replace it.
- **Three commands are awaited** — `agent.register`, `agent.configure`, `agent.drain` — each by the
  entry it lands as, or by an `error` carrying its id (`<slug>:<type>`), within 10 s. Everything
  else is sent and read back from the log.
- **The key travels as `Authorization: Bearer`**, never in a URL; `env` rides `pinecall-env`.
- **It reads nothing from the environment.** `Client(url, api_key, env)` is given all three.
- **Every tool call gets exactly one `tool.result`** — an unknown tool and a tool that raised
  included — and every `dev.request` one `dev.answer`: a turn or an ask with no answer waits forever.
- **Reading a log.** `history(call=…)` reads one page and its folded state; `observe(call=…)`
  streams it as server-sent events, coming back from the last entry it saw after a drop with
  `Last-Event-ID`, and raises only when the stream never opened.
- **Leaving.** `drain` asks every agent to drain and waits for the tools running, up to 30 s; a
  stop from the org (`error` coded `stopped`, for no agent) closes the socket for good and goes
  to `on_stopped`; an agent killed (`error` coded `killed`, on that agent) is dropped from the
  agents the client declares, so a reconnect leaves it out and the others go on; `on_entries`
  hands over every entry as the gateway wrote it.

## 6. The bridge, step by step

`mount(Class, client, slug=…, takes_unclaimed=…, last=…)`, the only module that knows both the
class and the socket.

1. **At mount** — the class's tools and its declaration (the layout, `uses_knowledge`, the
   fields' visibility, the events it accepts, the panel's name) go to `client.agent`. Nothing is
   sent until `connect`.
2. **`call.started`** → a fresh instance, sealed, handed its `CallWorld`; every job of the call
   runs one at a time on a task of its own. `on_call` runs; `call.started.state` — the state a
   golden, a persona or `?state=` asked for — is applied after the hook so it is not overwritten,
   and before the first render so the model never reads a state the call was not in.
3. **The opening send** — `prompt.set` for each block that says something and `tools.set`, then
   one `state.set`: the caller's first turn waits on the prompt, and only the log reads the state. Only then does the bridge follow the instance, so a hook writing five fields
   is one prompt and not five.
4. **On every write** — `state.set` with the field that moved; when an outside event caused it,
   a `state.cause` line naming it; then the sync.
5. **The sync** renders every block and compares each with what this call was last sent:
   `prompt.set` only for a block whose text differs (a block never sent counts as empty),
   `tools.set` only when the visible list differs. A tool's thread and the loop both sync, under
   one lock.
6. **A tool call** runs on the instance serving that call — an `async def` on the loop, a `def`
   on a thread — and its answer is made JSON; a call no longer served answers with an error.
7. **An outside event** reaches `on_event` only from a sender the class accepts, one at a time,
   in order, its writes authored `event:<name>`. **The view again** on the caller's turn, on
   `call.claimed`, and on `memory.ops` at once, not queued behind a running job: the runtime holds
   the model's turn while the recall runs, and `remembers` answers from what it brought. The ops
   then go to `on_memory`.
8. **`call.ended`** → nothing renders for the call any more; `on_end` runs with the log still
   open, so a farewell line lands.
9. **`call.attached`** → a call handed to this process mid-conversation: an instance restored to
   the state the gateway kept, no `on_call`, the whole prompt sent. A call already served here
   keeps its instance and sends its whole prompt again.

## 7. The serve contract

The one CLI (npm `pinecall`) starts this package's entry for the two verbs that need the class:

```
python -m pinecall.serve start --file agents/x/agent.py --slug x [--console] [--events] [--prod]
python -m pinecall.serve prompt --file agents/x/agent.py --slug x [--state field=json]… [--channel c] [--medium voice|text] [--show-machine]
```

- **The door is the environment's, and nothing else:** `PINECALL_URL`, `PINECALL_KEY`,
  `PINECALL_ENV` (`--prod` forces production). Missing → one sentence, exit 2. Never an argv.
- **A refusal is a sentence, exit 2**: a file that cannot be served, a declaration refused, a
  gateway that refuses the registration (a slug of another org, a key it does not take).
- **`PINECALL_LOG=debug`** (or `info`) writes the package's `pinecall` logger to stderr, each line
  timed to the millisecond: a call's opening and every entry read, with how long after the
  gateway wrote it.
- **The `--events` printer is a thread of its own**, flushing each line: a slow reader of stdout
  never holds the loop that answers the calls.
- **The file is a module of a package that is its folder** (`pinecall_agents.<folder>.agent`),
  and the folder is on `sys.path`: a module beside the class is imported relatively or by name.
- **The slug is the folder's**, `--slug`; a class whose `slug = "…"` says another is refused, and
  one that says none is served as it, so its view is `views/<slug>.jinja`.
- **`--events`:** one line per wire entry, `{"type","agent","call","data"}` with `data` as the
  gateway wrote it, `agent.registered` first (the listener is in place before the socket opens),
  each line flushed.
- **`--console`:** `takes_unclaimed=False` — a console's process takes only the calls it opened.
- **Leaving:** SIGINT, SIGTERM or the end of its stdin (the CLI that started it is gone) drains,
  then closes; a second signal closes at once, and the end of stdin after a signal is not a second
  one (the CLI sends both); a stop from the org closes without draining. A signal handler only
  pushes onto a queue: the main task does the leaving.
- **The console's verbs** are answered by the CLI's companion; the one this process answers,
  `view.render`, is the class's panel (404 when it has none, 502 when it fails, 422 for an ask that
  names no conversation), and every other verb is refused 404 with the TypeScript entry's sentence.

## 8. The four rings

| ring | what it asks | where it runs |
|---|---|---|
| 0 | does the class behave? | `pytest`, in the tenant's own repo, with `pinecall.testing.Gateway`: no network, no key, no model |
| 1 | does the agent hold its goldens? | `pinecall test`: the one CLI, this package's serve entry holding the class |
| 2 | does it hold on a real line? | `pinecall test --voice` and `pinecall simulate --voice` |
| 3 | what does one real call score? | `pinecall eval <call-id>` |
| 4 | what did every call score? | `call.score`, written by the runtime at hang-up |

## 9. Packaging

- **A library, no executable.** The verbs are the one `pinecall` CLI's (npm); it starts
  `python -m pinecall.serve`.
- **PyPI `pinecall`, import `pinecall`.** The runtime's distribution is `pinecall-runtime`; the two
  are never installed in one environment.
- **Python ≥ 3.11**, checked on 3.11, 3.12 and 3.13. A tenant's server is not ours to upgrade.
- **The version is the repository's**, written into `src/pinecall/_version.py` by the root's
  `scripts/version` and read by hatch; a `v*` tag that says another number is refused before
  anything is built (the root's `release.yml` guard).
- **Typed:** `py.typed` ships in the wheel, and the release checks it is there.
- **`make check`** is ruff (every rule, and the format), pyright strict, deptry and the suite.
