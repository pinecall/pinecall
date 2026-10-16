# Changelog

## 0.10.1 — Released with every other package (2026-10-14)

- Nothing of the Python SDK changed: published at 0.10.1 with every other package.

## 0.10.0 — One repository, one version (2026-10-12)

- Published from [pinecall/pinecall](https://github.com/pinecall/pinecall) with every other
  Pinecall package, at the one version they all carry from here on. Nothing a server
  imports changes.

## 0.1.13 — The wire reads evals.spent, call.started.expects and call.summary.run (2026-10-11)

- The wire reads `evals.spent` (what the harness asked a model — a judge tried, personas
  written, a case group diagnosed — its evals counted), `call.started.expects` (what a simulated
  caller expects, replacing `accepts_when`/`declines_when`), a
  `call.summary`'s `run`, and `credits.exhausted` for the `evals` and `simulations` quotas. Needs
  runtime 0.1.46.

## 0.1.12 — Every judge is a model's answer, and the class names the judge's model (2026-10-10)

- `@judge("<vendor>/<model>", builds=…, options=…)`: the model the agent's calls are judged on,
  over the org's choice and Pinecall's. On a key of the org's own — a local model through
  `options={"base_url": "…"}` among them — its evals are never billed.
- The wire reads what the runtime now writes: a judge's `na` and `classified` answers with their
  `choice` or `score`, `call.score`'s `evals` and `own_key`, and `call.summary`'s `simulated`.

## 0.1.11 — A greeting is words or improvise, a hangup is words or True, and the ears choose who ends the turn (2026-10-10)

- `greeting = "…"` (said as written), `greeting = improvise` (the model opens on its prompt) and
  `greeting = improvise("…")` (with an instruction); `interruptible=True`, or `words("…",
  interruptible=True)`, for an opening the caller may cut short, which by default they cannot. The
  `{"say": …}` / `{"reply": …}` dicts are gone.
- `hangup = "…"` (when, in your words) or `hangup = True` (whenever the model judges); the
  `{"when": …}` dict is gone.
- `@stt(…, end_of_turn="stt" | "livekit" | "smart-turn")`: who says the caller's turn is over, as
  @pinecall/agents 0.9.26 says it. Needs runtime 0.1.43.

## 0.1.10 — The class declares its voice, its models and the rest, and wins (2026-10-10)

- **A class declares its environment again, and it wins over the settings.** `@voice("<vendor>",
  "<id>", model=…)`, `@llm("<vendor>/<model>", temperature=…)`, `@stt(…)` and `@knowledge(path=…,
  text=…)`, and class attributes for `language`, `greeting`, `hangup`, `turn`, `says`, `hears`,
  `docs`, `memory` and `record`. A field the class declares is not read from the settings, the
  console shows it "set by the class", and `pinecall agent set` of it is refused. Needs runtime
  0.1.42.
- `builds=` and `options=` on the three models: a class of the vendor's plugin and its keyword
  arguments (`@llm("openai/gpt-5.4-mini", builds="responses.LLM", options={"use_websocket": True})`),
  only on the org's own key for the vendor. One of these annotated as state is refused at class
  creation with how to declare it; the refusal that named a CLI verb is gone.

## 0.1.9 — The release CI refused for a format (2026-10-09)

- One example file was not as `ruff format` writes it, and CI refused 0.1.7 and 0.1.8 for it, so
  neither reached PyPI. This release carries both: a call runs on the day a golden pinned, and a
  tool announces itself.

## 0.1.8 — A tool announces itself (2026-10-09)

- `@tool(announce="Let me check the agenda.")`: what the agent says as the tool starts, when the
  model's turn said nothing itself; a turn that spoke and then called the tool is not announced
  twice. Needs runtime 0.1.11.

## 0.1.7 — A call runs on the day a golden pinned (2026-10-09)

- `call.today` is the day `call.started` names when a golden pinned one (`today`), so an agent
  resolves "on Monday" against the golden's day, as the model does; the clock's day otherwise, as
  before. The field needs runtime 0.1.10.

## 0.1.6 — The first release: an agent as a Python class (2026-10-09)

- A frame sent from the loop could leave before frames a tool's thread had sent just before it.
  Every frame now leaves in the order it was sent, from any thread.
- `docs/tutorial.md`: forty minutes from an empty directory to an agent that answers from your
  documents and remembers who called. The README says what the package is and how to install it
  from git until its first release.
- `python -m pinecall.serve`: `PINECALL_LOG=debug` writes the package's log to stderr, timed; a
  gateway that refuses the registration is one sentence and exit 2, not a traceback.
- A call opens with its prompt before its state, and what memory recalled reaches the view as the
  recall lands, not behind the job running: the caller's first turn no longer waits on either.
- `pinecall.testing.load(file)`: an agent's class loaded as `pinecall start` loads it, its folder a
  package, for a test whose agent lives in a folder named by its slug.
- `examples/clinica_norte`: the TypeScript and Ruby example, in Python.
- `python -m pinecall.serve start|prompt`: the entry the one `pinecall` CLI starts a Python agent
  with. `pinecall.hold(Class, url=, api_key=)` holds one from a process of your own.
- `pinecall.testing.Gateway`: ring 0 — a class held as a call holds it, from a plain test, with no
  network and no key. `docs/testing-an-agent.md`, `docs/production.md`.
- `pinecall.bridge.mount(Class, client)`: a class held on a client, an instance of its own per
  call, opened with `on_call` and the state its opener asked for in one prompt, and from then on
  only the fields and blocks that changed. `on_memory` is called when memory is read or written.
- `self.call`, a `CallWorld`: the call's line, room and turns, and a verb per command — `say`,
  `reply`, `send`, `participant(…).mute()`, `invite`, `transfer`, `attention`, `hold`, `unhold`,
  `dtmf`, `claim`, `callback`, `opt_out`, `hangup`, `search`. A verb that waits answers with an
  `Answer`, awaited in an `async def` or `.result()` on a `def` tool's thread. The four hooks,
  `on_call`, `on_end`, `on_event`, `on_memory`, each a `def` or an `async def`.
- `Client.history(call=…)` and `Client.observe(call=…)`: a call's log, or an agent's own, as one
  page or as a stream, each entry with the state it folds to — the runtime's own reducer.
- `pinecall.Client(url, api_key, env)`: one socket to the gateway and the agents held on it —
  registered and declared again on every reconnect, each tool call answered with exactly one
  result, `drain()` to leave without cutting a call, `search(call, query, k)` for a call this
  process serves. It reads nothing from the environment.
- `@pinecall.panel("Ficha")`: the panel the console draws beside a conversation, a method
  `(self, who, draw)` that draws the closed catalogue (`panel`, `rows`, `row`, `stat`, `table`,
  `badge`, `text`) for a `Who`.
- `pinecall.render(agent, line)` and `show_prompt`: the prompt as four named blocks in two
  regions — `identity` (the class's docstring, the framework's rules, the channel's words),
  `knowledge`, `tools`, then the `view`. The view is a Jinja template, `views/<slug>.jinja` beside
  the class's file (or `view_template` on the class), with every state field in scope, `call`,
  `resumed` and `remembers("…")`. `docs/the-view.md`.
- `Agent.accepts = {"slot.released": ["app"]}`: the outside events an agent takes, and from whom
  (`app`, your backend; `participant`, a browser in the call). A sender that is neither is refused
  when the class is created.
- `docs/writing-an-agent.md`: the class, its config, the world's settings, state, the stage,
  tools, the events it accepts, and every refusal with its sentence.
- `@pinecall.tool`: a method the model may call, its docstring the description and its `Args:`
  section each parameter's. The parameters' types are the method's annotations (a `Literal` is
  an enum, a pydantic model a nested object), and what the model sends is checked and converted
  before the method runs. `stage=`, `when=`, `confirm=`, `preview=`, `pii=` and `timeout=`; a
  tool may be a `def` or an `async def`. A tool with no docstring, a parameter a model cannot
  fill by name, `pii=` naming no parameter, or a stage the class does not declare is refused when
  the class is created. `Agent.tools()`, `visible_tools()` and `run_tool(name, arguments)`.
- `pinecall.Agent`: a class's annotated fields are its state, opened per call at the value written
  (each call gets its own copy of a list); `state(pii=True)` or `state(visibility=…)` says who may
  see one; a public `@property` is a derived field; `stage: Literal[...]` is the stage. Once
  sealed, only a tool or a hook may write a field (`UnauthoredWrite`), and every write is recorded
  with its author. A class that sets one of the world's settings (`voice`, `llm`, `language`…) is
  refused when it is created, with the `pinecall` verb that sets it.
- `pinecall.wire`: every frame, event and command the gateway speaks, the runtime's own pydantic
  models; a frame that does not fit raises `pinecall.WireError`, which says what did not fit.
- The package's frame: `import pinecall` gives `PinecallError`, the root of every error it will
  raise, and `__version__`. Typed (`py.typed`), Python 3.11 and up. Nothing to write an agent with yet.
