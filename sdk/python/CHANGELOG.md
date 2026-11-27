# Changelog

## Unreleased
- **`app.agent(Agent)`: an agent the app holds with no line**, for its flows: one they call, text or read with.
- **`await step.extract(text, Schema, agent=..., instructions=..., model=...)`: a model reads words into an object.**
  No call is opened; the answer is read into the pydantic model, and `ExtractRefused` says what refused it.

## 0.11.54 — Messenger and Instagram are channels an agent answers; a WhatsApp template from every surface, its words opening the conversation (2026-11-27)
- **Two channels: `messenger` and `instagram`.** A call's `channel` may be a Facebook Page's Messenger or the Instagram account
  linked to it; both are written (`medium` text), and each has the framework's own rules (`channelRules.messenger`,
  `channelRules.instagram`), which an agent may replace with its own.
- **`step.template` takes `text=` and `metadata=`.** `text`, what the template says once filled, opens the contact's conversation as its first turn, so their answer reaches the agent with those words before it; `Templated.call` is that conversation.

- **`step.template` sends a WhatsApp template from a flow.** `await step.template(visit["phone"], Reminder, "visit_reminder", language="en_US", variables=["Ana", "9:30"])` sends the template approved at Meta as the agent and answers a `Templated(sent, simulated, message_id, from_, refused, message)`. In the sandbox it is answered `simulated` and never sent. Needs a gateway at this release.

## 0.11.53 — a benchmark of your agent from one command: spoken calls placed by a callers service, a report that plays every call, and a gate for CI (2026-11-26)

- **The state a call opens in is the call's: every agent that takes it starts from it.** A golden's, a persona's or `?state=`'s state was set on the instance that answered and no other. A call passed to a teammate now sets it on the instance that takes it too, after its `on_call`, in the fields that class declares; so does a call that comes back to the agent that answered it, which found a new instance with none of it. What an instance changed before it passed the call on is still gone with it: `call.shared` is what outlives a pass.
- **`step.text` writes the first email of a thread** to an address: `step.text("ana@example.org", Reminder, subject="Your visit", instruction="Remind Ana of her cleaning.")`, its words given or left to the agent; `metadata` and `instruction` are `step.call`'s, for an SMS too.

## 0.11.52 — the callers an agent is tested with live in its test folder, beside its goldens; one Calls page lists every conversation (2026-11-19)

- **An agent's test callers live in `agents/<slug>/test/personas.py`, beside its goldens.** Every `own_persona(…)` at the file's top level is the agent's own, whatever its name, and `ON = ["in-a-hurry", …]` names Pinecall's that are on; the serve entry loads the file with the class. `personas = personas(…)` on the class still works where there is no such file, and `pinecall start` says once that their place is the file; a class with both is refused. `judges` stay on the class.

## 0.11.51 — live is somebody on the line and never a written conversation; Emails is a page of its own, with a mailbox's server and the org's template in an agent's channels (2026-11-19)

- Released with the runtime: nothing of this package changed.

## 0.11.50 — an agent answers email, each thread its own conversation, its replies set in the org's layout (2026-11-19)

- **The channel `email`**: a call's `channel` may say it, it is written (`medium: text`), and the built-in rules tell
  the model to write a whole email in one message; `channelRules` (`channel_rules`) takes `email` for the agent's own.

## 0.11.49 — a flow writes to somebody by SMS, and an open written conversation reads as open (2026-11-18)

- **`step.text(to, agent, words)`**: a flow has an agent send a contact one SMS first, from a number it answers SMS at (`from_`), and reads what it came to as a `Texted`: `sent`, the `call` it was said on, or what `refused` it.

## 0.11.48 — an agent writes first by SMS, and a person's message on a thread reaches the contact (2026-11-18)

- Released with the runtime: nothing of this package changed.

## 0.11.47 — an agent says the languages its callers speak, a channel takes the agent's own words, and a stop word ends the conversation on any gateway (2026-11-18)

- **`channel_rules` takes the agent's own words for a channel.** `channel_rules = {"whatsapp": "…"}` says how the agent writes there in place of the framework's own way, and every channel it leaves out keeps the framework's (`voice`, `chat`, `whatsapp`, `sms`); `False` still leaves the block out on every channel.

## 0.11.46 — a contact who texts STOP is written to no more, a written conversation opens on the one before, and the audio of an MMS is heard (2026-11-18)

- **`optOut` on a WhatsApp or SMS conversation**, and `call.summary` says an SMS conversation's `sms_segments`.

## 0.11.45 — a number answers the phone, WhatsApp and SMS at once, and SMS comes through Twilio (2026-11-18)

- **`sms` is a channel.** A call by SMS is written (`medium: text`), and the built-in rule tells the model to write plain, short text.

## 0.11.44 — a WhatsApp number of your own Meta app is heard and says where each reply stands, a simulated caller rings by phone, and a restarted process keeps its line (2026-11-18)

- `message.status`: where a WhatsApp reply stands (`sent`, `delivered`, `read`, `failed`), an event on its call.

## 0.11.43 — released with the runtime's setup on a Mac's own Ollama (2026-11-17)

## 0.11.42 — a machine of your own sets up from nothing, a refused call says why, and the night's retention runs again (2026-11-17)

- **A rule's judge reads what the call carried.** `app.rule("…")` adds a judge to every agent of the app; it read the
  call's words alone, so an amount the agent read out of a document broke a rule about where amounts come from. The
  judge now reads the call's evidence too (`reads=("evidence",)`: the documents searched, the tools' answers, the state).

## 0.11.41 — the CLI answers in colour, an assistant connects by an address, and a dead worker's call goes on (2026-11-16)

- Released with the runtime: nothing of this package changed.

## 0.11.40 — a call hears the nearest voice, a simulated television is a real one, and a caller stops the agent by a model's word (2026-11-15)

- A class may declare `voice_isolation` (on unless `False`): whether a spoken call goes through the runtime's model that takes down the voices far from the caller.
- A class may declare `smart_interruptions` (on unless `False`): whether a caller speaking over the agent stops it by the runtime's model or by two words of the transcript.

## 0.11.39 — a terminal signs in again, a phone put down ends its call, and the console's call list is one row per call (2026-11-13)

- Released with the runtime: nothing of this package changed.

## 0.11.38 — a page's chat is written, a visitor keeps the conversation from page to page, and an app of one agent is one row (2026-11-13)

- **A page may be one environment's alone.** `app.page("site", only="sandbox")` keeps a guide or a demo to the
  sandbox: a deploy to production sends the app alone. `pinecall start` follows the same rule, and anything but
  `sandbox` or `production` is refused as the app is declared.

## 0.11.37 — an app's own page dictates, the widget's header is a menu, and a page going away ends its call (2026-11-13)

- **An app's page dictates on this machine too.** `pinecall start` answers `POST /pinecall/dictation` beside the
  page's ticket and its code, with your key and no captcha: the gateway's socket whole, as the deployed page's door
  answers it.

## 0.11.36 — a Python app names its agents by slug, and Brightside Dental is an example in every language (2026-11-13)

- **An agent is named by its slug.** A voice app's `app.py` imported its agents from `pinecall_agents.<folder>.agent`,
  a package only the loader makes: it ran, and no type checker could read it, nor could one agent import the teammate
  it passes a call to. A line's `answers`, `team` and `fallback`, a page's `answers`, what a line's function returns,
  `self.call.handoff` and a flow's `step.call` take the agent's slug, its folder's name, as well as its class:
  `app.line("+1 415 555 0134", "front-desk", team=["billing"])`. A slug no agent is served as is refused by name.
- **Brightside Dental, the voice app on pinecall.io's editor, is an example** (`examples/python/brightside_dental`):
  two agents, a team, a rule, a flow, and the clinic they share, the same app as the TypeScript and Ruby ones.

## 0.11.35 — a judge reads what the platform said as the platform's (2026-11-13)

- Released with the runtime: nothing of this package changed.

## 0.11.34 — the overflow promises a call back only where one is asked (2026-11-13)

- Released with the runtime: nothing of this package changed.

## 0.11.33 — a tool's answer follows what its app said, and the overflow speaks the agent's language (2026-11-13)

- **A file at the project's root that is no voice app says the way out.** `app.py` there is read as the project's
  voice app; one that is something else (a Flask app) is refused by a sentence that says so, and that another name
  frees it.

## 0.11.32 — a passed call is answered at once, and the doctor reads a cluster (2026-11-12)

- **A call passed to a teammate is answered by the teammate, at once**, as in TypeScript: what the transfer tool
  answers says the call is the teammate's, that nobody is left to connect the caller to, and to reply to what they
  last said. Under the words before, a small model said "one moment while I connect you" and waited.

## 0.11.31 — a voice app, and @agent says what an agent is (2026-11-12)

- **A voice app, as in TypeScript:** `app.py` holds `voice_app(…)`: lines with a greeting, a team (`takes`) the call
  passes between, a line that chooses who answers, rules every agent keeps, `silence`, `on` for what the app hears,
  and a page of its own (`app.page("ui/dist")`).
- **Flows:** `@flow("…")` on an `async def (input, step)`: sleeps, calls, waits and effects kept by the gateway, so a
  run outlives the process. `app.on(name, flow)` starts one.
- **Tasks:** a tool asks the caller for what it lacks with `self.ask(GetEmail)`; `task(…)` makes one.
- **The caller's screen:** `screen()`, `part(…)`, `scenes`, `@tool(shows=…)`, `self.call.show(…)`.
- **An agent declares its `timezone`.**

- **The wire reads `stage.changed`**: the agent's settings name another vendor, model or voice for a stage of a live
  call. The model and the voice run from its next turn; the ears wait for the next call (`applied` false).

## 0.11.30 — an app is written whole in its class (2026-11-09)

- **A class declares its monitors:** `monitors`, each a number of its calls and the line it fires across.

- **A tool may be `quiet`:** a move on the caller's screen that runs as the model calls it and asks for no answer, as
  in TypeScript.

- **A class may declare several knowledge bases:** `bases`, in place of `docs`.

- **A tool says more:** `@tool` says `delayed=` (with `delayed_after=`) and `failed=`, as a Studio tool does.

## 0.11.29 — an agent may bear silence, leave a voicemail, and name its own fallbacks (2026-11-09)

- **A class declares the quiet, a machine and its fallbacks:** `silence_timeout`, `idle`, `voicemail`, `stt_fallbacks`
  and `tts_fallbacks`, each over the agent's settings.
- **Docs: an app is set by its code.** The CLI and the console no longer write a code agent's settings, so the guides
  declare the voice, the knowledge, the base it searches and the memory policy on the class.
- **The wire reads `turn.detection`**: who ends the caller's turn on a spoken call (the ears, livekit's detector or
  Smart Turn), its model, and the least silence it waits. Written once after `call.started`.

## 0.11.28 — the wire reads vendor.failed and org.quiet (2026-11-05)

- **The wire reads `vendor.failed` and `org.quiet`, and `credits.exhausted` carries `calls`.** A vendor that failed a
  call, a newborn org with no call that went well, and the calls holding an org's seats when the calls-at-once limit
  refused: the gateway's, read off the log, nothing for an app to fold.

## 0.11.27 — released with the CLI's tilde (2026-11-04)

## 0.11.26 — released with the CLI's output review (2026-11-04)

## 0.11.25 — the class owns its judges and callers as code, its docs, its melody, its look and its timeouts (2026-11-04)

- **`hold` and `widget`** as class attributes: the hold melody — a file beside the class, shipped once the agent
  registers unless the gateway holds it already, the wait before it, or `"off"` — and how the widget presents the
  agent, fixed over the console. `Client.hold_audio` and `.upload_hold_audio` are the doors.

- **A class that declares `docs` pushes its folder.** Once the agent registers, every Markdown file under
  `agents/<slug>/docs/` is written into the declared base by path, the base's other files kept, once per process:
  `pinecall start` and a deploy need no `pinecall docs push`. `Client.push_knowledge` is the door.

- **`max_duration` and `llm_timeout`** as class attributes: the longest a voice call runs (minutes, or `"off"`) and
  how long a turn waits for the model's first word (seconds), fixed over the settings.

- **A class owns its judges and its personas, as code.** `judges = judges(on=["consent", …], own=[OFFERS_NEXT_SLOT])`
  names which of Pinecall's judges the agent's calls meet and the agent's own, each an `own_judge(name=…, asks=…,
  answer=…, choices=…, when=…, trigger=…, reads=…)`; `personas = personas(on=…, own=…)` the same for the callers
  `pinecall simulate` plays, each of its own an `own_persona(name=…, goal=…, style=…, …)`. `pinecall new` writes both
  in `agents/<slug>/harness.py`. Both reach the gateway on `agent.configure` (`judges`, `personas` on `AgentConfig`),
  the console shows them locked, and a wrong one, or two of one name, is refused when the agent registers, by a
  sentence that names it.

- **`agent.waiting` is read.** The runtime writes it when the agent's turn is over: every sentence of the reply
  played, every tool it called run. An app on an earlier version logged `unknown event type: agent.waiting` on every
  turn; this one parses it and leaves it to `call.on`.

## 0.11.24 — released with the dot's marked walk (2026-10-25)

## 0.11.23 — released with the dot's smaller face (2026-10-25)

## 0.11.22 — released with the dot's fix for phones (2026-10-25)

## 0.11.21 — released with the tutor's walks (2026-10-25)

- **The view's `resumed` is true on a call handed over mid-conversation**; it never was on a live call. (2026-10-24
  tools eval, P F3)
- **`remembers("…")` matches case aside**, as in TypeScript and Ruby: "usual doctor" is in "Usual doctor is Dr.
  Vidal.". (P F7)
- **`call.history.length`** (and `len(call.history)`), the count every SDK's page names. (P F4)

## 0.11.20 — released with the runtime's live readers (2026-10-24)

- Nothing of the Python SDK changed: published at 0.11.20 with every other package.

## 0.11.19 — released with the CLI's reload on save (2026-10-23)

- Nothing of the Python SDK changed: published at 0.11.19 with every other package.

## 0.11.18 — released with the runtime's settings fixes (2026-10-23)

- Nothing of the Python SDK changed: published at 0.11.18 with every other package.

## 0.11.17 — released with the runtime's wire fixes (2026-10-23)

- Nothing of the Python SDK changed: published at 0.11.17 with every other package.

## 0.11.16 — a failing view or hook fails its call, every write names its author, pii masked everywhere (2026-10-23)

- **A view that cannot be rendered fails its call**: the opening no longer stops half way (no state, no following)
  when the view raises; the call's log gets a `render.failed` line and the model keeps the view it had. (found by the
  2026-10-23 eval, B B8)
- **A hook that raises fails its call, not the rest of it**: the call's log gets a `hook.failed` line naming the hook
  (and the event) and the error, and the opening no longer stops half way when `on_call` raises. (found by the
  2026-10-23 eval, B B8)
- **Every state write carries its author on the wire** (`StateSet.cause`: tool and call id, event and entry, or hook
  `on_call`/`on_memory`), and `EventMeta.seq` is the log's seq of the entry (it was a per-call counter); the
  `state.cause` custom line is gone. (found by the 2026-10-23 eval, B B4)
- **A line logged in `on_call` lands on the call's log**, as `on_end`'s already did. (found by the 2026-10-23 eval, B
  B3)
- **The SDK sends `call.done` after the end hook, and registers `says_done`**, so the gateway's seal waits for what
  the hook logs before it seals the log. (found by the 2026-10-23 eval, S2)
- **`call.to`, `call.direction`, `call.caller` and `call.metadata`** (the token's, sealed). (found by the 2026-10-23
  eval, K F6)
- **`python -m pinecall.serve start` prints what the log keeps** (private values masked), says on stderr when an admin
  kills an agent (`Client.on_killed`), and the client no longer answers `end_call`. (found by the 2026-10-23 eval, A
  F3, J F3, R2)

## 0.11.15 — the serve entry registers as its host (2026-10-23)

- **The serve entry registers as `PINECALL_HOST` when it is set**, else as this machine's hostname (`Client.host`). A
  hosted app's runner names each host, and the gateway knows a release is serving by it, on a machine that runs
  several.

## 0.11.14 — released with every other package (2026-10-23)

- Nothing of the Python SDK changed: published at 0.11.14 with every other package.

## 0.11.13 — the wire knows `app.failed` (2026-10-23)

- **The wire knows `app.failed`, a feed event.** A hosted app that did not build, start or stay up: the org's alert,
  read by the console; an app acts on none of it.

## 0.11.12 — released with every other package (2026-10-23)

- Nothing of the Python SDK changed: published at 0.11.12 with every other package.

## 0.11.11 — released with every other package (2026-10-23)

- Nothing of the Python SDK changed: published at 0.11.11 with every other package.

## 0.11.10 — released with every other package (2026-10-22)

- Nothing of the Python SDK changed: published at 0.11.10 with every other package.

## 0.11.9 — released with every other package (2026-10-22)

- Nothing of the Python SDK changed: published at 0.11.9 with every other package.

## 0.11.8 — released with every other package (2026-10-21)

- Nothing of the Python SDK changed: published at 0.11.8 with every other package.

## 0.11.7 — The wire knows the feed's tool.ran, tool.failed and judge.broke (2026-10-20)

- **The wire knows the feed's `tool.ran`, `tool.failed` and `judge.broke`.** Each with only its call, agent and name
  (and seconds): the org's feed says a tool answered or failed and a judge found a call broken, never what it said.

## 0.11.6 — A tool's untyped parameter with a default takes the default's type (2026-10-19)

- **A tool's parameter with a default and no annotation takes the default's type.** `cantidad=1` reached the model as
  text to fill; an int, a float, a bool or a str default now types it.

## 0.11.5 — @realtime: a voice call's model that hears and speaks itself, beside the @llm (2026-10-19)

- **A voice call runs on a realtime model while a written call keeps the LLM.** `@realtime("xai/grok-voice-3.0",
  options={"voice": "eve"})` names the model the agent's voice calls (phone and web) run on alone, one that hears and
  speaks itself — no ears, its own voice — while the `llm` keeps answering its written calls. Its options run on the
  org's own key for the vendor; an `llm` that names such a model is refused at registration.

- **An agent an admin killed is declared no more.** An `error` coded `killed` on one agent (`POST
  /v1/agents/{slug}/kill`) drops it from the agents the client declares: the socket stays, the other agents go on, and
  a reconnect leaves the killed one out.

- **An agent no longer says it will check and then stops.** The first protocol every agent is given now says to call
  the tool in the same reply, that saying it is about to act does not act, and never to ask the caller to wait: once
  it stops talking nothing happens until the caller speaks. Open models said "Let me check the details of your order.
  Please wait." and ended the turn (2026-10-18).

## 0.11.4 — Released with every other package (2026-10-17)

- Nothing of the Python SDK changed: published at 0.11.4 with every other package.

## 0.11.3 — Released with every other package (2026-10-17)

- Nothing of the Python SDK changed: published at 0.11.3 with every other package.

## 0.11.2 — Released with every other package (2026-10-17)

- Nothing of the Python SDK changed: published at 0.11.2 with every other package.

## 0.11.1 — Released with every other package (2026-10-17)

- Nothing of the Python SDK changed: published at 0.11.1 with every other package.

## 0.11.0 — Released with every other package (2026-10-16)

- Nothing of the Python SDK changed: published at 0.11.0 with every other package.

## 0.10.1 — Released with every other package (2026-10-14)

- Nothing of the Python SDK changed: published at 0.10.1 with every other package.

## 0.10.0 — One repository, one version (2026-10-12)

- Published from [pinecall/pinecall](https://github.com/pinecall/pinecall) with every other Pinecall package, at the
  one version they all carry from here on. Nothing a server imports changes.

## 0.1.13 — The wire reads evals.spent, call.started.expects and call.summary.run (2026-10-11)

- The wire reads `evals.spent` (what the harness asked a model — a judge tried, personas written, a case group
  diagnosed — its evals counted), `call.started.expects` (what a simulated caller expects, replacing
  `accepts_when`/`declines_when`), a `call.summary`'s `run`, and `credits.exhausted` for the `evals` and `simulations`
  quotas. Needs runtime 0.1.46.

## 0.1.12 — Every judge is a model's answer, and the class names the judge's model (2026-10-10)

- `@judge("<vendor>/<model>", builds=…, options=…)`: the model the agent's calls are judged on, over the org's choice
  and Pinecall's. On a key of the org's own — a local model through `options={"base_url": "…"}` among them — its evals
  are never billed.
- The wire reads what the runtime now writes: a judge's `na` and `classified` answers with their `choice` or `score`,
  `call.score`'s `evals` and `own_key`, and `call.summary`'s `simulated`.

## 0.1.11 — A greeting is words or improvise, a hangup is words or True, and the ears choose who ends the turn (2026-10-10)

- `greeting = "…"` (said as written), `greeting = improvise` (the model opens on its prompt) and `greeting =
  improvise("…")` (with an instruction); `interruptible=True`, or `words("…", interruptible=True)`, for an opening the
  caller may cut short, which by default they cannot. The `{"say": …}` / `{"reply": …}` dicts are gone.
- `hangup = "…"` (when, in your words) or `hangup = True` (whenever the model judges); the `{"when": …}` dict is gone.
- `@stt(…, end_of_turn="stt" | "livekit" | "smart-turn")`: who says the caller's turn is over, as @pinecall/agents
  0.9.26 says it. Needs runtime 0.1.43.

## 0.1.10 — The class declares its voice, its models and the rest, and wins (2026-10-10)

- **A class declares its environment again, and it wins over the settings.** `@voice("<vendor>", "<id>", model=…)`,
  `@llm("<vendor>/<model>", temperature=…)`, `@stt(…)` and `@knowledge(path=…, text=…)`, and class attributes for
  `language`, `greeting`, `hangup`, `turn`, `says`, `hears`, `docs`, `memory` and `record`. A field the class declares
  is not read from the settings, the console shows it "set by the class", and `pinecall agent set` of it is refused.
  Needs runtime 0.1.42.
- `builds=` and `options=` on the three models: a class of the vendor's plugin and its keyword arguments
  (`@llm("openai/gpt-5.4-mini", builds="responses.LLM", options={"use_websocket": True})`), only on the org's own key
  for the vendor. One of these annotated as state is refused at class creation with how to declare it; the refusal
  that named a CLI verb is gone.

## 0.1.9 — The release CI refused for a format (2026-10-09)

- CI refused 0.1.7 and 0.1.8 for one file's format, so neither reached PyPI: this release carries both.

## 0.1.8 — A tool announces itself (2026-10-09)

- `@tool(announce="Let me check the agenda.")`: what the agent says as the tool starts, when the model's turn said nothing itself; a turn that spoke and then called the tool is not announced twice. Needs runtime 0.1.11.

## 0.1.7 — A call runs on the day a golden pinned (2026-10-09)

- `call.today` is the day `call.started` names when a golden pinned one (`today`), so an agent resolves "on Monday" against the golden's day, as the model does; the clock's day otherwise. Needs runtime 0.1.10.

## 0.1.6 — The first release: an agent as a Python class (2026-10-09)

- A frame sent from the loop could leave before frames a tool's thread had sent just before it. Every frame now leaves in the order it was sent, from any thread.
- `docs/tutorial.md`: forty minutes from an empty directory to an agent that answers from your documents and remembers who called. The README says what the package is and how to install it from git until its first release.
- `python -m pinecall.serve`: `PINECALL_LOG=debug` writes the package's log to stderr, timed; a gateway that refuses the registration is one sentence and exit 2, not a traceback.
- A call opens with its prompt before its state, and what memory recalled reaches the view as the recall lands, not behind the job running: the caller's first turn no longer waits on either.
- `pinecall.testing.load(file)`: an agent's class loaded as `pinecall start` loads it, its folder a package, for a test whose agent lives in a folder named by its slug.
- `examples/clinica_norte`: the TypeScript and Ruby example, in Python.
- `python -m pinecall.serve start|prompt`: the entry the one `pinecall` CLI starts a Python agent with. `pinecall.hold(Class, url=, api_key=)` holds one from a process of your own.
- `pinecall.testing.Gateway`: ring 0 — a class held as a call holds it, from a plain test, with no network and no key. `docs/testing-an-agent.md`, `docs/production.md`.
- `pinecall.bridge.mount(Class, client)`: a class held on a client, an instance of its own per call, opened with `on_call` and the state its opener asked for in one prompt, and from then on only the fields and blocks that changed. `on_memory` is called when memory is read or written.
- `self.call`, a `CallWorld`: the call's line, room and turns, and a verb per command — `say`, `reply`, `send`, `participant(…).mute()`, `invite`, `transfer`, `attention`, `hold`, `unhold`, `dtmf`, `claim`, `callback`, `opt_out`, `hangup`, `search`. A verb that waits answers with an `Answer`, awaited in an `async def` or `.result()` on a `def` tool's thread. The four hooks, `on_call`, `on_end`, `on_event`, `on_memory`, each a `def` or an `async def`.
- `Client.history(call=…)` and `Client.observe(call=…)`: a call's log, or an agent's own, as one page or as a stream, each entry with the state it folds to — the runtime's own reducer.
- `pinecall.Client(url, api_key, env)`: one socket to the gateway and the agents held on it — registered and declared again on every reconnect, each tool call answered with exactly one result, `drain()` to leave without cutting a call, `search(call, query, k)` for a call this process serves. It reads nothing from the environment.
- `@pinecall.panel("Ficha")`: the panel the console draws beside a conversation, a method `(self, who, draw)` that draws the closed catalogue (`panel`, `rows`, `row`, `stat`, `table`, `badge`, `text`) for a `Who`.
- `pinecall.render(agent, line)` and `show_prompt`: the prompt as four named blocks in two regions — `identity` (the class's docstring, the framework's rules, the channel's words), `knowledge`, `tools`, then the `view`. The view is a Jinja template, `views/<slug>.jinja` beside the class's file (or `view_template` on the class), with every state field in scope, `call`, `resumed` and `remembers("…")`. `docs/the-view.md`.
- `Agent.accepts = {"slot.released": ["app"]}`: the outside events an agent takes, and from whom (`app`, your backend; `participant`, a browser in the call). A sender that is neither is refused when the class is created.
- `docs/writing-an-agent.md`: the class, its config, the world's settings, state, the stage, tools, the events it accepts, and every refusal with its sentence.
- `@pinecall.tool`: a method the model may call, its docstring the description and its `Args:` section each parameter's. The parameters' types are the method's annotations (a `Literal` is an enum, a pydantic model a nested object), and what the model sends is checked and converted before the method runs. `stage=`, `when=`, `confirm=`, `preview=`, `pii=` and `timeout=`; a tool may be a `def` or an `async def`. A tool with no docstring, a parameter a model cannot fill by name, `pii=` naming no parameter, or a stage the class does not declare is refused when the class is created. `Agent.tools()`, `visible_tools()` and `run_tool(name, arguments)`.
- `pinecall.Agent`: a class's annotated fields are its state, opened per call at the value written (each call gets its own copy of a list); `state(pii=True)` or `state(visibility=…)` says who may see one; a public `@property` is a derived field; `stage: Literal[...]` is the stage. Once sealed, only a tool or a hook may write a field (`UnauthoredWrite`), and every write is recorded with its author. A class that sets one of the world's settings (`voice`, `llm`, `language`…) is refused when it is created, with the `pinecall` verb that sets it.
- `pinecall.wire`: every frame, event and command the gateway speaks, the runtime's own pydantic models; a frame that does not fit raises `pinecall.WireError`, which says what did not fit.
- The package's frame: `import pinecall` gives `PinecallError`, the root of every error it will raise, and `__version__`. Typed (`py.typed`), Python 3.11 and up. Nothing to write an agent with yet.
