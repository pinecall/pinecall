# Changelog

## Unreleased

- **The open models' Ollama is 0.40.6.** Up to 0.32 Ollama re-read a model's whole vocabulary on
  every request before running it: ~0.25 s on the embedder and ~0.3 s on the thinking, every turn,
  longer than a spoken turn's lookup budget. On 0.40.6 an embedding takes ~10 ms. On a GPU
  (`infra/models/compose.yaml`) the CUDA kernels Ollama compiles on first use are kept in their own
  volume, and the embedder is warmed on every sentence length up to forty words when the stack
  comes up: a first call no longer waits 2 to 9 s for a kernel, and the 30B loads in 6 s instead of
  90 once the cache is there.

- **A spoken turn's search and recall are back before the turn ends, on ears that write no
  interims.** A lookup started on the first interim worth a query, and Whisper-family ears write
  none: every lookup started at the end of the turn and spent its 250 ms waiting on the embedder,
  so every turn of a call on open models logged `search did not run: no answer within 250 ms`
  (gpu.pinecall.io, 2026-10-18). The final transcript starts it too now, while the end of the
  turn is still weighed, once a turn as before. `PINECALL_VOICE_LOOKUP_BUDGET_MS` and
  `PINECALL_TEXT_LOOKUP_BUDGET_MS`, documented and never read, are the budgets the sessions wait.

- **A command the session refuses no longer cuts the call off from its app.** A `room.send` on a
  written call, or any command the session refuses, that reached the gateway serving the call through
  another gateway (the app's socket on one, the call on the other) raised out of the call's command
  listener and ended it: every command after it — `state.set`, `prompt.set`, `tools.set` — was lost in
  silence, the agent read a stale state and an old view, and a tool just run "did not happen". The same
  command on the socket's own gateway was answered as a refusal and the call went on, so it struck one
  call in two. The refusal is now answered to the app from either gateway, and the listener goes on.

- **A host advises an org what to run: `GET /v1/providers/advice`.** A stage at a time, from what
  the host has: an open model its own servers list (asked at the row's `base_url`, the
  OpenAI-compatible `/models`; the best measured one first), else a vendor it lends, else the org's
  own key, else one the org must bring; the judge and the caller are the host's. The box's operator
  also gets its machine (the card, the memory, what fits), where the row's servers run on it.
  `pinecall setup` on a project on another host asks this instead of reading the laptop. The
  machine's reading moved into the providers domain (`providers/service/machine.py`) so the
  gateway can answer it; the measured table is its constants.

## 0.11.4 — Noise never reaches the ears, the ears' loops never take the floor; a golden the vendor fails breaks alone (2026-10-17)

- **A breath or a sigh no longer reaches the ears.** livekit's Silero opens a segment for the ears on
  0.05 s of speech, and Whisper-family ears write each breath as words ("Thank you.", "Mm-hmm.",
  "We'll be right back."), which went to the model as the caller's. The session's detector now waits
  0.25 s: calibrated on a real call, where 0.05 s opened 8 segments for the caller's 4 sentences and
  0.25 s exactly the 4, while "Sí." and "No." alone (0.35 s of speech, the shortest measured) still open one.

- **The ears looping is never the caller.** On a fraction of a second of noise Whisper writes one
  phrase over and over ("I'm going to make sure that" forty times); it took the floor from the agent
  and the turn went to the model. A turn in which a phrase of three words or more comes three times
  running is dropped, whoever is speaking.

- **A golden's reply is the agent's answer, not the line that covers a tool's wait.** A `reply` step
  reads past the lines said around a tool — the announcement or `say` while a call has no output yet,
  and a line that leads straight into a call in the same answer ("Dejame chequear…") — to the message
  after them. Every model announces before its tools, so a turn's first message was the filler, and
  goldens broke on it whatever the model answered after.
- **`make deploy`'s live suite is back** (`tests/live`, lost when the packages became one repo): the
  console, the widget, the doors' refusals and the OpenAPI checked against the deployed domain.

- **A golden the model's vendor fails breaks alone.** A line the vendor answers with an error — an
  outage past livekit's retries, a content filter's refusal such as Gemini's `PROHIBITED_CONTENT` —
  breaks that golden at that turn (`t<n>.model`, with the vendor's words), and the run plays the next
  one; it used to end the whole run (`the run broke on the gateway`), leaving the goldens after it
  unplayed. Whatever stops a golden's play, the call it opened is ended (`error`, `platform`): one
  left open held the org's only sandbox line, and every run after it was refused `429`.

## 0.11.3 — Setup reads the machine and takes any open model, pinecall setup chooses it on a screen, the agent no longer hears itself, a visitor's room reaches a worker (2026-10-17)

- **The agent no longer hears itself.** On a web call the caller's audio passes WebRTC's echo
  canceller (AEC3, in livekit's SDK) fed with what the agent plays, before the VAD and the ears hear
  it (`session/echo.py`); a phone cancels its own. What the canceller leaves is caught by its words:
  while the agent speaks, a turn that is all one of the phrases Whisper writes on no speech ("Thank
  you.") is dropped like a backchannel, and until 1.5 s after it stops, a turn whose words are mostly
  the agent's own of the last seconds. A visitor on laptop speakers made the agent answer its own
  sentences in a loop (11 caller turns of which 2 were real); with both, 3 turns, all real, and the
  real barge-in still stops the agent.

- **`setup` takes any open model, per stage and per role.** `--llm local/<ollama tag>` and
  `--stt local/<whisper model>` name the model itself; `--judge` and `--caller` choose who judges a
  finished call and who plays the simulated caller (the thinking's model unless named); Ollama
  pulls each once and the row prices each at nothing. The local thinking's default is `gemma4:12b`,
  the model that took a message, answered from the documents and made small talk on a 24 GB card;
  `qwen3:4b` thought aloud and never called the tool.
- **`setup --recommend`** reads the machine — cards and their memory, Apple silicon, RAM, cores,
  Docker, an Ollama already running, which key variables are set — and prints the stack that fits
  it as JSON, from `cli/local/measured.json`: every measured model with whether it fits beside the
  ears, the voice and the embedder, and by how much it is short.

- **A visitor's call reaches a worker again.** LiveKit's webhook names its LiveKit `?world=`, as the
  chart and the operator's page say; the gateway read `?env=` and took every event as production's.
  On Linux, `local up` and `setup` make the gateway listen on every interface: Docker's
  `host.docker.internal` is the bridge's address there, and a gateway on loopback never heard LiveKit,
  so the playground's and the widget's rooms were never offered to a worker ("no worker is available").
  The local LiveKit's webhook names `?world=sandbox`.

- A judge's verdict and a simulated caller's line are given 30 s, not livekit's 10: a local model
  asked for a whole tool call takes longer now and then (gemma4:12b took 16.6 s on an L4), and the
  simulated call broke on it with nobody speaking after the greeting.

- **`setup` chooses a stage at a time**: `--stt`, `--llm` and `--tts` each `local` or a vendor of
  yours, `--turn` who ends the caller's turn (the ears' own, Smart Turn or LiveKit's), a vendor's
  key read from `<VENDOR>_API_KEY` or asked once; `--password-stdin` for the CLI's screen.
  `providers installed` lists what the build runs with no database. A plugin whose classes take
  no key (an open model in this process) runs on none.

- **A person's password set with no link.** `PUT /v1/members/{id}/password` for an admin of the org,
  `pinecall-runtime orgs password <org> <email>` for the operator (typed twice, or read from stdin);
  an invited person becomes active by it. `setup` makes the console's person with a password in
  both modes — typed at a terminal, drawn and shown once where nobody is asked — instead of an
  invitation link.
- **The grounded judge sees what a turn's lookup read.** A lookup writes no speech id, so the
  documents it found were filed under none and no agent turn carried them: the judge called facts
  from the base made up. They are now the next agent turn's.

- **A call with no judge on says so.** A panel with nobody on it was reported as "every judge run
  over this call failed"; it now says no judge is on for the agent and names `pinecall judges on`.
- **A simulated caller whose model answers in words is asked once more**, as a judge is, and the
  refusal says what the model said. A local model (gemma 4 on Ollama) now and then answered a line
  in words, and the simulation stopped with a 502.
- **`local up` runs on a machine with no checkout.** The compose files the package ships were looked
  for beside the module `cli/local.py` instead of in `cli/local/`, and the schema upgrade read the
  process's settings instead of the local ones (it reached for Postgres on :5432).

- **`pinecall-runtime setup`: this machine's runtime in one verb, with no login, no link and no
  vendor keys.** Docker, the services, the schema, a key of the org `default`'s handed to the CLI in
  `~/.pinecall/local.json` (which the CLI reads when a project has no key of its own), and the
  models: `--models local` runs Ollama, Whisper and Kokoro on this machine through the `openai`
  plugin, in CPU images, the row written for them; `--models keys` runs on the vendors' keys read
  from the environment or asked; `--org` is a team's runtime, as `init` makes it. `--chat-only`
  runs written calls alone, with no LiveKit and no worker. `local up` is unchanged.

- **A key asking for an env it does not open is refused by name, not with a 500.** The refusal
  (a person without production access asking for production, a server's token asking for the
  other env) was raised while the request's actor was resolved, in a middleware outside the app's
  exception handlers, so it answered `500 Internal Server Error`. It now answers 403 with its
  sentence, and a socket closes with 4403 and the same sentence.

## 0.11.2 — A streamed answer holds no database connection; the feed keeps the types asked for (2026-10-17)

- **A streamed answer no longer holds a database connection.** The request's session was handed
  back after the response was sent, which for a stream is when its reader leaves: every open
  `deploy logs`, every console following a live call, every export held one of the gateway's ten
  connections and an open transaction for as long as it stayed. `deploy logs` never got fresh
  lines because its ask to the runner sat uncommitted in that transaction. The session is now
  committed and handed back when the endpoint returns.
- **The feed's `?types=` keeps those types alone.** A call's ending passed every filter, which a
  call's reader needs and the org's feed does not: `deploy up` followed on the feed still met another
  call's `call.ended` and left on it.

## 0.11.1 — Every verb walked again: the feed takes types, refusals name verbs, a broken run says why (2026-10-17)

- **The org's feed takes `?types=`.** `GET /v1/events` sent every entry of the floor whatever a
  reader asked for, and a reader following one type (a release going live, a run finishing) met
  entries it had no shape for. The feed filters as a log's stream does.
- **A monitor watches an agent the org has.** `POST /v1/monitors` with an agent no app of the org
  ever held is 404, as every other door naming an agent is, instead of a monitor that never fires.
- **A persona's vendor and voice are checked when written.** `tts` names a vendor, and one this box
  lacks is refused; a voice the vendor's catalog does not list is refused, as the page said.
  `POST /v1/voices/sample` reads `tts` as a vendor the same way.
- **Switching a judge nobody wrote is 404**, not a 409 calling it the org's own.
- **A run that broke says why in words.** A vendor's refusal (a model it does not have) is read in
  the vendor's words, never its SDK's repr with the request id in it.
- **The box's judge runs with the row's options and request.** On the box's key the judge was
  built bare: the row's `llm/<vendor>/<model>` entry (its caching, its output ceiling, its effort)
  never reached it, so `personas generate` hit the plugin's default ceiling of 1024 output tokens
  and came back empty two times in three. A judge model that answers in words instead of calling
  its tool is quoted in the 502.
- **Refusals name `pinecall` verbs, never a route or a body.** The webhook and telemetry doors,
  the judges' and personas' switches, a monitor nobody has, a group with no proposal, a vendor
  nobody installed, an agent nobody holds, and the desk's line-holding refusals.
- **A hosted app starts on the platform's `pinecall` 0.11.** The runner installed `^0.9.40`.
- **A release whose process printed nothing says so**, instead of ending its report with a colon.
- **A chat that ends from two sides at once closes its socket once.** The caller's hang-up and the
  call's own end each closed the socket; the second close was a traceback in the gateway's log.
- **A call reaches its app on every gateway.** With two gateways, a call opened on one for an agent
  whose socket is on the other was told to that gateway before its opening row was committed; the
  gateway found nothing to serve it from and dropped the word in silence, so every tool the call
  made waited out its deadline (`lookUp did not answer within 8s`), about half the time, written
  and spoken calls alike. The opening is committed before any gateway is told, and a bind this
  gateway cannot serve is logged.

## 0.11.0 — The runtime rewritten as one Rails-shaped application; a run that answers as it starts; a key tried before it is kept (2026-10-16)

- **A vendor's refusal is its own sentence** (`cerebras refused this key: Wrong API Key`), read off the
  body the vendor answered, never the SDK's repr of that body. `GET /v1/voices` with a language the
  providers row lists none of the vendor's voices in says so.
- **A refused socket closes with 4000 plus the status** it would have answered (`4404` for an agent
  nobody holds), so a terminal reads the refusal as the 404 it is; it closed with 1008 for every one.
- **A vendor key is tried before it is kept.** `pinecall providers add` (and the operator's box keys)
  ask the vendor one small thing on the key, on the first job it does, as a call would run it; a
  key the vendor turns away is refused in its words and nothing is kept. A fake key was kept before.
- **A voice the vendor has not is a 400 in one sentence**, as the settings refuse it; the vendor's
  own failure stays a 502. `GET /v1/voices` with a language the vendor has no voice in says so.
- **A judge model that answers in words is asked once more**, its words in front of it, before the
  request is given up as the vendor's failure; both requests are counted. `personas generate` and
  a judge on a thinking model failed now and then with "answered without calling …".
- **A spoken simulation needs the agent held** (`POST /v1/evals/voice`): refused as every other
  verb refuses it, instead of forty seconds waiting for an agent that never joins. Its call ends
  `caller_hung_up` when the simulated caller leaves, not `drained`: the room is closed after the
  worker wrote the end.
- **`?agent=` on the lists of cases, groups and callbacks** is a known agent of the org or a 404,
  as every `/v1/agents/{slug}` door is.

- **A case decision that moves nothing is refused** (`409 case x is already dismissed`), as a settings
  write that changes nothing writes no version; it answered the case again before.
- **Every sealed call counts into its day's drift again.** Since the rewrite the fold crashed
  on the env it was handed (text where the column takes the enum), and every seal logged "was not
  counted into its day's drift".
- **A case kept before 0.10.1 lists again.** Its golden held the caller's lines as `input`; a
  migration rewrites them as `turns`, so `GET /v1/evals/cases` and `cases show` no longer answer
  500 for an agent that has one.
- **An agent the org never held is a 404 on every `/v1/agents/{slug}` door**, naming the slug:
  a slug typed wrong (`--agent nobody`) was answered a plausible empty page before. An agent is
  the org's once an app of the org held it; another org's slug is the same 404.
- **A written call parked by a process that left is ended two minutes later** by the platform
  (`app_detached`) when no process takes it back: it stayed live with nobody to answer it, for
  ever, before.
- **A settings or lexicon write that changes nothing writes no version.** `pinecall agent set` with
  the same values, `agent clear` of a field nobody set, `lexicon rm` of an absent word all
  answered a new version before.
- **One sentence for nobody holding the agent**, wherever a verb needs one held: `no app holds
  agent x: start one, or deploy it`. The run, the simulation, the chat and the dial each said it
  their own way. A slug another org holds is refused naming the way out (rename the agent's
  folder, or hold it with that org's key).
- **A run holds no connection, and `POST /v1/evals/run` answers as it starts.** The run is stored
  `running` and played on a task of the gateway; its row is rewritten as each golden is judged, for
  `GET /v1/evals/runs/{id}` and the feed's `run.changed`, and a gateway stopping writes it `failed`
  saying so. Nothing of a run — nor of a simulated call, written or spoken — holds a session of the
  pool past the statement it needs: a run or a simulation held one of the pool's ten for its whole
  length before, one per tenant testing, which is where the 503s under several runs came from.
- **A golden that gives `memory` on an agent that keeps none breaks alone**, as a cell on the
  metric `memory` saying what policy to set, and the rest of the run plays; it refused the whole
  run with a 400 before.
- **A run is listed while it runs.** Its row was written inside the request's own transaction,
  committed only when the run ended: a second `pinecall test` was refused naming a run that
  `runs show` could not find, for up to fifteen minutes after a terminal had let go of the first.
  Each write of the row is now its own, committed, transaction.
- **A caller's own sampling never rides a request.** Every stage's LLM carries the row's request
  fields, and drops `temperature`, `top_p` and `top_k` a caller hands it: livekit's intent judge
  asked every model for temperature 0, which the Anthropic SDK no longer takes, so every golden
  with an `intent` step failed on a Claude judge.

- **A list of calls folds no log.** The seal writes what a list shows of the call (`call_facts.line`)
  and `GET /v1/sessions` and `GET /v1/agents/{slug}/calls` read it; only a live call is still folded. A page
  of 200 calls took 7 s and could starve the pool (503) before. A migration adds the column;
  `pinecall-runtime facts rebuild` writes it for the calls sealed before it existed.
- **`cryptography` 50**, which the vault seals with: 46.0.7 carried four published advisories
  (PYSEC-2026-3552, -3553, -3554, GHSA-537c-gmf6-5ccf).
- **The runtime is rewritten from zero as one Rails-shaped application**, `pinecall_runtime`
  (import name; the distribution stays `pinecall-runtime`). One folder per bounded context, every
  domain the same six files (`schemas repository service auth endpoints tasks`), in a fixed
  bottom-up order no domain imports against; `kit/`, `models/` and `wire/` below them; the
  entrypoints (`app.py api.py worker.py runner.py cli/`) above, wiring only. `CONTRIBUTING.md` is
  the canon, and `tests/conventions/` holds it: the layers (an AST walk of every import, no cycles),
  the canon's files, the vocabulary's banned words, the sizes, the suppressions, `alembic check`.
  Every endpoint of the previous runtime answers at the same path with the same shape; the wire is
  unchanged, so no SDK, console or widget moves.
- **The schema is Alembic's**, shipped in the wheel: the live schema is the baseline revision, the
  110 SQL files that made it are the history (`migrations/sql/`, read on a new database, never
  run again on one that has them), and a change to a table is a revision generated from the model.
- **`pinecall-runtime` is a Typer app**: a verb is a typed function, as an endpoint is, its
  arguments and enums its `--help`; `--json` before any verb answers for a script. The verbs are
  the same, but `sessions show <call> --json` is `sessions show <call> --folded`.
- **The vocabulary is one word per concept**: `endpoint`, `env`, `scope`, `actor`, `sign_in`,
  `one_time_secret`, `email`, `phone_leg`; the wire keeps `world` where the console reads it.
- The image runs on Python 3.13.

## 0.10.1 — A golden is turns; callers that murmur, slow down and ring from a café; judges that say what they save you from (2026-10-14)

- **The console's Judges lists the org's own and the agent's own first**, then Pinecall's library:
  the recommended eight, then the rest.
- **New simulation shows every agent's callers when none is in view**: each of the agent's own rings
  its agent, Pinecall's library rings the one picked beside it; only the sidebar narrows.
- **A library judge says what it saves you from, and whether to switch it on first.** Each row of
  Pinecall's judges carries `why` (one line) and `recommended`: `consent`, `disclosed`, `grounded`,
  `promises`, `ended-well`, `identified`, `honoured-stop` and `expected-outcome` are; `relevance`,
  `repetition` and `sentiment`, which grade a call rather than guard it, are not. Every one stays off
  until switched on.
- **A simulated caller murmurs, speaks at its own tempo, and rings from somewhere.** A persona's
  `behavior` takes `backchannels` (the share of the agent's answers it says an "mm-hmm" into
  without taking its turn, in its language), `speed` (0.5 to 2, the vendor's audio stretched with
  the pitch kept, so a slow caller is slow and not low) and `ambience` (what plays behind it once
  `interferer_db` sets a level: `television` as before, or a `cafe`, an `office`, a `street`, each
  made the same every run). `POST /v1/simulations`, the caller door and a spoken run take
  `ambience` beside `interferer_db`. A library persona says them in its front matter.
- **Box settings ▸ Defaults edits the providers row.** What a call runs on when neither the agent
  nor its settings chose — each stage's vendor, model and fallbacks, the voice per language picked by
  ear, the judge and the simulated caller with what each may spend, every model's price, the languages
  the ears also listen for and the tuning as JSON — saved whole and checked by the gateway; the embedder
  is shown and never edited there. It was a JSON file seeded once.
- **A golden is turns, each line held to what must follow it, on livekit's own test run.** A
  golden's `input` and `events` are gone (no old shape is read): it is `turns`, each a `say` (the
  caller's line) or an `event` (the app's `call.event`). A line is run with livekit's
  `AgentSession.run`, and its `then` is asserted in order with livekit's own assertions: `tool`
  (the next tool call, `args` among its arguments), `no_tool`, `reply` (the next message: `says`,
  `says_any`, `not` by code, `intent` by livekit's `judge`), `nothing_else`; and `end` and
  `within_ms`, which livekit has no step for. The first step that breaks ends the golden: no later
  turn is played and the final `expect` is not asked. Metrics are the turn's (`t2.reply`,
  `t1.tool:book`); `heard` and `expect.replies` are gone. A spoken run refuses a golden with an
  `event` turn or a `then`, and a call promoted to a case is written as turns.
- **Box settings has Keys and Admission.** The operator holds the box's vendor keys and the Twilio
  account it buys numbers on from **Keys**, and sets what a new org is given — each world's limits and
  the keys it may run on — from **Admission**; an org's **Limits** edits what the box lends it, every
  vendor the box holds a key for a checkbox, where it used to send the lends back unchanged.
- **The operator types the box's own rows.** `pinecall-runtime box keys set|rm|list` holds the box's
  vendor keys (the key on stdin), `box numbers-account set|show|rm` the Twilio account the box buys
  every org's numbers on — new doors `GET` · `PUT` · `DELETE /v1/ops/numbers-account`, the pair tried
  with Twilio before it is kept; nothing could write that account before — and `box admission
  show|set` what a newborn org is given, one environment at a time.
- **`orgs quota` no longer lends every key behind the operator's back.** It replaced the whole set,
  and a quota written without `--lends` sent `null`, which lends everything; it now keeps what the box
  lends the org, and `orgs lends <org> --env <env> <list|all|none>` sets that alone.

- **No judge of Pinecall's library is on until switched on.** `consent`, `grounded`, `promises`,
  `disclosed`, `identified`, `honoured-stop`, `ended-well` and `expected-outcome` were on by
  default; now every one of the eleven is off for an org or agent that never switched it, and a
  call meets only the judges switched on and the org's and the agent's own. A switch already
  written stays as it is.
- **A golden asks only the judges its `expect` names.** Every golden was asked `consent` whether it
  named it or not; now it gets `heard` (when it has lines), one check per `expect` field, and
  `grounded` or any judge only when it names it. A golden that wants `consent` lists it in
  `expect.judges`.
- **The console says whose keys a call runs on, and what is left of each limit.** The Overview's
  **Limits** card shows minutes, evals, simulations and bought numbers as what is used of each, when
  the monthly ones start again, and the vendors the org brought keys for beside the ones the box
  lends it; Providers marks each vendor *your key*, *lent by the box*, *some models lent* or *bring a
  key*, where it said *ready* for a vendor the box would refuse to lend. **Finish setting up** asks
  for the keys, a simulation and, in the sandbox, a call from your own phone.
- **A second Twilio account from the console.** Numbers' Accounts tab connects another Twilio account
  or a WhatsApp number, each account says how many numbers it routes, and Add a number always shows
  which Twilio account a number is taken from, with *Connect another* beside it; before, the
  connect form appeared only while the org had none. Buying shows how many numbers the org bought.

- **The model writes the line a tool is announced with.** Every tool the model sees, the app's
  and the knowledge lookups, carries an optional argument `say`: one line for the wait, in the
  caller's language. When the model's turn said nothing itself, that line plays as the tool
  starts, in place of the tool's `announce`; the app never receives it. A tool declaring an
  argument named `say` is refused.
- **A tool's `announce` plays on every written turn, not the first one alone.** A written call
  (a simulation, a chat, WhatsApp) never started the caller's turn unannounced, so once the agent
  had said anything, no tool it called in silence was announced again.
- **A judge answers its own question and no other.** One asked whether the agent answered in the
  caller's language broke a call on a claim about the caller's screen. The judge model is now told
  that anything else in the conversation is another judge's question, never decides its answer
  and has no place in its reason, and that a call giving its question nothing to judge is `na`.
- **Generate callers reads as what it does**: what they call about and which of Pinecall's
  callers they take after, each a labelled question, the cost beside the button; the
  callers written come back as the grid's cards — what each wants, how it sounds, what it holds the
  agent to — each kept on its own or all at once.
- **A call that a judge broke on shows where.** In the call's log, transcript and chat, every row
  a broken judge cites is red, with the judge's creature, its name and its reason under it; a seq
  no row carries (a tool's result, a state change) marks the row before it.
- **The caller's words stay on screen until their turn lands.** The live line emptied the moment a
  stretch was heard to the end, while its turn landed a moment later, so the words vanished for
  that moment; the call screen now keeps what was heard since the last turn until it lands.
- **A judge decides last.** The tool a judge answers with takes the positions first, then the
  reason, then the answer, and the prompt says to decide by that reason: a model fills the fields
  in the schema's order, and `grounded` on Claude Haiku answered `broken` first and then wrote a
  reason that ended in "so the verdict is held". The trigger's tool is ordered the same way.
- **A simulated caller never speaks in the agent's voice.** It was compared with the voice the
  agent declared only, so an agent on the operator's voice for its language, or on its plugin's own
  when the operator set none, had both ends of a spoken simulation in the same voice. The caller
  now steps past the voice the agent actually speaks with — the one it declared, the operator's, or
  the plugin's own default — and, when the operator offers no other, takes the next voice the
  vendor lists in the agent's language.
- **The console hears a spoken simulation again.** Its ear waited for the call's `room.opened`
  and took the stream's opening `log.caught_up` for the call being over, so it never joined; the
  CLI's `--listen` refused the same way. Only `room.opened` or `call.ended` decides now.
- **An org with one agent opens on it**: the sidebar puts that agent in view, an org-wide screen
  an agent also has opens as its, and the Viewing list drops "All agents", which would show the
  same calls.
- **Nothing asks on a clock, and a rule says so.** `run.changed` (the run, its agent, whether it is
  over) and `release.changed` (the app, the release) are said on the org's feed, and `worker.changed`
  (the worker, its fleet, whether it is heard and cordoned) on the box's floor, each with only its
  ids and never stored: a screen or a terminal reads the run, the app or the fleet at its own door
  when one is said. An app's logs are a stream (`GET /v1/hosted/{name}/logs` with
  `Accept: text/event-stream`: a frame each time the runner's beat brings lines, and the stream is
  what keeps the runner sending), `GET /v1/ops/usage` as a stream wakes on the metered entry written
  on any gateway and no longer reads Postgres every second per client, and a terminal waiting to be
  signed in asks `GET /v1/login/pairings/{code}/key?wait_s=25` once a wait, the gateway holding it
  until a browser approves. The console's eval runs, fleet, app logs, insights, series, limits and a
  number's first call, and the CLI's `pinecall test`, `deploy`, `deploy logs`, `login`, `--listen`
  and spoken simulations, read when they are told. Rule 25: no generator that serves a reader sleeps
  to look again.
- **The console reads on the feed, never on a clock**: one `/v1/events` stream per page, shared by
  everything that reads on it. The call list, the insights, the series, the limits and a number's
  first call are read when the page opens and when the feed says a call started, ended, was
  summarised or judged, and every 3 s only while the feed is down. A spoken simulation's ear joins
  once when the call's log says its room is open (`room.opened`), where it knocked at the door
  every second thirty times.
- **The org's feed says when a call is sealed and judged**: `/v1/events` and the box's floor carry
  `call.summary` and `call.score` with `data` empty, so a list redraws a row when its outcome,
  cost and verdicts land, with nothing of the call's content on the feed. The console reads its
  calls when the feed says one changed, and asks every 3 s only while the feed is down.
- **A tool runs with the arguments the model gave it, whichever gateway wrote the call.** A
  gateway sent the app a tool call's `pii` arguments from its own memory, and only the gateway that
  wrote the call held them: with the worker on one gateway and the app's socket on the other, the
  app was sent the log's mask, and a tool declared `pii` ran with `***` (`who(name=***,
  email=***)`, refused as not an email, the model left with nothing to say). The gateway that
  sends the entry now reads the values back from their sealed copy when it did not write them.
- **`dead_air` is gone**: with `e2e_latency` the wait to the reply's first sound, it measured the
  same silence twice. The pipeline's medians and a replay's budget name `e2e_latency` for it; a
  budget that still says `dead_air` judges nothing by it.
- **End to end is the caller's wait to the agent's first sound.** livekit's `e2e_latency` ran from
  the caller's last word to the turn it rode on, so a preamble said before a tool ("let me look
  that up", 0.6 s after the caller) carried none and the answer after the tool carried the tool's
  wait too: a call's end to end read 3.2 s, at its worst 12.8 s, where the caller had heard the
  agent in under a second. The first turn after the caller's now carries the wait to it, and a
  later turn of the same reply carries none, in the log, the call's facts, the insights, the
  monitors and a replay's latency check alike. Calls before it keep livekit's.
- **A simulated caller writes its next line while the quiet after the answer passes**, asked for
  the moment the agent's answer lands, where it waited for the quiet before asking its model: the
  model's 0.7 s no longer come after it. An answer that goes on (the tool after a preamble) throws
  the line away and asks again; a call that ended in the meantime says none of it.
- **A simulated caller answers once the agent is done, not seconds later.** The quiet it leaves
  after an answer was counted over every entry of the log, and the VAD's metrics, which land about
  once a second all call long, kept starting it over: a spoken caller took 3 to 4.6 seconds to
  speak where the agent took under one. It is counted over the conversation alone now: the agent's
  states, words and tools, the caller's own turns and the call's end.

## 0.10.0 — One repository, one version; a visitor's conversation resumed, the console redrawn (2026-10-12)

- Published from [pinecall/pinecall](https://github.com/pinecall/pinecall) with every other
  Pinecall package, at the one version they all carry from here on. 0.1.48 was never published;
  what it held is here. The wheel's console and widget are those of the same commit, so
  `console.lock` is gone and an image is built from one checkout, not three.

- **The console's screens are redrawn**: Personas and Judges are grids (a face on each persona, a
  creature on each judge, Pinecall's library folded under the agent's own callers), Simulations
  is the runs with the callers to choose from, Cases is a short list of groups with one move each,
  and a call's trace id is a section of its rail. The wheel carries that console and a widget
  whose End chat ends at once and whose welcome shows on the maximized panel alone.
- The widget a visitor can size, maximize and re-theme: a drag from the corner away from the button,
  a maximize that takes the whole window and reads like a chat app, a switch between the light and
  dark theme that follows the machine unless the page forces one, and a page's own launcher
  (`slot="button"`) that opens the panel once instead of twice.
  Maximized and inside a conversation, the conversations kept are a list at the side (New chat on
  top, the one in view marked, each one deletable); the X ends the conversation in view; and no
  weight of the widget is bold.
  What an agent puts on the visitor's screen with call.send("pinecall.ui", …) is drawn in the
  widget's conversation: {type: "choices"} as buttons whose tap is the visitor's next line, and
  {type: "html"} as a card kept to text, lists, tables, https links and images, and code.

- **The simulated callers' model is the box's to set**: `caller.llm` of the providers row, a stage
  as `judge.llm` is, plays every persona that names no model (absent, the default `llm`), and is
  refused when written for a vendor that is not installed.
- **One of Pinecall's personas is played on the model an agent names**: `PUT` of a library name
  takes `{"llm": "vendor/model"}` beside `{"on": …}` (`""` back to the box's caller model), kept
  per org and agent in `persona_switches.llm` (migration 0109), the agent's over the org's.
- **Pinecall's library is a bar of its own on the Personas screen**, under the agent's callers,
  saying what it holds and opened by Show them; the wheel carries that console.
- **A simulated caller lets go the moment the quiet after an answer has passed**, where it
  waited a whole beat past it: half a second less on every turn of a spoken simulation.
- **The `grounded` judge reads the agent's prompt and the day the call began** (version 2): an
  address the prompt gives, or the agent saying what day it is, no longer reads as invented. The
  evidence every judge that reads it is shown opens with when the call began.
- **A simulated caller speaks each line as its vendor sends it**, piece by piece through the
  line's noise, where it waited for the whole line to be synthesized before its first word: a
  turn of a spoken simulation answers one to two seconds sooner, by the length of the line.
- **One of Pinecall's personas is read in the voice an agent names**: `PUT` of a library name
  takes `{"tts": "vendor"}` and `{"voice": "id"}` as it takes `{"llm": …}`, kept beside it in
  `persona_switches` (migration 0110); what a `PUT` leaves out of the three stays as it was. The
  console picks all three from what the box runs, the voice by ear, for every persona; the wheel
  carries that console, with a call's own page and a base's file read as markdown.
- **A tool's `announce` is said once for the caller's turn**, not once for each round of the
  model's: a model that chains tools in silence (Gemini calls `propose`, then `who`) no longer
  stacks one announcement on another.
- A visitor's conversation can be resumed, the two ways LiveKit recommends. A widget call waits
  five minutes for a visitor who left (a reload, a closed tab, a dropped line) and their room
  outlives them as long, so `POST /v1/tokens` with `resume` seats them back in the same call. Later,
  the same `resume` opens a new call that carries the old one on: its worker is handed the earlier
  turns, read from the log by the gateway, and the agent greets nobody. Every mint answers a
  `resume_token` for 30 days; a widget says a hang-up on `pinecall.hangup`, which ends the call at
  once. (`docs/protocol/tokens.md`, "Resuming a conversation")

- A simulation opened before 0.1.46 wrote `accepts_when` and `declines_when` on its
  `call.started`, and the reader refused them: the console's page of such a call threw, and the
  runtime could not read it again to judge it or keep it as a case. `CallStarted` reads both again
  and writes neither; the console's schema does the same, and its timeline skips an entry it cannot
  read instead of throwing.

- Every livekit plugin is a vendor of every deployment: `voice-big` is gone and aws, azure, google
  and speechmatics are in `voice`, so a vendor is one key away (`pinecall providers add`), never a
  release away. Gemini answers calls on the Gemini API with one key, `pinecall providers add google`.

- Gemini answers: every call's history opened on the clock's call to `current_date`, and Gemini
  refuses a function call no user turn comes before (400, "function call turn comes immediately
  after a user turn"). Behind a Google model the pair now opens after a user turn of one dot, the
  turn livekit's own Gemini format adds at a history's end for the same rule; every other model
  opens as before.

## 0.1.47 — The outbox drains without spinning, and two tests wait for what they check (2026-10-11)

- `Outbox.drained` could spin forever: a letter that finished just before it was called stayed in
  the set until a callback the loop never got to run, because `gather` answers a finished task
  without yielding (Python 3.12). It now yields after each gather. It is what a gateway waits on
  when it stops, and it is what hung the sign-up test of the 0.1.45 release.
- The session tests that checked a spoken turn after a fixed 50 ms wait for the turn instead
  (`until`, shared from `tests/conftest.py`): a loaded runner lost that race on the 0.1.46 release.

## 0.1.46 — Evals and simulations are counted, personas expect and act, cases are grouped and diagnosed (2026-10-11)

- **Evals and simulations are quotas.** `Quotas` gains `evals` and `simulations` (migration 0106),
  counted a month at a time in `usage_totals` from `call.score`, `evals.spent` and `call.summary`,
  as the feed folds them: a judge on the org's own key counts none. Past `evals` a call's judges
  left are `skipped` and `credits.exhausted` is written once; past `simulations` a simulation, a
  spoken caller or a spoken golden is refused before it opens. `GET /v1/limits` shows both.
- **A simulated call counts no minutes, nor does a call an eval run opened** (`call.summary.run`):
  a simulation is one simulation, a written golden is its evals alone.
- **What the harness asks a model is counted**: `evals.spent` on the agent's log (`kind`: a judge
  tried, personas written, a group diagnosed), in the environment it was asked in, carries its
  evals; the feed has a row for it. A try takes the agent's finished calls only, and says when a
  judge runs on simulations alone.
- **Personas say what they expect and how they act.** `expects` (one demand a line, "The agent
  should…") replaces `accepts_when`/`declines_when` (migration 0107 carries them over;
  `call.started.expects`), with `tags` and a `behavior`: `interrupts` (the share of the agent's
  answers a spoken caller talks over, some way into them — barge-in tested for real), `pause_s`,
  and the line's noise. **A library of personas** (`evals/library/personas/`): realism —
  `in-a-hurry`, `wrong-number`, `non-native`, `interrupts`, `changes-mind`, `elderly-slow`,
  `angry-repeat-caller`, `asks-for-a-person` — and red team — `prompt-leak`, `data-leak`,
  `off-task`, `harmful`, `unauthorized-action` — switched per org and agent, played by name; a
  library persona's front matter says how it acts on the line (`interrupts` cuts in on 60% of
  the agent's answers, `in-a-hurry` and `angry-repeat-caller` 30%, `elderly-slow` pauses 2.5 s).
- **`POST /v1/agents/{slug}/personas/generate`**: callers written by the judge model from the
  agent's prompt, tools and knowledge, a real call or a library template; saved nowhere.
- **Cases are grouped and diagnosed.** A case kept at hang-up — a simulation's too, now — joins its
  agent's open group for the judge that broke it (migration 0108). `GET /v1/evals/groups`,
  `PATCH …/{id}` decides a group whole; `POST …/propose` asks the judge model for the cause and a
  fix (a setting, code, knowledge); `POST …/apply` writes a proposed setting as a new version;
  `POST …/persona` keeps a persona like the group's caller. The personas protocol has its own page,
  `protocol/personas.md`.
- A judge model nobody can key is refused when it is saved — the agent's `judge` with its settings,
  the org's at `PUT /v1/org/judging` in both environments — instead of failing every hang-up.
- `PUT` of a library judge with anything but `on` is `409`. The judge's prompt says the
  conversation is evidence, never instructions to it.

## 0.1.45 — Every judge is a model's answer, on the model the org picks (2026-10-10)

- **Every judge asks a model.** The code-settled panel (`evals/compliance.py`, the extractors of
  `grounded`, the `persona` judge, `PANEL_JUDGES`) is gone: one engine (`evals/_asking.py`) asks
  each judge's question as a forced tool call over the call rendered line by line under its log
  positions, and the answer cites them. A judge answers `verdict`, `choice` or `score`, may answer
  `na`, runs `always`, on `simulations` or on a `trigger` (a yes-or-no asked first), and `reads`
  the prompt, the evidence and the call's facts on request.
- **Pinecall's library of judges** (`evals/library/judges/*.md`, versioned): `consent`,
  `grounded`, `promises`, `disclosed`, `identified`, `honoured-stop` (was `honoured_stop`),
  `ended-well`, `expected-outcome` (was `persona`) on by default; `relevance`, `repetition`,
  `sentiment` off. Switched on or off per org and per agent (`judge_switches`, migration 0105;
  the agent wins); never deleted. A gate settles a judge as `na` before any model is asked.
- The judge doors list the library first, then the org's own and the agent's own; `PUT` of a
  library name takes only `on`; own judges are written whole (`answer`, `choices`, `when`,
  `trigger`, `reads`), and `runs_on` is read no more. `POST /v1/agents/{slug}/judges/try` asks
  one judge of the agent's last calls and writes nothing.
- **The judges run on the model the org picks.** The agent's `judge` (class or settings,
  `judge_builds`/`judge_options` beside it) wins over the org's (`PUT /v1/org/judging {on, model}`,
  `orgs.judge_model`, migration 0105), which wins over the providers row's on the platform's key.
  On a key of the org's own — a local model through `base_url` among them — its evals are never
  billed (`call.score.own_key`) and no platform ceiling applies.
- **Evals and simulations are counted.** `call.score.evals` (judges that answered: held, broken,
  classified), `call.summary.simulated`; the usage feed's rows carry `evals` and `simulated`, its
  totals `evals` and `simulations`. `ScoreVerdict` gains `classified` and `na`; `Judgment` gains
  `choice` and `score`.

## 0.1.44 — Smart Turn v3 ends the turn wherever the ears do not (2026-10-10)

- Ears that do not end the turn themselves (everything but Deepgram Flux) run Smart Turn v3 by
  default, not livekit's v1-mini: the providers row's `turn_model` left out is Smart Turn now, and
  an agent's `end_of_turn` still wins. Migration 0104 takes `v1-mini` out of the row where the
  console had written it only as the default, so production's ears move to Smart Turn too.

## 0.1.43 — Who ends the turn is the agent's to say, and an opening is not cut short (2026-10-10)

- `end_of_turn` on the ears (`ModelConfig.end_of_turn`, a class's `@stt(…, { endOfTurn })`, the
  settings' `end_of_turn`): `stt`, the ears themselves where the operator's row says their class
  ends the turn (Deepgram Flux), refused otherwise; `livekit` (v1-mini) or `smart-turn` (Smart
  Turn v3), a model on the worker, on any key. Soniox with Smart Turn is one line of the class now,
  not an operator's row. Refused on a model, and checked at `agent.configure`
  (`refuse_what_cannot_run`).
- An opening is not interrupted unless it says so (`allow_interruptions: true`): a caller's
  "hello?" over it no longer stops the agent mid-sentence.
- An empty `reply` lets the model open on its prompt alone: the SDKs' `improvise`.

## 0.1.42 — What the class declares wins over the settings (2026-10-10)

- An agent's class may declare its environment again — language, voice, llm, stt, greeting,
  hangup, turn, says, hears, knowledge, docs, memory, record — and **what it declares wins** over
  the org's settings for that agent (`providers/declared.py`). The declaration remembers which it
  fixed (`AgentConfig.fixed`); a field sent as null is the settings' again.
- A declared voice names its vendor and its voice, and a declared model a vendor that is installed
  and does the stage, or the configure is refused (`session/_environment.py`).
- `VoiceConfig` and `ModelConfig` carry `builds` and `options`: a class of the vendor's plugin,
  dotted names allowed (`responses.LLM`), and its keyword arguments, each over the operator's. An
  OpenAI model declared with `{builds: "responses.LLM", options: {use_websocket: true}}` runs on
  the Responses API's WebSocket.
- The settings and lexicon doors list the fields the class fixes (`fixed`), and a set that changes
  one is `409` naming it and the class.
- The settings gain `temperature`, `llm_builds`, `llm_options`, `stt_builds`, `stt_options`,
  `tts_builds` and `tts_options`: everything a class can declare of a stage, the settings can set.
- The console's Configure shows a field the class fixes read-only, "set by the class", and gains the
  model's temperature and each stage's plugin class and options (console 69ab3ca).
- A plugin class or options of the agent's own (class or settings) run only on the org's own key
  for the vendor: on a lent key they are `409` at `agent.configure`, at a settings `PUT` and when the
  call's stages are handed out (`providers/credentials.py`), since an option can point a plugin at
  another server.

## 0.1.41 — The written caller's tests run on a real written call (2026-10-10)

- `tests/evals/test_simulated.py` drives a real text session against the org's app instead of a
  stand-in, as the rules ask; 0.1.40's release was refused on that file. No code changed.

## 0.1.40 — A simulated caller waits for the agent's whole answer (2026-10-10)

- The caller of a simulation, spoken or written, speaks again only once the agent has spoken after
  its line, listens with no tool running, and a second of quiet has passed (`evals/turns.py`).
  livekit publishes `listening` while a tool runs and between one tool and the next, and the
  caller took that for an answer: it talked over an agent that looked something up twice. A long
  answer is waited for whatever it takes; only thirty seconds of silence on the line give up.
- The written caller takes its turns by the same rule as the spoken one.

## 0.1.39 — An agent's search answers on every call it serves again (2026-10-10)

- `POST /v1/calls/{call}/lookup` takes the org's key on a call its process serves, whoever opened
  it. Since 0.1.10 the worker doors belonged to the call's opener alone, and the lookup was one of
  them: an app's `knowledge.search` was answered 404 on every call the fleet's worker or the
  gateway opened — phone, voice and written — so an agent's lookUp tool failed on them. The other
  worker doors stay the opener's. A test pins the app's search on a fleet's and a written call.

## 0.1.38 — A simulation calls whatever holds the agent, deployed too (2026-10-10)

- `POST /v1/simulations {agent, persona, voice?, turns?, interferer_db?, packet_loss?}`: the
  gateway plays one of the agent's personas against whoever holds it — a deployed process or a
  developer's `pinecall start` — spoken (the call `/v1/evals/voice` places) or written (the chat
  the widget has, each improvised line said once the agent's whole answer is in). Refusals come
  before the answer; the call's id comes back at once and the conversation is played in the
  gateway, stopped with the process (`gateway/simulating/`, `evals/simulated.py`).
- The spoken caller, its model, voice and line are one module both doors use
  (`gateway/simulating/caller.py`); a written caller's line counts its model alone.
- Console 1370bb1: Harness ▸ Simulations starts every simulation through the gateway, so a
  deployed agent is simulated like a local one; it no longer asks the dev socket.

## 0.1.37 — An agent that is not the org's is erased whole (2026-10-10)

- `DELETE /v1/ops/orgs/{named}/agents/{agent}`: the operator erases one agent of an org, both
  worlds — its logs, recordings and memories, its settings, callers, judges, monitors, routes, eval
  runs and cases, its days of drift — with one trail row (`what: agent`, migration 0103). Refused
  while a process of the org holds it or a call of it is live; another org's agent of the same slug
  is never touched (`tenancy/erasure.py agent`).
- `GET /v1/simulations` takes `?agent=` once or more: the console asks for the agents the org holds.
- Console 1529df9: the harness lists the org's agents alone; Routes reads the runtime's row
  again; Box usage pages its rows; Privacy is four tabs; a log in euros is read as dollars.

## 0.1.36 — One harness screen whoever is in view (2026-10-10)

- `GET /v1/simulations?agent=`: one agent's simulated calls, from the same door as every agent's.
- Console d79c0e7: Simulations, Personas and Cases are one screen each, the same with every
  agent in view or one; a simulation opens inside Simulations, never as a bare call. Personas and
  Judges are list rows with a face.

## 0.1.35 — A number's account id keeps to its column (2026-10-09)

- Console 32491ba: on Numbers, a long account id under Comes through is cut at its column
  instead of running over If it rings now; the whole value is in the title.

## 0.1.34 — The org's whole harness: every caller and every simulated call (2026-10-09)

- `GET /v1/personas`: every agent's callers, by agent and then by name; a persona row now says
  `agent`, whichever door lists it.
- `GET /v1/simulations`: every simulated call of the key's world and scope, newest first, paged as
  a persona's runs are; a run row now says its `persona`.
- Console a5b5fbe: the Harness lists every agent's simulations, personas and cases with every
  agent in view, and Cases is a row of it.

## 0.1.33 — The console's sidebar keeps the person in sight (2026-10-09)

- Console 64a494d: the person and their bell stay at the sidebar's foot while the rows scroll,
  and Viewing is one compact row.

## 0.1.32 — The console's Settings is what is set once (2026-10-09)

- Console fae4edd: Apps and Secrets are tabs of Agents, Docs and Memory the org's Knowledge row,
  Data & privacy the workspace's Privacy row, and Notifications the person's own, opened from
  their name. Settings keeps Tokens, Providers, Telemetry, Alerts and Phone testing.

## 0.1.31 — The console's Harness: simulations, personas, judges and monitors in one section (2026-10-09)

- Console 83b945e: the sidebar has a Harness section — Simulations, Personas, Judges, Monitors —
  for every agent or the one in view; they were tabs of Test and of Quality. With every agent in
  view, Simulations and Personas list the org's agents and ask whose.

## 0.1.30 — Settings ▸ Telemetry says what the export is (2026-10-09)

- Console 3cc98c9: the Telemetry screen's lede said every call was already traced, which read as
  if a chat were traced and as if the console depended on the export. It now says the export is a
  copy of every spoken call's trace, a chat has none, and it is off until set; the rest of the
  console reads the call's log either way.

## 0.1.29 — A call's trace says its world, its session and its contact as any tool reads them (2026-10-09)

- Every span of a call also carries the OpenTelemetry conventions `deployment.environment.name`
  (the world), `session.id` (the call) and `user.id` (the contact's id, never the number), so
  Langfuse, Datadog, Honeycomb and Grafana sort a trace into its environment, session and user
  without knowing what `pinecall.*` means (`worker/_traces.py attributes_of`).
- Console a6263fc: Settings ▸ Telemetry offers Langfuse by its region and two keys, beside any
  OpenTelemetry collector; the Erasures card names who asked.

## 0.1.28 — The charts in both themes, and the access log whole (2026-10-09)

- Console f4448e2: the charts' six tones are a palette the console has (four series drew in
  no colour, and on dark two were one violet); the tooltip, ticks and crosshair on real tokens.
- Data & privacy reads every kind of read the runtime records (listen, supervise, export, memory):
  one such row had refused the whole list.

## 0.1.27 — The webhook's secret is resealed with the rest (2026-10-09)

- `org_webhooks.ciphertext` joins the columns a vault key rotation walks; 0.1.25 and 0.1.26
  sealed it under the current key and would have left it behind on a rotation.
- Console 5dcd629: the Alerts tab's event labels get their width.

## 0.1.26 — The console's Alerts tab and the widget's kept conversations (2026-10-09)

- Console dc0403f: Settings ▸ **Alerts** sets the org's webhook, proves it with a test post
  and says what is posted; Notifications gains "a monitor fires"; Monitors says who set each
  one by name.
- Widget a5aacad: the visitor's last conversations kept in the browser and read again from the
  menu (`history="off"` keeps none); the panel redrawn.

## 0.1.25 — A webhook for the org's alerts (2026-10-09)

- **Webhook**: `PUT /v1/webhook` names a URL of the org's own; every alert — `monitor.fired`,
  `spend.unusual`, `credits.exhausted` — is posted there as it is written on the agent's log,
  `{type, org, env, agent, at, data}`, signed with `x-pinecall-signature: sha256=<hmac>` when the
  org set a secret, tried twice within five seconds. `POST /v1/webhook/test` proves the URL.
  `monitor.fired` says its `env`.

## 0.1.24 — The console's Quality is a harness: judges and monitors as its tabs, Test opens on an overview (2026-10-09)

- Console 63bf329: Quality's judges table is a tab of its own beside **Monitors** — the
  world's monitors, set and dropped there, each with the last day it fired; an agent's Test opens
  on an overview of the harness: personas, simulations, judges, goldens, cases and monitors, each
  with its number, and the latest runs.

## 0.1.23 — Monitors: a number of the series watched, fired once a day (2026-10-09)

- **Monitors**: `POST /v1/monitors` watches one number of the series — end-to-end or first-token
  latency, the judges' held rate, the share a person took over, the share of tools that failed,
  spend or calls — over 1, 7 or 30 days, above or below a line, for every agent or one. At each
  call's seal the world's monitors are read; one that crossed fires once a day as
  `monitor.fired` on the agent's log and keeps the day and the value. `pinecall monitors` and the
  console's Monitors screen set them.
- The console's charts bridge a day with nothing by a dotted stroke, and every day with data
  gets a dot (console d491bcb).

## 0.1.22 — A call's length counts only when it ended after it started (2026-10-09)

- **A mean length, and an agent's minutes, count only calls that ended after they started**: one
  production call sealed with an `ended_at` before its start threw a day's mean to minus fifty
  million seconds on the Observability screen and the Overview.

## 0.1.21 — Observability's cards, one word each (2026-10-09)

- A card's seconds read as one word (`1.46s`), and its delta names the window short.

## 0.1.20 — org_telemetry under row-level security (2026-10-09)

- **`org_telemetry` gets the row-level security every org table has**: a tenant's connection
  sees its own telemetry row alone. CI had refused 0.1.14 to 0.1.19 for it, so none of them
  reached PyPI; production ran them from the image, where every door checks the org itself.

## 0.1.19 — Observability, the way a dashboard reads (2026-10-09)

- **The series say each day's mean call length** (`mean_length_s`), and the console's
  Observability screen opens on five cards — calls, success rate, time to first token, mean
  length, spend, each against the window before — then endings as stacked bars by day, the
  duration, the failure modes (the judges that said no, most often first), and a by-agent table.

## 0.1.18 — Observability, the axes right (2026-10-09)

- A judge's share tops out at 100%, and a day with calls shows its tool count, zero included.

## 0.1.17 — Observability, in the console (2026-10-09)

- **Observability, in the console**: `GET /v1/insights/series` answers the window day by day —
  calls, how they ended, cost, end-to-end and per-stage latency at the median and p95, each
  judge's held rate, tools run and failed — and the console's new Observability screen draws it,
  for every agent or the one in view, over 24 h, 7 d or 30 d. A call's tools are counted at its
  seal (`drift_calls.tools_ran`, `tools_failed`).

## 0.1.16 — The transcript says the word written, not how it is pronounced (2026-10-09)

- **The lexicon is read back in the transcript**: a word the voice was told to say another way
  (`Pinecall` → "pain-col") reached the log, the console and the judges as the spoken form.
  The transcript now carries the word written, with the spoken form's timing.

## 0.1.15 — Settings ▸ Telemetry, padded (2026-10-09)

- The console's Telemetry card reads like the form beside it.

## 0.1.14 — A call's trace id is the call's (2026-10-09)

- **A call's spans share a trace id a reader can compute**: the call id's 32 hex digits, or the
  first 32 of the SHA-256 of a carrier's call id — so a call found in the console is found in the
  org's own tracing tool by the same id. The console's call page names it, with a copy, when the
  org exports (console `screens/call/trace-id.tsx`).

## 0.1.13 — The console gets Settings ▸ Telemetry (2026-10-09)

- **Settings ▸ Telemetry** in the console: the org's collector set with its headers (sent once,
  read back by name alone) and whether a span may carry what was said, and stopped from the same
  card — the console's `screens/telemetry`, over `/v1/telemetry`.

## 0.1.12 — An org's traces reach its own collector (2026-10-09)

- **An org sends its calls' traces to its own collector**: `PUT /v1/telemetry` names an OTLP
  endpoint, the headers every export carries (sealed in the vault, never read back) and whether
  a span may carry what was said; the worker exports each call's spans there beside the box's
  collector, every span carrying `pinecall.org`, `pinecall.env`, `pinecall.agent`,
  `pinecall.call` and `pinecall.holder`. `pinecall telemetry` sets it from the CLI.

## 0.1.11 — A tool announces itself (2026-10-09)

- **A tool announces itself**: a tool declared with `announce` ("Let me check the agenda.") is
  said as it starts, while it runs, when the model's turn said nothing itself; a turn that spoke
  and then called the tool is not announced twice. `@pinecall/agents` 0.9.24, `pinecall` 0.1.8 on
  PyPI and the gem 0.0.4 declare it.
- **A golden's recall reaches the agent**: the facts a golden gives are written on the call as a
  real recall is (`memory.ops`), so the agent's `remembers(…)` reads them; before, only the model
  saw them and the view went on as if nothing were remembered.

## 0.1.10 — A golden's day reaches the agent (2026-10-09)

- **`call.started` says the day a golden pinned** (`today`, `YYYY-MM-DD`), so an agent resolves
  "on Monday" against the golden's day, as the model does, and not the clock's. Absent on every
  other call. An SDK before this field refuses the entry: `@pinecall/agents` 0.9.23, `pinecall`
  0.1.7 on PyPI and the gem 0.0.3 read it.
- **A golden that gives `memory` to an agent whose policy keeps nothing is refused** by name,
  before the run opens a call: recall runs only on an agent with a policy, so the facts would
  never have been recalled and the golden would have tested a memory the agent does not have.

## 0.1.9 — The runtime whole on one machine: `pinecall-runtime local up` (2026-10-09)

- **`pinecall-runtime local up`**: the runtime whole on one machine from the package alone — the
  compose files it ships written to `~/.pinecall-runtime/local`, Postgres, Redis and LiveKit up,
  the schema migrated, the secrets drawn once, then the gateway with the console and a sandbox
  worker in the foreground. `local down`, `local init`, `local env`. `make local` runs it.

## 0.1.8 — A hosted project starts on the newest CLI of its minor (2026-10-09)

- **A hosted project starts on the newest CLI of its minor**: the runner installs `pinecall@^0.9.40`
  when a pod starts, so a CLI release reaches hosted projects on their next start and no runtime
  release carries it. A CLI that breaks its contract bumps the minor, and the runner with it.

## 0.1.7 — A hosted project is started by the platform's own pinecall (2026-10-09)

- **A hosted project is started by the platform's own `pinecall`**, installed in the pod beside
  the project's dependencies at the version the runtime names (`CLI_VERSION`, 0.9.40), never from
  the project's `node_modules`: a project lists `@pinecall/agents` and nothing of the CLI.

## 0.1.6 — PyPI `pinecall-runtime`, and a call a judge broke on kept as a case (2026-10-09)

- **The runtime is PyPI `pinecall-runtime`**: `pip install "pinecall-runtime[voice]"`, `uvx
  pinecall-runtime …`. The import is still `pinecall`, and the command still `pinecall-runtime`.
  PyPI `pinecall` is now the Python SDK, from 0.1.6 on; 0.1.0–0.1.5 there are this runtime, so a
  `--from pinecall` without a version pin no longer finds the command.
- **A call a judge broke on waits as a case**: at hang-up, a call that did not pass is kept in the
  org's dataset as a `pending` case, its `expect` what the broken verdicts forbid (`consent` →
  `not_tools`, `grounded` → `grounded`, the model judges → `judges`), its golden carrying what
  `recall` gave the call. At most 50 wait per agent. `PATCH /v1/evals/cases/{id}` approves (the
  nightly's `dataset: true` plays only those), dismisses, holds out, or marks a case kept in the
  repository; `judge_was_wrong` writes the calibration label. `GET /v1/evals/cases` takes
  `status` and says how many wait. `GET /v1/calls/{call}/golden` answers the golden a call makes,
  kept nowhere. Migration `0097_case_status.sql`.
- **`expect.judges`**: a golden asks hang-up judges by name (`promises`, a compliance judge, the
  org's or the agent's own) of its call; a name the panel does not hold breaks the golden.
- **`GET /v1/callbacks` lists the key's world only**: an agent's log holds the callbacks of both
  worlds, and the list returned every one of the org's; each is now the world of the call it names.
- **A sealed call's usage entries carry their `type`**: the memory writer's and the simulated
  caller's were built without one and frames drop unset fields, so the SDKs rejected the seal of
  any call that wrote memory (`pinecall chat --as` ended in a ZodError).
- **A written caller can hang up**: `{"hangup": true}` on `WS /v1/chat` ends the call, then closes
  the socket with `the call ended: caller_hung_up`, so whatever served the call stops with nothing
  live. A caller that only closes its socket still ends the call, as before.
- **A drain counts only calls still live**: a call that ended and waits for its seal is neither
  handed on nor parked, so `pinecall chat` and `test` no longer say a live call was kept.
- **`pinecall remember`'s refusal names the memory policy**, which is the world's: `agent <slug>
  remembers nothing: its memory policy names nothing to keep`.
- **An agent's language is a setting of its world**, like its voice and its models: `language` in
  the settings body (`pinecall agent set --language en`, the console's Settings), a pipeline knob a
  `words` key cannot set, tried on the ears and the voice before it is kept. Unset, each vendor
  keeps its own default; an app on an SDK before 0.9.19 still declares one, read only when the world
  set none.
- **`call.started` says how the call is had**: `medium`, `voice` for a call in a room and `text` for
  a written one, so an app tells the widget's spoken call from its chat, which share the `web`
  channel. SDKs before 0.9.19 refuse a field they do not know: release them first.
- **A call opens in the state its opener asked for, on `call.started`.** `WS /v1/chat?state=<json>`
  (an object, 16 KB at most; anything else closes the socket with the sentence) and a golden's
  `state` ride the call's `call.started` as `state`, absent when nobody asked; the app applies it
  before the first render. The eval runner no longer sends a `session.configure` with the
  golden's state, so the log holds no `state.changed` the app did not write. A spoken call carries
  it too: a spoken golden's state and `POST /v1/evals/voice`'s new `state` ride the dispatch to the
  worker, which writes them on `call.started`.
- **Breaking: the console's directory verbs go to the socket that answers the console.**
  `agent.register` may say `answers_dev: true`, and `POST /v1/agents/{slug}/dev/{family}/{verb}`
  goes to the newest such socket that is not draining; `view.render` still goes to the socket
  serving the call. An agent held only by sockets that serve calls is `409`, naming
  `pinecall start`. Update the CLI with this runtime: an older `pinecall start` registers no
  companion, and the console's Chat, Tests, Simulations, Docs and Memory screens are refused.
- **The start-up rebuild of the SIP trunks tries again until whole**: a gateway started beside a
  LiveKit still starting (or down) left that world's numbers unadmitted until its own next start;
  it now retries, 2 s and doubling, a minute at most, while an org is refused or a LiveKit cannot
  be reached.
- **A developer's own phone reaches their sandbox copy across LiveKits.** Where each world has a
  LiveKit of its own, a ring from a developer's registered phone at a production number can no
  longer be handed to the sandbox's fleet in production's room, so production's room dials it to
  the sandbox's livekit-sip: `sip:<the production number>@<the sandbox's SIP name>`, the caller as
  its From, `X-Pinecall-Org`, `X-Pinecall-Agent` and `X-Pinecall-Holder` saying whose ring it is.
  The caller and that leg stay bridged in production's room, and the gateway deletes the room when
  either leaves, so hanging up either side hangs up the other. On the sandbox's LiveKit the start
  makes a `hand-over` trunk and rule: the trunk lists no number and admits production's media
  address alone (the one `PINECALL_SIP_DOMAIN` names) with a pair drawn from `LIVEKIT_API_SECRET`,
  turning the headers into the leg's attributes; the rule sends the leg to the sandbox's fleet, and
  the gateway offers it as the developer's call. `GET /v1/agents/{slug}/rings-for` answers the
  `trunk` to dial in that case (null where the worlds share a LiveKit, which keeps the hand-over in
  one room). A handed-over ring is now opened as a phone call at the production number, its
  caller read off its leg, in both cases; it was opened as a widget's. The firewall in front of the
  sandbox's SIP must admit production's media address on 5060.
- **A LiveKit per world.** A sandbox call never shares a machine with a production one: each
  world's rooms, trunks and rules live on a LiveKit of its own. The gateway reaches production's at
  `LIVEKIT_URL` and the sandbox's at `LIVEKIT_SANDBOX_URL` (unset, the sandbox shares production's,
  as before), on the one key pair, and asks each world's of its own: a room is offered on the
  LiveKit of its fleet's world, the reaper asks a quiet call's world's, a simulated caller joins
  its world's, and a number's trunk and rule are on its world's alone — moving it between worlds
  takes it off the old world's LiveKit and admits it on the new one's, and the start's rebuild takes
  a number off the other world's where it is still listed. LiveKit's webhook names the world that
  sent it, `POST /v1/livekit/webhook?world=sandbox` (none is production's; another word, `422`). A
  browser joining a sandbox call is told `wss://<the name>/sandbox` when the sandbox has its own
  LiveKit. `doctor` asks each world's LiveKit and names the one that does not answer.
- **One name, two worlds.** A box has one name (`PINECALL_DOMAIN`) and both worlds answer at it:
  the world of a request is its key's (a server's token opens the world it was made in) or, for a
  person, the `pinecall-env` header's, the sandbox when it names none — never the name the request
  came in by. `PINECALL_SANDBOX_DOMAIN` is gone, and with it the refusal of a header that disagreed
  with the name. The console is production's at `/` and the sandbox's at `/sandbox/…`, same
  origin, same sign-in; the gateway writes no `pinecall-world`/`pinecall-elsewhere` marks into the
  page, and `GET /.well-known/pinecall` no longer says `world` or `elsewhere`. A browser's
  `server_url` is `wss://<the name>` in both worlds. The SIP names stay one a world
  (`PINECALL_SIP_DOMAIN`, `PINECALL_SANDBOX_SIP_DOMAIN`): a carrier's, written into its trunk by the
  runtime, typed by nobody.
- **v1's machines left the repository**: the box, the cell, the fleet loop and its
  clouds, the Packer image, the AWS fleet and the lab's own Terraform, and with them `box up`,
  `box upgrade`, `box failover`, every `cell` verb, `fleet loop`, `fence apply` (`pinecall-fence`),
  the join door and its scope. The fence is the cloud's firewall: `fence export` prints the
  networks 5060 opens to as Terraform's `sip_sources`, and `GET /v1/ops/carriers` says them
  (`networks`, in place of `applied_at` and `applied`). A carrier sends a world's calls to its SIP
  name (`PINECALL_SIP_DOMAIN`, `PINECALL_SANDBOX_SIP_DOMAIN`; unset, the world's name), and
  `sip repoint` (`POST /v1/ops/sip/repoint`) sends every Twilio trunk at a world's name on to it,
  once. A worker registers with LiveKit under its name and its start, so a container started again
  under the same name is never taken for the dead one. A gateway keeps an idle connection 620 s
  (Google's load balancer keeps its own 600) and imports every plugin before it listens;
  `pinecall_vendor_failing` carries every installed vendor, 0 while it is sound. Uplift AI imports
  (`python-socketio`, which its plugin needs and does not declare).
- **The runtime runs in Kubernetes pods** (`infra/`), with the box's behaviour unchanged unless
  said: `PINECALL_GATEWAY_LISTEN` binds a pod's gateway on its network and
  `PINECALL_TRUSTED_PROXIES` names the load balancer it believes (a box keeps loopback and Caddy);
  `PINECALL_METRICS_FROM` lets a cluster's Prometheus scrape `/metrics`, never a forwarded
  request; `PINECALL_WORKER_HTTP_HOST` opens the worker's health port to a pod's probes; and
  `GET /v1/ops/fleet/{fleet}/wanted` tells KEDA how many scaled workers the fleet wants, by the
  loop's own line, counting the core's seats first. `PINECALL_WAL_SPOOL` names the box's WAL
  spool `doctor` reads (a cluster's Postgres archives through its operator, with none, and the
  application connects there as no superuser).
- **A chat in a room ends after ten minutes without a message.** It was the one call with no
  ceiling: a visitor who left a chat open held a worker's seat for as long as the page stayed
  open. It ends as `timeout`, the ten minutes the voice ceiling has.
- `gcp-mig.py delete` asks the group's list first and deletes only a machine still on it, instead
  of reading a refusal's text to tell one already gone.
- `gcp-mig.py list` leaves out a machine the group is deleting: it stays listed for about a minute
  after its delete returned, and the loop decided its delete again every tick (four times in
  production on 2026-10-03). The script's verbs have a test on a fake Compute API (`tests/infra/`).
- A worker's heartbeat names it to LiveKit (`agent_name`) only once LiveKit registered it: it beats
  from its start, and the gateway offered calls to a machine still loading its plugins, which waited
  12 s for the offer to go to another worker.
- **A machine the loop makes is named once**: `pinecall-worker-<yymmddhhmmss>-<n>`, the time it was
  asked for, instead of the lowest free `pinecall-worker-<n>`. A reused name carried the last
  machine's cordon and its silence in the roster onto the next one, which the loop deleted as
  "cordoned and gone" 13 s after asking for it (production drill, 2026-10-03).
- **A call whose caller dropped ends**, whatever the reason they left. livekit's session closes on
  the caller leaving only when they hung up, the room was deleted or they were rejected; a browser
  whose connection timed out was waited for, and with a supervisor watching the room never emptied:
  on 2026-10-03 a call held its worker's seat for over half an hour after its visitor was gone. A
  caller who does not come back within 20 s, LiveKit's own wait for a room's last person, now ends
  the call as `caller_hung_up`, the room deleted with it.
- **The fleet loop is the one thing that sizes a fleet.** Production's managed instance group had an
  autoscaler too, grown on the fleet's calls the loop wrote to Cloud Monitoring: it counted the
  calls the box's own workers held, asked for a machine at the first call, and the loop let it go
  as one too many, five machines in forty minutes on 2026-10-03. The autoscaler (and AWS's target
  tracking) is gone; `infra/fleet/gcp-mig.py create` makes a machine in the group by name and
  `aws-asg.py create` raises the group by one, as every other cloud script makes one. `measure`,
  `--grow-at-most 0` and the box's metric-writer role are gone with it.
- A release stops each world's fleet loop before it changes the package and starts it when it
  ends: it never restarted it, and the loop ran the code it was started with until it crashed.
- **The gateway chooses the worker a call goes to.** A worker registers with LiveKit under its own
  name, `<fleet>/<worker>`; the SIP rule and a visitor's token still dispatch to the fleet's plain
  name, which nobody holds, and the gateway, told by LiveKit's webhook that a person is alone in a
  room, offers its call to the worker heard in the last 12 s with the most seats free, again to
  another after 12 s, and to the fleet's overflow after three. Outbound calls, simulated callers
  and the sentence of a worker gone go the same way. The overflow is `<fleet>/overflow`, always
  open; its gate and `GET /v1/fleet/standing` are gone. `fleet list` and `/metrics` say the rooms
  waiting for a worker; each offer is a line in the gateway's journal with the worker and why, and
  `doctor`'s `offers` line names rooms no gateway swept. A room is let go when a worker opens its
  call, an agent joins it or it ends, so a caller who hung up first is never offered again; a
  fleet none of whose workers was heard yet (a gateway just started) has its room wait up to 12 s
  for the next sweep instead of the sentence. A box needs LiveKit's webhook to place calls.
- **The hosted apps' machine is Terraform's too** (`module "apps"`, imported with no change):
  nothing of the runtime's cloud is made by hand any more.
- **A worker that counts its calls takes every one of them.** It reported `calls ÷ slots` to
  LiveKit, whose server and framework both stop at 0.7: LiveKit refused it at 0.7 of its slots
  (6 of 8, 23 of 32) while the gateway counted the rest free, and the next call rang in silence.
  It now reports on LiveKit's scale, `0.7 × calls ÷ slots`, so LiveKit's full is its last slot,
  and `calls ÷ slots` to the gateway, full at 1.0; neither of LiveKit's lines is overridden, and a
  test reads the installed framework's to hold the worker to it.
- A machine of workers no longer takes the box's `PINECALL_IDLE_PROCESSES` with its fleet's
  settings: it keeps livekit's, one warm process per CPU.
- The lab stops a worker before it destroys its machine, keeps the machine's journal under
  `.lab/`, and places its calls at `--rate` a second. A machine destroyed with its worker up stayed
  registered in LiveKit for 15–20 minutes and took half the next run's calls into silence.
- Every machine of the cell is a `pinecall-runtime cell` verb, as the box is `box up`: on the box
  `cell allow-replica`, `allow-gateway`, `allow-worker` (an address or the fleet's range), their
  `forget-…`, `gateway-credentials`, `worker-settings` and `worker-credentials`; on the machine,
  `sudo uvx --from pinecall==<version> pinecall-runtime cell join-worker | image-worker |
  release-worker | join-gateway | release-gateway | join-replica`, which copies the package's
  `infra/` there first. Nobody copies `infra/` by hand or calls a script by its path any more; the
  scripts stay as what the verbs run. `pinecall-runtime --version` says the version to install.
- The curl examples are gone, from the repository and from the docs site.
- **The cloud is Terraform's** (`infra/terraform/`): the state in a versioned bucket, one root
  module per environment, `make tf-plan`/`tf-apply`/`tf-check` (CI runs the last). Production was
  imported whole — the box and its replica, the fleet's subnet, the firewall rules, the static
  address, the two buckets with their IAM users and policies, SES, the box's four names in Route 53
  — and a plan says `No changes.`.
- **A fleet machine on Google Cloud reads its credentials from Secret Manager** as its own
  identity: a worker service account per world, five secrets declared with no value
  (`modules/secrets`), written by the box with `pinecall-runtime cell publish-secrets`.
  `pinecall-runtime cell enroll` replaces the bash enroll: a join token, or Secret Manager, once.
- **Production's fleet is a managed instance group** (`modules/fleet-gcp`): the image built by
  Packer (`make image`, `infra/packer`), no public address (a NAT for the fleet's subnet), healed
  on the worker's health port, grown by its autoscaler on the fleet's calls; it never shrinks
  itself. `fleet loop --grow-at-most 0` is the loop of such a cloud: it tells the cloud the calls
  (`measure`) and lets go of the one too many once drained; `infra/fleet/gcp-mig.py` is its
  script, and `pinecall-fleet-loop@<world>` runs it on the box, configured from the box's
  metadata. The box's VM acts as `pinecall-fleet`, which may touch the fleet's machines alone.
- **The runtime whole on a laptop**: `make local` starts the box's Postgres, Redis and LiveKit in
  docker (`infra/local/`), migrates and writes `.local/env` once; `make local-gateway` and
  `make local-worker` run both from the checkout. No cloud account, no key of a box.
- **A fleet on AWS, the same shape as Google Cloud's**, written and validated, applied by no box:
  `modules/secrets-aws` and `modules/fleet-aws` (an Auto Scaling group grown by target tracking on
  `Pinecall/fleet_calls`, its scale-in off), `infra/fleet/aws-asg.py` for the loop, an
  `amazon-ebs` source in `infra/packer`; `cell enroll` and `cell publish-secrets` read and write
  Secrets Manager on AWS. `infra/fleet/aws`, the loop that made EC2 machines itself, is gone.
- **The voice lab is Terraform's** (`environments/lab`): `infra/lab/measure.py` makes the box, the
  generator and the worker machine with `terraform apply` at the sizes under test, resizes the box
  by the same apply, and destroys all of it with `terraform destroy`; the machines' configuration
  is `infra/lab/configure.sh`, one verb a step.

## 0.1.5 — The fleet's image carries no credential: each machine joins on a key of its own (2026-10-02)

- The fleet's image carries no credential. A machine the loop makes spends a join token at its first
  boot (`POST /v1/fleet/join`, `pinecall-join.service` → `worker.sh enroll`) for a fleet key of its
  own, the LiveKit pair and the store's secret, sealed to that machine; the loop mints the token
  (`POST /v1/ops/fleet/join-tokens`: a key of scope `join`, named for the machine, ten minutes, spent
  once) before each `create` and revokes the machine's keys after each `delete`
  (`DELETE /v1/ops/fleet/{worker}/keys`). `worker.sh image` prepares the machine the image is frozen
  from, from `primary.sh worker-settings` (no secret); `infra/fleet/first-boot` is the user-data the
  three cloud scripts hand over; `fleet loop` requires `--fleet` unless `--dry-run`.
  Measured on Google Cloud against the sandbox fleet: a machine made from such an image was
  `accepting` 99 s after the loop asked for it, and deleted with its key revoked 86 s after the
  cordon. The recipe is `infra/fleet/README.md`.
- The fence lets in a range (`primary.sh allow-worker 10.100.0.0/24`), the subnet the fleet loop
  makes its machines in; `infra/fleet/gcp` takes `PINECALL_FLEET_SUBNET`.

## 0.1.4 — Workers on machines of their own, the recording made by the call itself, a box measured with real audio (2026-10-02)

- Workers on other machines: `primary.sh allow-worker <address>` on the box (the fence, LiveKit's
  API and the gateways' balancer at the box's own address, `PINECALL_HERE`), then the fleet's
  credentials through a pipe into `worker.sh join <box> <wheel> <world> [calls]` on the other
  machine; `worker.sh release` for a new wheel. A worker machine reaches the box's LiveKit and
  gateways and nothing else of it. Measured on 8 vCPU: 24 calls at once at 3.5 cores (~0.15 vCPU a
  call, the recording included), first audio p95 1.3 s, every turn answered; the box spends ~0.1 a
  call on their media. `docs/scaling.md`, "A machine of workers alone".
- A call's recording is made by its own session, not by an egress process per call: livekit's
  recorder for the caller (left) and the agent (right) at 24 kHz, and every other voice of the room
  — a supervisor who took over, the far end of a warm transfer, the hold melody — laid in on the
  right where it sounded when the file closes, a stretch at a time. The worker seals it under the
  call's key and moves it to the bucket before the seal. Egress is no longer asked for anything
  (track egress was built and measured dearer: ~0.1 vCPU and ~170 MB a track). The lay-in costs
  ~1/40 of the call's length on a core; a call of half an hour or more with another voice may run
  past the worker's minute to seal, said on the box page.
- LiveKit's API is published on the box's own address by `install.sh`, behind the fence, so letting
  a worker or gateway machine in restarts nothing (a box from before gets one restart, said).
- The object store's file is `/etc/pinecall/store.env` (was `backup.env`): backups and recordings
  both read it. `box upgrade` (and `install.sh`) moves a box's `backup.env` there, once, and says so.
- The four alerts are evaluated on the box by Prometheus and mailed by Alertmanager
  (`infra/box/alerts.sh`, `alerts.sh test` proves the path).
- The box measured whole with real audio and no vendor (`infra/lab/`: the vendors faked on their own
  wire, SIP callers playing a recording): a 4-vCPU box with everything on it holds 6 calls at once.
  Three fixes it found: the plugins are preloaded in the worker's forkserver (ring to live 0.1 s, was
  3–5 s idle and up to 74 s loaded), SIP's RTP range matches the fence, and each world's seats are
  its own.
- Insights count a window of 1, 7 or 30 UTC days, of the scope or one agent.
- A chat's opening is kept, so the gateway holding the app's socket serves it.
- `replica.sh join` works on a machine made a minute ago.

- The box's workers count their calls (`PINECALL_MAX_JOBS`, one per vCPU each, written by `install.sh`)
  instead of reading the machine's CPU: on CPU, a burst of calls left rooms with no agent, LiveKit never
  offering them again (measured: 5 of 10 at 20 % CPU; counting, 14 of 15). A call costs ~0.24 vCPU.
- The disaster drills, run: a restore to a minute in 79 s with RPO under a minute, and a failover
  to the replica in 17 s with no write lost, a box again in under 3 minutes (`docs/a-box-in-production.md`).

## 0.1.3 — The server side, measured: gateways on many machines, a cluster of media, and the numbers (2026-10-02)

- A model that says nothing for 12 s (or the agent's `llm_timeout_s`) no longer leaves the caller in
  silence: the turn is cut and the caller hears a short sentence asking them to say it again, in the
  agent's language. Unset used to mean no deadline at all.
- LiveKit as a cluster, measured: two nodes on the box's Redis carried 400 voice calls with no packet
  lost, and a worker on one node took rooms placed on the other. How a node is added is on the box page.
- Gateways on machines of their own: `infra/cell/primary.sh allow-gateway` on the box (pg_hba, the
  fence, Postgres, Redis and LiveKit's API published on its address for those machines alone, Caddy
  sending them calls), `gateway.sh join` on the other machine (the credentials through a pipe). Redis
  asks a password of everyone (drawn by `install.sh`, `PINECALL_REDIS_URL` a credential). Measured: a
  gateway machine killed for two minutes under 1 200 calls lost none of them.
- What a container is published on beyond loopback is written into its installed file: podman 4.9
  reads no `.container.d` drop-ins, so the replica's Postgres (`primary.sh allow`) was never
  published on the box's address. Fixed for it and for gateway machines.
- A gateway that dies with a worker's request in flight loses no call: an open is asked again while
  the gateway is away and is the same call by its id (one claim, one opening, one ringing), and a seal
  asked again that finds the call sealed is done. The seal's lease is 15 s renewed while sealing (was 120 s):
  a gateway that dies sealing lets the call go in seconds, and a knock waiting on it takes the seal
  over, instead of the worker giving up and the reaper sealing the call with no usage. The lease
  names its holder (migration 0085): only it renews or gives it back, and a summary is written once
  per log, so two gateways sealing one call price it once. Measured: 1 200 calls held, a gateway killed every
  minute: 0 logs wrong, and the only refusals left were opens and seals in flight at the kill.
- `pinecall-runtime load` counts refusals by status and door (`502 POST /v1/calls`), not by status.
- A log read is built from its rows without validating them again (`log/store.py` `entry_of`): a seal
  reads its whole log three times. Measured from a generator machine at 300 calls held: append p50
  60 → 38 ms, p99 850 → 430 ms, seal p50 330 → 200 ms.
- The append path costs a gateway a third less of its core (100 calls held: 155 % → 100 % on two
  gateways; append p50 161 → 14 ms, p99 1.4 s → 94 ms): a group's rows go to Postgres as one JSON
  document instead of six arrays adapted a value at a time, the entries socket and the relay read and
  write JSON in pydantic's own parser, and only the types the facts fold lock a call's facts row.
- A worker's batches of a call go down one WebSocket for the call's life (`WS /v1/calls/{call}/entries`)
  instead of a request per batch: no routing, headers or key per batch on the gateway. A refusal is a
  frame and the socket stays; a lost socket is opened again and the batch asked again with the same
  `after`; a gateway of before (no such door) gets every batch by request, as before.
- A gateway remembers a key it verified for five seconds (`tenancy/remembered.py`): verifying
  was a round trip per request, 15 % of its core under load. A key revoked at a door is forgotten
  on every gateway at once, said on the signal, and so is a person whose role, agents, production
  access or operator standing changes; one revoked at a shell opens for those seconds.
- A summary or a score written before money in dollars (`eur`, `judge_cost_eur`, the euro's `rate`)
  is read again, its euros as the same number of dollars, as migration 0007 kept the facts: on a
  box that ran before dollars, most summaries had become unreadable. `facts rebuild` and doctor's sample
  leave a call whose log holds an entry the wire still refuses as it was folded, instead of
  refolding it to nothing.
- The providers row may name the language a vendor's ears are told (`tuning."stt/<vendor>".options.language_code`),
  and it wins over the call's base code: NVIDIA's streaming ASR takes `es-US`, not `es`.
- How a spoken turn ends is the ears' `tuning` too: `turn_model` picks the local model that reads
  the end of the caller's turn off the audio, `v1-mini` (livekit's, the default) or `smart-turn-v3`
  (Daily's Smart Turn v3, a new dependency, 8 MB of ONNX on the worker's CPU).
- The open stack: `infra/models/` holds three model servers for one NVIDIA GPU (`compose.yaml`:
  Whisper large-v3-turbo on Speaches, Gemma 4 12B and bge-m3 on Ollama, Kokoro-82M) and the
  providers row that points a box at them (`providers.json`); the wheel carries it as
  `pinecall/infra/models/`. `docs/the-open-stack.md` walks it from a bare GPU and has the numbers:
  about 1.6 s from the caller's last word to the agent's first on an RTX 3090, and why NVIDIA's
  streaming ASR is not the ears (its NIM drops sentences after the silences of a real call).

## 0.1.2 — A box from the package itself

- `pinecall-runtime box up --domains …` makes the machine it runs on a box, with no checkout: the
  wheel carries `infra/box` and `infra/postgres` as `pinecall/infra/`, and `box up` installs the
  system's packages, runs `install.sh` and releases this version from PyPI. `box upgrade` brings a
  box to the version it is run from, its names kept. `sudo uvx --from pinecall pinecall-runtime box up`.
- `release.sh` releases a PyPI version or a wheel's path (`PACKAGE=`) besides a built wheel (`WHEEL=`).
- `/usr/local/bin/pinecall-runtime` on a box runs any operator verb with the box's credentials.
- A box made from the package encrypts its backups to the key `--backup-key` gives, or makes none:
  the package carries no backup key, and `install.sh` enables the backup only with one.

## 0.1.1 — The runtime written again, in production

The runtime written again from a blank page, in production since 2026-09-29. `pip install pinecall`
installs the gateway, the worker and `pinecall-runtime`, the console and the widget inside;
`docs/from-zero.md` walks a box to its first call.

- The skeleton: the domain types, the error hierarchy, the settings, the wire, the database pool
  and the migration runner, the schema as one migration, and the rules `make check` enforces.
- The call's log: an append-only store whose seq is born in one upsert (a sealed log refuses an
  append with 409), the facts of each call folded in the same transaction, the reducer the
  TypeScript and Ruby SDKs share (held to the protocol's golden log at every cut), the two
  projections (the tenant's, with `pii` fields masked when read, and the public one), and one
  in-process fanout whose slow reader gets a `log.gap` with a snapshot.
- Fixed: the usage feed counted every call's tokens and characters as zero; it read rows named
  `llm`/`tts` while a summary carries `llm_usage`/`tts_usage`.
- Fixed: a reader of a log sealed without `call.score` waited for ever; the stream asks the store
  whether the log is sealed before it reads the backlog.
- The suites run on a local Postgres (`make test`: colima, the image of `infra/postgres/`, one
  schema per test); `make test-sandbox` runs them on the sandbox database.
- Every vendor livekit ships is a vendor here: each installed plugin that exports an LLM, an STT
  or a TTS, and LiveKit Inference, built through one path with its constructor's own argument
  names. The runtime keeps no list of vendors, models or voices; a model or a voice a vendor does
  not have is that vendor's own error, in the call's log. `pinecall[voice]` installs all but
  four; `pinecall[voice-big]` adds aws, azure, google and speechmatics.
- An org's own key runs any installed vendor and any model of it; the box's keys run what
  `quotas.lends` lends the org. What the box offers, each vendor's options, the defaults, the
  voices per language and the prices are one row of the database, edited from the console.
- Voice and written calls run on the same livekit session: the same turns, tools, prompt,
  supervisor verbs and entries. A written call's `agent.reply` is instructions for one turn, as a
  voice call's always was.
- One gateway and one database serve production and the sandbox. A person signs in once and
  has one key for both worlds (production only with production access); a server has a key per
  world, `pc_live_` or `pc_test_`. Test calls stay off production processes because each world
  has its own fleet of workers, and every call is dispatched to the fleet of its world. Quotas and
  an agent's hold melody are kept per world (migration `0002_worlds.sql`).
- What a new org is given is the box's `admission` setting, edited from the console; a box with
  none limits nothing. No extension package is loaded.
- `PINECALL_VAULT_KEY` is required: every secret is sealed under it, and the gateway does not
  start without one. `PINECALL_WORLD`, `PINECALL_ELSEWHERE_URL`, `PINECALL_IDENTITY_URL`,
  `PINECALL_SANDBOX_URL`, `PINECALL_SANDBOX_KEY`, `PINECALL_PEER_KEY` and `PINECALL_EXTENSIONS`
  are gone.
- Orgs, people, keys, sign-in (password, one-use codes, pairing, sign-up, an org's own OpenID
  provider), tuning and lexicon versions per corner, widgets, hold
  melodies, personas, caller codes and mail. Usage is counted from the calls' summaries when a
  call or a turn asks to start; nothing is held in memory.
- Fixed: the tuning and the lexicon a call is built on are read in one query, so a write between
  two reads no longer records a version the call did not run on.
- Fixed: a written call counted each turn twice (the caller's and the agent's); a tool's
  structured output reached the model as Python's repr instead of JSON.
- The gateway and the worker. One gateway serves both worlds: the app socket, the worker's doors,
  the log's readers (a page or a stream), the supervisor's seats and verbs, a visitor's room token
  with the dispatch to its world's fleet signed inside, caller codes, and text calls on
  `WS /v1/chat`. A worker is livekit's `AgentServer` registered under its fleet's name
  (`pinecall`, `pinecall-sandbox`); it resolves whose call a job is from its dispatch or the number
  dialled, opens the log, and runs the session. Workers report to the gateway every five seconds;
  a full production fleet is answered by the overflow, a full sandbox refuses at the token door.
  A call the worker lost is sealed by the gateway's reaper. The vendors a call ran on the box's
  key are kept with its facts (migration `0003_lent.sql`).
- The box: `infra/box/` makes a machine from nothing (cloud-init, `install.sh`, Quadlet containers
  for LiveKit, SIP, egress, Redis and Postgres, the units); `make deploy` builds the console into
  a wheel and releases it; `pinecall-runtime` has `gateway`, `worker start`, `worker overflow`,
  `migrate up`, `keys fleet` and `doctor`.
- Fixed: a tool of a call whose agent nobody holds waited until its deadline; it is refused at
  once.
- Numbers and WhatsApp. An org holds many carrier accounts (Twilio accounts, SIP peers, WhatsApp
  numbers at Meta), sealed under the vault key; a number is imported from one of them ("we hook
  it": the account's trunk pointed here, found by where it points) or hooked by the org itself
  ("you hook it": admitted from its networks, nothing outside touched). On the SFU an org has one
  trunk per fence and one dispatch rule per world, so a number moves between worlds by a door
  (`PUT /v1/numbers/{number}/env`) without touching its trunk. The box buys numbers into either
  world on its own Twilio account, capped by that world's `numbers` quota. The door paths and
  answers are v1's, so the console reads them unchanged. `0004_carriers.sql`.
- Dialling out needs no trunk on the SFU: every leg is dialled with its trunk inline, so an emptied
  SFU dials on. A Twilio account's termination is one per account and box, with a credential per
  org on it. The dial guards count and write the ledger row in one transaction under the org's
  lock, and a number is a stranger to a world it never called.
- WhatsApp conversations are keyed by the org, the world, the number and the contact; a message
  whose agent nobody holds waits on the agent's log and is answered when an app declares the
  agent, with no polling. The box's Meta app and Twilio account are sealed rows of
  `box_settings`, not variables: `PINECALL_WHATSAPP_APP_SECRET`, `PINECALL_WHATSAPP_VERIFY_TOKEN`
  and the three `TWILIO_*` are gone.
- Fixed: a number the box bought was never admitted again when LiveKit's Redis was emptied, and a
  purchase rewrote an org's SIP peer trunk with Twilio's fence; the reconcile at start rebuilds
  every routed number with its own fence.
- Fixed: a supervisor's `end` on a WhatsApp conversation left it open; the conversation closes
  with its call.
- A WhatsApp account's number is listed from Meta beside the Twilio numbers and imported on its
  account; an agent answers at as many numbers as the org routes to it, of any kind.
- The account doors, on the one gateway, at v1's paths and in v1's shapes: `/.well-known/pinecall`,
  `whoami`, sign-in with a password or a one-use code, the orgs a person opens and the switch
  between them, a terminal paired from a browser, a forgotten password, an invitation accepted,
  the org's members and keys, sign-up, the org's identity provider and its mailbox, and
  `/v1/ops/whoami`. The sandbox asking production who a person is (`POST /v1/login/redeem`) is
  gone with the second instance; box-wide Google sign-in answers `503`. A key minted for a device
  is labelled with it, and a login code gives a copy of the key that minted it, the person
  included, dying when it dies.
- Evals: a suite of goldens runs through the app that holds the agent, one written call per
  golden and model, judged into a matrix stored as it goes (`POST /v1/evals/run`); a finished call
  is checked by code (`/replay`) or judged again (`/judge`); a persona is played by a model, in
  writing (`/caller`) or on a spoken line (`/voice`). A persona names the agents it may call. Every
  call is judged at hang-up when its org judges, the box names a judge model and the ceiling is
  above zero; the judge's tokens are counted and priced. Eval runs belong to an org and a world.
- Money is in US dollars, the currency providers price in: a call's cost, each priced line, the
  judge's cost, a persona run's cost, the org's monthly budget and the judging ceiling
  (`PINECALL_JUDGE_CEILING_USD`). Nothing is converted at a rate; the providers row carries no
  exchange rate. A persona names the agents it may call on the wire too.
- Retrieval in the call: a turn's recall and search run on the gateway for the worker
  (`POST /v1/calls/{call}/lookup`) and for a written call alike, every attached base searched in
  one pass, the contact's facts recalled when the agent keeps memory, `docs.sources` and
  `memory.ops` written on the log where they ran; a lookup that cannot run is a recoverable
  `<tool>_skipped` and the turn goes on. The seal writes what the call taught into the contact's
  memory between `call.ended` and `call.summary`, within `PINECALL_REMEMBER_BUDGET_S`, and a
  hang-up that cannot remember says so and seals all the same (`POST /v1/calls/{call}/remember`
  does the same on request).
- The rest of the doors, so every door of v1 answers: the org's meters (`/v1/usage`,
  `/v1/insights`, `/v1/limits`), an agent's settings and the org's lexicon versioned per world and
  scope, the pipeline report and the hold melody (uploads converted once to Ogg Opus), the widget,
  the providers catalogue as each org may run it, the org's own vendor keys, a vendor's voices and a
  sample, and the operator's `/v1/ops/*`: orgs, their people, keys, quotas per world, dial guards,
  the SSO break-glass, routes, the fleet and its cordons, every org's floor and meter, the box's
  mail and brand. The fleet loop (`fleet/hub.py`) grows and shrinks a fleet through a cloud script.
  `pinecall-runtime` gained `init`, `orgs`, `keys`, `routes`, `fleet`, `sessions`, `providers`,
  `memory reembed`, `migrate status` and `migrate plan`. Box-wide Google sign-in answers 503.
- The box's own configuration has doors: the providers row (`/v1/ops/providers`), the box's vendor
  keys (`/v1/ops/provider-keys/{vendor}`), admission (`/v1/ops/admission`) and the fleet of each
  world (`/v1/ops/fleets`); `pinecall-runtime providers seed` writes a box's first providers row.
  `infra/fleet/` holds the clouds a fleet grows on (gcp, aws, hetzner).
- The pages, every one under the name the site syncs: the gateway API and every door in one table,
  tokens, codes, projections (PII masked when read), the line, a deploy that never cuts a call, the
  smallest app, people, the operator's doors, the box's settings and floor, settings, pipeline,
  providers, dev verbs, the console's reads, retrieval, scaling, charging for it, a box in
  production, from zero, prompt injection.
- A call's cost counts everything it billed: each leg on the phone network in minutes begun,
  priced by the longest prefix of its number (`CostRow.unit` takes `minutes`), and the tokens of
  the model that writes memory at hang-up. The box's prices ship as `infra/box/prices.csv`, the
  operator's to edit, applied with `pinecall-runtime providers prices`.
- A name per world: `PINECALL_DOMAIN` is production's and `PINECALL_SANDBOX_DOMAIN` the sandbox's,
  both one gateway. The name a request comes in by is its world: the console served at the
  sandbox's name is the sandbox's (the page carries `pinecall-world` and `pinecall-elsewhere`),
  `pinecall-env` may only agree (on a door and on the app and chat sockets alike),
  `/.well-known/pinecall` says `world` and `elsewhere`, a browser
  joins LiveKit at its own name, and a number imported in a world points its carrier at that
  world's name.

- The box's floor (`GET /v1/ops/events`) says each frame's world: `env` is the world of the call,
  `null` on an agent's own entries, so a reader serving one world keeps its frames and no other.
- Fixed: an org's feed (`GET /v1/events`) carried both worlds' calls; it carries the calls of the
  world the key acts in, and the org's agents' own entries, which serve both.
- A lexicon is one agent's: `GET`·`PUT /v1/agents/{slug}/lexicon` and `GET …/lexicon/history`
  replace `/v1/lexicon`, with the same bodies, keys, scopes and versions. Migration 0008 copies
  each org's lexicon to every agent the org has in that world, keeping its version numbers, so
  `GET /v1/calls/{call}/settings` still reads the words an older call ran on.
- A persona is one agent's: its doors are `/v1/agents/{slug}/personas[/{name}[/runs]]`, a name is
  unique within the agent, its runs are that agent's calls, and `/v1/evals/voice` refuses with
  `404` a name nobody wrote for the agent it calls. `/v1/personas` is gone, and so is a persona's
  `agents`: a row written for some agents becomes one copy each, one written for every agent one
  copy per agent the org has. Fixed by construction: the console and the CLI never sent `agents`,
  so every edit of a persona made it callable by every agent again.
- An agent's own judges: a question about its job the org writes (`GET /v1/agents/{slug}/judges`,
  `PUT`·`DELETE /v1/agents/{slug}/judges/{name}`, `pinecall judges`), asked of the judge model at
  hang-up beside the runtime's panel, on every call or only on simulated ones; its verdict is in
  `call.score` under its name. `POST /v1/evals/judge/{call}` asks them too.
- The org's own judges: `GET /v1/org/judges`, `PUT`·`DELETE /v1/org/judges/{name}`, questions
  asked of every agent's calls beside the panel and the agent's own; a name may not be the
  panel's, nor the org's and an agent's at once, and a judge without a question is refused.
- The judge's ceiling is the providers row's `judge.ceiling_usd`, applied: a model judge asked
  once the call's judging reached it is `skipped`, saying so. `PINECALL_JUDGE_CEILING_USD` is gone.
- Hosted apps, the record: `POST /v1/hosted/{name}/releases` keeps a project's sources (a gzipped
  tarball, read before it is kept: no link, no path out of the project, 10 MB) as the app's next
  release; the first makes the app, counted against the new `hosted_apps` quota, and mints a
  server's token for it, sealed. `GET /v1/hosted`, the releases and a release's source back,
  `DELETE /v1/hosted/{name}`. The org's secrets per world, sealed and never read back:
  `GET /v1/secrets`, `PUT`·`DELETE /v1/secrets/{name}`. Nothing builds or starts a release yet.
  Migration 0018.
- The runner's doors, for the process that will run hosted apps: a key scope `runner`
  (`pinecall-runtime keys runner <world>`), `POST /v1/runner/heartbeat` (every app of the world
  with the host its release runs under, whether it registered, and the runner's `live` and
  `failed` reports kept), a release's source and an app's environment (the org's secrets, its
  token, the world's address). `GET /v1/hosted` says `live_release` and `failed_why`.
  Migration 0019.
- The runner: `pinecall-runtime runner start`, the process that keeps a world's hosted apps
  running on a machine of their own (`infra/apps/`: podman, gVisor, an nftables fence, one runner
  unit per world). It installs a release inside gVisor, starts it read-only, capped and on a
  network of its own under the release's host name, reports it live once its agents register, and
  stops the release it replaced only then; one that does not install, exits or never registers is
  reported failed with its last lines, and the one before keeps serving. `PINECALL_RUNNER_KEY`,
  `PINECALL_RUNNER_ROOT`, `PINECALL_RUNNER_IMAGE`, `PINECALL_RUNNER_RUNTIME`.
- Each runner sees only its world's containers (`pinecall.world`), so two share a machine; an app's
  network is DNS-less and on a bridge of the runner's own (`pca…`), the only one the fence matches;
  the install's HOME is a scratch folder on disk. From a terminal: `pinecall deploy` and `pinecall secrets` (pinecall 0.9.10).
- A hosted app stopped and started (`POST /v1/hosted/{name}/stop`·`start`: its process drains, its
  releases and token stay), rolled back on the gateway (`POST …/rollback {release}`), and its logs
  read (`GET …/logs`: the runner sends its container's last 300 lines on the beat after they are
  asked for). The time each app served is counted per UTC day while a process of the org runs under
  one of its hosts: `GET /v1/hosted/usage`, and every org's at `GET /v1/ops/hosted-usage`, for a
  billing layer. Migration 0021.
- The hosting code reviewed, end to end. An org's secrets no longer ride podman's environment,
  which is root's (a secret named `LD_PRELOAD` was root's to run): the runner writes each host's
  environment to a tmpfs (`PINECALL_RUNNER_ENVIRONMENTS`, `/run/pinecall-runner/<world>`),
  mounted read-only into that container, and its shell reads it. A live host whose process exits
  is run again, its last lines kept as the app's logs; five exits in ten minutes and it is failed.
  Each app's steps run in a task of their own, planned from numbers alone (`runner/_plan.py`); a
  report is never lost to a beat that fails; release folders, environments and networks nothing
  uses are swept. A host's name is stamped with the org and the world, an app's name is 40
  characters at most, and the runner reads the gateway leniently (`live_host` is new): upgrade
  the runner first. The time served is counted in one statement a beat; an upload is capped while
  it streams. The operator's `pinecall-runtime` wrapper writes no bytecode, so a verb run as root
  no longer breaks the next release.
