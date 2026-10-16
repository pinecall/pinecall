# Changelog

Every change a person using this gem would notice. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers and tags are the
maintainer's call.

## [0.11.1] — Released with every other package (2026-10-17)

- Nothing of the Ruby SDK changed: published at 0.11.1 with every other package.

## [0.11.0] — Released with every other package (2026-10-16)

- Nothing of the Ruby SDK changed: published at 0.11.0 with every other package.

## [0.10.1] — Released with every other package (2026-10-14)

- Nothing of the Ruby SDK changed: published at 0.10.1 with every other package.

## [0.10.0] — One repository, one version (2026-10-12)

- Published from [pinecall/pinecall](https://github.com/pinecall/pinecall) with every other
  Pinecall package, at the one version they all carry from here on. Nothing an app
  requires changes.

## [0.0.8] — The wire reads evals.spent, call.started.expects and call.summary.run (2026-10-11)

- The wire reads `evals.spent` (what the harness asked a model — a judge tried, personas
  written, a case group diagnosed — its evals counted), `call.started.expects` (what a simulated
  caller expects, replacing `accepts_when`/`declines_when`), a
  `call.summary`'s `run`, and `credits.exhausted` for every quota the runtime refuses for —
  `hosted_apps`, `evals`, `simulations` and `budget_usd` were missing. Needs runtime 0.1.46.

## [0.0.7] — Every judge is a model's answer, and the class names the judge's model (2026-10-10)

- `judge "<vendor>/<model>", builds:, options:`: the model the agent's calls are judged on, over
  the org's choice and Pinecall's. On a key of the org's own — a local model through
  `options: { base_url: "…" }` among them — its evals are never billed.
- The wire reads what the runtime now writes: a judge's `na` and `classified` answers with their
  `choice` or `score`, `call.score`'s `evals` and `own_key`, and `call.summary`'s `simulated`.

## [0.0.6] — A greeting is words or :improvise, a hangup is words or true, and the ears choose who ends the turn (2026-10-10)

- `greeting "…"` (said as written), `greeting :improvise` (the model opens on its prompt) and
  `greeting improvise("…")` (with an instruction); `interruptible: true` for an opening the caller
  may cut short, which by default they cannot. The `say:` / `reply:` keywords are gone.
- `hangup "…"` (when, in your words) or `hangup true` (whenever the model judges); `when:` is gone.
- `stt "…", end_of_turn: :stt | :livekit | :smart_turn`: who says the caller's turn is over, as
  @pinecall/agents 0.9.26 says it. Needs runtime 0.1.43.

## [0.0.5] — The class declares its voice, its models and the rest, and wins (2026-10-10)

- **A class declares its environment again, and it wins over the settings.** Class macros `voice
  "<vendor>", "<id>", model:`, `llm "<vendor>/<model>", temperature:`, `stt "<vendor>/<model>"`,
  `language`, `greeting`, `hangup`, `turn`, `says`, `hears`, `knowledge`, `docs`, `memory` and
  `record`, sent on `agent.configure`. A field the class declares is not read from the settings,
  the console shows it "set by the class", and `pinecall agent set` of it is refused. Needs runtime
  0.1.42.
- `builds:` and `options:` on `voice`, `llm` and `stt`: a class of the vendor's plugin and its
  keyword arguments (`llm "openai/gpt-5.4-mini", builds: "responses.LLM", options: { use_websocket:
  true }`), only on the org's own key for the vendor. The refusal that named a CLI verb is gone.

## [0.0.4] — A tool announces itself (2026-10-09)

### Added
- **`tool announce: "Let me check the agenda."`**: what the agent says as the tool starts, when the
  model's turn said nothing itself; a turn that spoke and then called the tool is not announced
  twice. Needs runtime 0.1.11.

## [0.0.3] — A call runs on the day a golden pinned (2026-10-09)

### Added
- **`call.today` is the day `call.started` names when a golden pinned one** (`today`), so an agent
  resolves "on Monday" against the golden's day, as the model does; the day the call opened
  otherwise, as before. Needs runtime 0.1.10. `Pinecall::Testing`'s `call_started` takes `today:`.

## [0.0.2] — A refused registration is a sentence (2026-10-09)

### Fixed
- **A registration the gateway refuses is one sentence and exit 2** from the serve entry — a slug that
  belongs to another org, a key it does not take — instead of a stack trace and exit 1.

## [0.0.1] — The first release: an agent as a Ruby class (2026-10-09)

### Fixed
- **The tutorial prints the prompt the gem sends**: the framework's rules and the channel's words
  are in English, and the `<channel>` block was missing. Its `Pinecall::Client` example no longer
  needs `PINECALL_URL`, which `pinecall link` writes only for a gateway other than Pinecall's.
- **`pinecall start` drains a Ruby agent whole on Ctrl-C or a SIGTERM.** The CLI passes the signal on
  and closes the child's stdin together, and the serve entry took the second as "leave now": it
  closed the socket mid-drain, with tools still running. Only a second signal cuts a drain short,
  as in TypeScript; the drain line is printed. The serve entry no longer prints its own
  `answering on` line, which the CLI already says.
- **Leaving after the socket closed is quiet.** When the gateway's socket closed just before the
  drain was asked, `pinecall test` and `chat` ended with `Pinecall::NotConnected: agent.drain: the
  gateway is not connected`; a drain with no socket has nothing to hand over, and says so.
- **A judged call's score reaches the agent.** The runtime's `call.score` says which judge model
  gave it (`judged_by`), and the gem refused the field: `pinecall simulate --judge` and every
  judged call printed `CallScore has no field called judged_by` and dropped the score.
- **`pinecall start`, `chat` and `test` see a Ruby agent register.** The serve entry's lines went
  to a pipe's buffered `$stdout` and reached the CLI only when the process left, so every verb
  that waits for `agent.registered` gave up after 30 seconds. Each line is flushed now.
- **A voice call whose vendor fails over no longer stops the agent.** The runtime writes
  `vendor.switched` when a stage's fallback switches vendor, and the gem did not know the type: the
  socket raised `unknown event type` mid-call. `vendor.switched` and `spend.unusual` are in the
  wire now, both left to `call.on` and `client.on_any`.

### Changed
- **Breaking: the language is the world's, and the prompt says how to write for the channel** — as
  the TypeScript package's 0.9.19. `language :es` is refused at load (`pinecall agent set
  --language es`); the rules and protocols are English for every agent and tell the model to answer
  in the caller's language; the `identity` block gains `<channel>`: speech, a website's Markdown, or
  WhatsApp's formatting, by the call's channel and `medium`. `channel_rules false` leaves it out.
  `call.started.medium` is in the wire (the runtime sends it from this release on, and a gem without
  it refuses every call), on `CallWorld#medium` and `Client::Call#medium`; serve's `prompt` takes
  `--medium`. `language` is no longer in `agent.configure`.
- **Breaking: no CLI, no console, no executable.** The verbs are the one `pinecall` CLI's (npm),
  the same for a Ruby project as for a TypeScript one, in the same layout
  (`agents/<slug>/agent.rb`): for `prompt`, `chat`, `test` and `start` it runs `Pinecall::Serve`.
  `exe/pinecall`, `bin/pinecall`, the vendored console and `pinecall ui`, `run`, `whoami`,
  `knowledge`, `memory`, `remember` and `keys` are gone, and so are `Client#knowledge`,
  `#memory_of`, `#memory` and `#provider_keys`: those doors are the CLI's verbs.
- **Breaking: `Pinecall::Client.new` reads nothing from the environment.** It takes `url:`,
  `api_key:` and `env:` (`"production"` names production for a person's key); the serve entry
  reads `PINECALL_KEY`, and no other key variable is read anywhere.
- **Breaking: a call opens in the state its `call.started` carries.** `Pinecall.mount` takes no
  `opening:`: the state a golden, a persona or a chat's `?state=` asked for rides the call, and the
  bridge applies it after `on_call` and before the first render. `Testing::Gateway#call_started`
  takes `state:`.
- **The wire is the gem's own.** The gem keeps the runtime's wire it speaks in
  `lib/pinecall/wire/` (`Pinecall::Wire`: the shapes, the validator, the codec, the reducer), held
  to the runtime's golden call log; `Pinecall::Protocol` is `Pinecall::Wire` and `ProtocolError` is
  `WireError`.
- **Breaking: the class is code, the world is environment.** A class declares the contract — its
  `language`, `state` and `stage`, its `tool`s, `accepts`, its view — and nothing it runs on.
  `voice`, `llm`, `stt`, `greeting`, `hangup`, `says`, `hears`, `memory`, `record`, `knowledge`
  and `docs` in a class body now raise `DeclarationRefused` when the class loads, before a prompt
  is printed or a gateway is knocked at, naming the verb that sets each instead:
  `` `voice` is the world's now, not the class's: pinecall agent set --voice <name> — remove it
  from the class``. What to run instead, per world, with the Node CLI or the console's Settings:
  `pinecall agent set --voice | --llm | --stt | --greeting '…' (or --reply '…') | --hangup '…' |
  --record on|off`, `pinecall lexicon add <word> --say '…'` and `pinecall lexicon hear <word>`,
  `pinecall memory policy --remember '…' --forget '…'`, `pinecall agent knowledge edit` for what
  the agent knows by heart, and `pinecall docs attach <base>` for the base it searches. None of
  them travels on `agent.configure` any more, and the `knowledge` block is the gateway's to fill:
  the class sends nothing for it, so `pinecall prompt` prints it empty.
- **A class declares no doors.** `phone`, `whatsapp` and `web` still load and are read by nobody:
  `agent.register` carries no routes from the class, and nothing counts them. A
  number is pointed at an agent with `pinecall numbers import <+34…> --agent <slug>`, and every
  agent can be talked to from a page.

### Added
- **The console's panel: `panel "Cliente" do |who| … end`**, as the TypeScript package's `@view`.
  The block draws with the console's catalogue — `panel`, `rows`, `row`, `stat`, `table`, `badge`,
  `text` — and the nodes are the same JSON, drawn by the console's own parts. The gateway is told the
  panel's name; serve's `start` answers `view.render` with it, and refuses every other console verb
  as the TypeScript entry does. A class without one is the 404 the console falls back from.
- **`agent.on_dev { |verb, data| … }`** answers a console's ask (raise `DevRefused` to refuse with a
  status); without one an ask is a 501 saying this process answers none. It replaces the fixed "a
  Ruby agent draws no panel".
- **`client.on_connected`**, each time the socket is up and every agent on it registered.
- **`call.opt_out(note)`**: the caller's number joins the org's do-not-call list (`call.opt_out`).
- **`Pinecall::Serve`, the entry the one `pinecall` CLI starts a Ruby agent with**:
  `start --file --slug [--console] [--events] [--prod]` holds the agents (its door from
  `PINECALL_URL`, `PINECALL_KEY`, `PINECALL_ENV` alone; the wire entry by entry on stdout with
  `--events`; leaves draining on a signal or the end of its stdin) and `prompt --file --slug
  [--state field=json]… [--show-machine]` prints a prompt. `Pinecall.serve(klass, url:, api_key:,
  env:)` holds one inside your own Ruby process. The client gains `drain`, `on_entries`,
  `on_stopped` and the `pinecall-env` header, registers its machine as `host`, and answers a
  console's ask with `a Ruby agent draws no panel`. `docs/production.md` says how a server runs it.
- **A call handed over mid-conversation is served.** On `call.attached` (another process drained
  or died) the agent opens in the state the gateway kept, with no `on_call`; one this process
  already serves sends its whole prompt again. A call knows the code it claimed (`call.claimed`)
  and the eval run that opened it. `Testing::Gateway#call_attached(state:)`.
- **`examples/clinica_norte` is the TypeScript example's agent, in Ruby**, in the one CLI's layout
  (`agents/clinica-norte/`, `docs/clinica-norte/`, `test/clinica-norte/`): the same agenda —
  specialties, slots booked by id, a day resolved to a date — the same documents, the same three
  extraction cases and the same eleven goldens. `rake ring1` runs them through the CLI.
- A stage restored from JSON — a golden's, `call.started.state` — is the declared stage it names.
- **The whole call.** `call.transfer(to, mode:)` and `call.attention(reason, wait_s:)` block until
  the log answers (a `Transferred`, an `Attended`); `call.hold`, `unhold`, `dtmf(digits)`,
  `claim(code)` (then `call.claimed`) and `callback(number, at:, note:)` are one command each.
  `knowledge.search(query, k:)` — or `call.search` — searches the bases attached to the agent
  through the gateway, and a class that searches registers `uses_knowledge`. The view is rendered
  again on the caller's turn, on a claim and on recall, and reads `call[:claimed]`. The call ending
  answers every verb still waiting. `Testing::Gateway#finds` and `#searched` for ring 0.
- The wire reads `call.started`'s `worker`, which the runtime writes on every spoken call: until
  now a Ruby app refused a phone call's first entry.
- The wire reads `call.started`'s `state`, the state a call opens in when its opener asked for
  one, and `agent.register` may carry `answers_dev`. Nothing sends or reads either yet.
- **`pinecall remember [PATHS]`**, and `client.memory.extraction(slug, cases)` — the goldens
  the memory policy is held to, which is the write side and the half that persists. A case is one
  call already held (both speakers, in `said`), the facts memory already holds (`holds`), and what
  must come of the hang-up's one model call: which categories got a fact (`writes`), which never
  did (`never`), which values must not survive in any fact's text (`never_says`), and which held
  facts the call contradicted (`invalidates`) — its mirror included, so a model that supersedes
  whatever it touches is caught too. A case may `plants` sentences somebody tried to get into
  memory, and planting one IS the assertion that admission refuses it. Nothing asks a model whether
  two sentences mean the same thing: a category is your own word, a value is a literal, a
  supersession is an id. The class is mounted in this terminal, because the tool names admission
  refuses a fact for are the class's own declaration; the one
  model call per case runs in the gateway on the org's keys. Exits 1 when a case did not hold.
  `test/memory` beside the `agent.rb` by default; Clínica Norte ships three.
- `pinecall memory eval [GOLDEN] [--k N]`, and `client.memory.eval`: the other table's golden.
  A list of `{ "holds", "asks", "expects" }` — what memory holds about a question's contact, what
  the caller said, and the fact or facts that should come back — asked of `recall`, and `recall@k`
  and `nDCG@10` printed, computed by code with no model. No contact of the org is read or written:
  each question's facts go to a scratch contact and are deleted again, which is what makes the
  figures the real ranking. A fact answers when what came back CONTAINS what was expected, folded
  for case, accents and whitespace, because a fact is a sentence a model wrote. Names every
  question memory did not answer whole with what came back instead and exits 1 when anything did.
  Clínica Norte ships one of seven questions, eight or nine facts each.
- `pinecall knowledge eval [GOLDEN] [--base NAME] [--k N]`, and `client.knowledge.eval`: every
  question of a golden asked of the base, and `recall@k` and `nDCG@10` printed — computed by code
  with no model, so two runs answer the same numbers. Names every question it missed with what came
  back instead and exits 1 when anything did, so a base can be held to its golden in CI. Clínica
  Norte ships one. A base listing now names the embedder that wrote its vectors.

- The package itself: `Pinecall::Agent` (config on the class, state on the instance, `tool` above
  the method, the comment as the docstring), the ERB view resolved as `views/<slug>.erb`,
  `Pinecall.mount`, `Pinecall::Client`, and `pinecall/testing` — the gateway that is not there,
  which is what a ring-0 suite mounts against.
- The prompt as four named blocks in two regions: `identity` · `knowledge` · `tools` (static,
  cached), the history, `view` (dynamic). The bridge sends each block by name and only when its
  text changed. `Pinecall.render` returns `Blocks` (`[:name]`, `static`, `dynamic`,
  `instructions`); `pinecall prompt` prints one section per block. In a test,
  `call.block("knowledge")`.
- The wire: Ruby's side of it, generated from the same JSON Schema as the Python
  and TypeScript packages, with the log reducer proved against the same golden fixture.
- `sig/`: the public surface as RBS, checked by `rake rbs`.
- `examples/clinica_norte`: a whole agent, its view, and its own ring-0 suite.
- **A lookup is a tool result, never a piece of the prompt.** What memory kept from an earlier
  call and what the knowledge base returned no longer travel through the view: the platform runs
  its own `recall` and `search` tools and their answers reach the model as `tool_result` blocks,
  JSON, in the history — which is where both vendors say content from outside the conversation
  belongs (`runtime/docs/security/prompt-injection.md`). So a view is now the tenant's own prose
  and conditions and nothing else: the `memory`, `retrieved` and `knowledge` template tags are
  gone, and so are the tenant-declared blocks (`prompt static:`/`dynamic:`) and the render props
  that came with them. What a view may still do with memory is ask it a question —
  `remembers?("médico habitual")`, answered by the runtime — and say a sentence of its own about
  the answer.
