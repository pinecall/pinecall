# Architecture — what each folder does, and what it may import

One package, `pinecall_runtime/`, shaped like a Rails application: one folder per bounded context,
every domain the same files, in a fixed bottom-up order no domain imports against.
`CONTRIBUTING.md` is the canon (the layout, the twelve rules, the vocabulary); `tests/conventions/`
holds it as tests that fail the commit. This page says what each folder is for and how a call
moves through them. Every fact of a call is an entry appended to the call's log, and everything
else (the app socket, the console, the reducer, the usage feed) reads entries. The media side is
LiveKit's `AgentSession`, used as is.

## If you know Rails

The same shape, with the names Python and FastAPI give things. One app, one database, convention
over configuration: a file is where its name says, and does one thing.

| in Rails | here | one example |
|---|---|---|
| `config/routes.rb` | `api.py` mounts each domain's router; the paths are on the endpoints | `@router.get("/v1/agents/{slug}/settings")` |
| `app/controllers/` | `<domain>/endpoints.py`: a dependency, a body, one service call, a schema back | `agents/endpoints/settings.py` |
| `app/models/` (the tables) | `<domain>/models.py`: one SQLAlchemy class per table, declaring and never querying | `agents/models.py` · `AgentConfig` |
| ActiveRecord queries, scopes | `<domain>/repository.py`: every query on the domain's tables, returning models | `AgentConfigRepository.newest_version` |
| `app/services/`, the model's business methods | `<domain>/service.py`: the rules and the use cases, as functions; the domain's errors | `settings.write_tuning` |
| strong parameters, serializers | `<domain>/schemas.py` (pydantic): what an endpoint reads and answers; `wire/` for what the SDKs implement | `PutSettingsRequest`, `SettingsResponse` |
| `before_action`, Pundit | `<domain>/auth.py`: which scopes open which endpoints, as dependencies | `WordsKey`, `KnownAgent` |
| ActiveJob, cron | `<domain>/tasks.py`: the loops the lifespan starts; a run or a simulation is a task of the gateway | `calls/tasks.py` · the reaper |
| `db/migrate/` | `migrations/` (Alembic), shipped in the wheel; an applied revision is never edited | `20261016_000001_call_facts_hold_the_line.py` |
| `config/application.rb`, credentials | `config.py` (every variable, one place), the vault for every secret the box holds | `PINECALL_DB_POOL` |
| `lib/` | `kit/`: generic code with no business noun in it | `kit/sse.py`, `kit/websockets.py` |
| `bin/rails`, rake tasks | `cli/`: the operator's terminal, a Typer app, one module per group of verbs | `pinecall-runtime facts rebuild` |
| the application record | **the call's log**: every fact of a call is an entry appended to it; summaries, facts, usage and state are read models folded from it | `calls/store.py`, `calls/facts.py` |

Where Rails has one process, this has three: the **gateway** (`app.py`, the API and every socket),
the **worker** (`worker.py`, one LiveKit job per spoken call) and the **runner** (`runner.py`, the
apps the box hosts). They share the database and talk through it, through Redis's signal and
through the gateway's own endpoints; a worker never opens the database.

A request's path, in five lines: `api.py` finds the route → `auth.py`'s dependency verifies the
key and its scopes → `endpoints.py` reads the body as a `schemas` shape → one `service.py` function
decides, reading and writing through `repository.py` → the answer is a `schemas` shape, and a
refusal is a `PinecallError` with its status, answered by the one handler in `app.py`.

## The layout

```
src/pinecall_runtime/
  app.py api.py worker.py runner.py cli/      the entrypoints: wiring only; cli/ one module per group of verbs
  config.py exceptions.py postgres.py redis.py livekit.py   one process's foundations
  kit/            the toolkit: generic code with no business noun in it
  enums.py        the words every table and wire shape share (Env, Channel, Role, …)
  wire/           the protocol the SDKs implement (events, commands, state, metrics); golden-pinned
  migrations/     Alembic, shipped in the wheel; migrations/sql/ is the history that made the live schema
  <domain>/       models.py schemas.py repository.py service.py auth.py endpoints.py tasks.py, each a package when it grows
```

A domain owns its tables (`models.py`: one SQLAlchemy class each; `calls/models/` is a package,
having fourteen); its `endpoints` call services and read schemas; a `service` holds the rules and the use
cases as functions; a `repository` holds every query on the domain's tables and returns models;
`auth` names which scopes open which endpoints; `tasks` the loops the lifespan starts. Across
domains, a module imports the `service` of a domain **below** it, as a module
(`from pinecall_runtime.billing import service as billing`), never a name out of it and never
upwards; a domain reads a lower domain's `models` as its own, and a `schemas` module a lower
domain's schemas. Two value objects are read by any
domain as `models/` is: `agents/declaration.py` (what an agent declares) and `calls/context.py`
(what a call is). Endpoints may call any domain's service; nothing imports an `endpoints` module
but `api.py`.

## The domains, bottom up

| domain | what it holds |
|---|---|
| `platform/` | the box's own: its settings row (`box_settings`), the brand, the schema brought to this release (`service/schema.py`: the SQL history on a new database, then Alembic's revisions), the WAL archive for `doctor`, the pages the box serves (the widget's files, the console at every other path) |
| `billing/` | quotas and admission: an org's limits in an env against what it used there, before it uses more; the usage totals the database's triggers keep, and their rebuild |
| `accounts/` | orgs, members, keys (and the keys a gateway verified lately), sign-in (a password, a one-use code, a paired terminal, a sign-up), SSO, the tokens the gateway signs, the emails the box sends and the mailboxes it sends through |
| `compliance/` | the org's policy (retention, what a call says first), who read what, a recording's own key, the org's OTLP collector |
| `providers/` | the providers row (the catalog: defaults, models, voices, rates, the judge's and the caller's models, the embedder), the vendors this build runs (livekit's plugins), the keyring a call runs on and what the box lends, the three stages built, prices, voices |
| `agents/` | an agent as the gateway holds it: its declaration (`declaration.py`), the registry of app sockets across every gateway, its settings per scope and the version on a canary's share, the lexicon, the prompts a call was told, the widget's look, the hold audio |
| `knowledge/` | knowledge bases with their cutter and hybrid search, contact memory, a call's lookups written on its log, what a call taught at hang-up, the embedder |
| `channels/` | where a conversation comes in and which agent answers it: the routes (number or channel to agent, per org and env) and WhatsApp's API |
| `fleet/` | who takes a call, the gateway's choice and not LiveKit's draw: the fleet each env dispatches to, the roster of workers heard, a room kept until a worker opens it and offered to the worker with the most seats free, LiveKit's word that a person is alone in a room, the sweep |
| `telephony/` | the phone network: a call's legs in its room, the carriers the box knows and admits and the networks 5060 opens to (the fence), the org's accounts at its carriers, numbers imported and bought, dialling out and its guards, consent, a developer's own phone at a production number handed to the sandbox, the SIP trunks and rules on each env's LiveKit |
| `session/` | one LiveKit `AgentSession` for voice and text: the pipeline built, every turn, tool call and metric written as an entry, the call's time, the room, hold music, tools, the widget's channel, the recording |
| `judging/` | what a judge and a persona are, Pinecall's library of both (`library/`), a finished call as a judge reads it, the hang-up panel, calibration, cases grouped and a fix proposed, a golden's turns and their checks |
| `alerts/` | an alert of the org's — a monitor fired, the spend unusual, a quota out — on the agent's log and posted to its webhook |
| `calls/` | the log, which is the record: the store and its writer (`store.py`, `writer.py`), the relay between gateways, the logs open in this process and their readers, the facts folded at write and read back, the reducer and the two read projections, the metering; and the call as the gateway serves it: opened, served, bound to a socket, sealed (memory, the bill, the judges), reaped when nobody ends it, a written call and a WhatsApp thread, the desk, the dev relay, usage and insights, `/metrics` |
| `evals/` | the harness above the calls: a run of goldens and its matrix — answered as it starts and played on a task of the gateway, its row rewritten as each golden is judged — the simulated caller (written or spoken, its ambience and tempo), a replay, the eval suites |
| `hosting/` | the apps the box runs for an org: releases, secrets, the runner's beats and the cluster it starts pods on |
| `studio/` | an agent built in the console: its definition checked and turned into a declaration, its tools' requests held to the public internet, the gateway holding it on an in-memory app socket, its export as a class |
| `retention/` | what the box keeps and forgets across every domain: the nightly run, erasure (a call, a contact, an org, an agent) and its trail, the export, the vault key rotated over every sealed column |
| `jobs/` | the worker's side of the box: its client to the gateway (every endpoint it calls, its batches down one socket per call), its heartbeat and the last minute it carries, the job that runs one call, the overflow's sentence, the recorder, the traces, the load lab |

Below them, `kit/` holds what has no business noun (the auth dependency, the vault, SSE,
WebSockets, S3, Opus, Prometheus text, the sealed audio, time, text), `enums.py` the words every
table and wire shape share, `wire/` the protocol; `config.py` every variable, `exceptions.py` every error with its
HTTP status, `postgres.py` the engine, the sessions and row-level security, `redis.py` the signal
the gateways tell each other things on, `livekit.py` each env's LiveKit client.

Above them, the entrypoints build objects from settings and nothing else: `app.py` wires the
gateway once in its lifespan (the engine, the vault, LiveKit, the signal, the logs, the registry,
the roster, the loops) and holds the one handler a refusal is answered by; `api.py` mounts every
domain's router, the box's pages last; `worker.py` is livekit's `AgentServer` under the fleet's
name, and the fleet's overflow; `runner.py` the runner of hosted apps; `cli/` the operator's
terminal, a Typer app, one module per group of verbs, each verb a typed function that calls a
service or the gateway's operator endpoints.

## The path of a call

1. A carrier or a browser reaches LiveKit; LiveKit dispatches the room to the fleet of the
   call's env (`PINECALL_FLEET`), and a worker takes the job (`jobs/service/job.py`).
2. The job asks the gateway to open the call (`POST /v1/calls`, `calls/service/worker.py`): the
   gateway writes `call.ringing` to a new log (an outbound call's first entry, `call.dialing`, was
   written when it was placed), finds the agent's app socket, and answers the minutes left.
   `call.started` is the session's, once the media is up.
3. `session/voice.py` builds the pipeline from the org's providers, `session/session.py` starts
   the `AgentSession` and writes every turn, tool call and metric as an entry. The entries travel
   in batches (`session/writing.py`): one task per call sends whatever is queued, up to 64, down
   the call's socket (`WS /v1/calls/{call}/entries`), and while it is out the next batch fills, so
   an idle call sends each entry alone and a busy one batches itself. Each entry is stamped when
   it is queued. Past 4 096 waiting, an ephemeral entry is shed; a durable one never is. In the
   gateway every append of every call goes through one writer (`calls/writer.py`) and its two
   lanes, one transaction at a time each: what arrives while a transaction is out, up to 500
   entries, is the next group, the heads locked and read in one statement, the facts folded once.
   A log is in a group once, so its seqs keep the order its requests came in. Each request is
   answered after its commit.
4. A tool call crosses the app socket (`calls/service/socket.py`, behind `WS /v1/apps`) to the
   tenant's process and back; the gateway writes `tool.call` and `tool.result`.
5. At hang-up the job seals the log (`POST /v1/calls/{call}/sealed`, `calls/service/seal.py`):
   the summary, the price, memory and the judges' verdicts are folded from the entries. A call is
   sealed once: a second request waits for the first, and a seal that broke after its summary goes
   on from the score.

## What is retried, and what never is

A retry is written only where doing a thing twice changes nothing, or where not doing it loses
something a call cannot get back. The worker's client (`jobs/service/stream.py`, `again`) retries
while the gateway is away (unreachable, or a `5xx`), waiting 0.5 s and doubling to 5 s; a `4xx`
is an answer and is never retried.

| what | retried how | why | where |
|---|---|---|---|
| a batch of a call's entries, every one a worker writes | without limit, the same batch after the same `after` | a call has one writer from its open to its seal, and the head counts what it took, so a retry is answered with the seqs it was given; an entry dropped is a hole in the log | `jobs/service/client.py` `append_many`, `session/writing.py`, `jobs/service/ending.py` `open_writer`, `calls/store.py` |
| a tool call | while the gateway is away, up to the tool's `timeout_s` (30 s unless declared) plus 5 s | the gateway runs one round trip per call id: a retry joins the one still running, and one already finished is answered with the `tool.result` the log holds and never sent to the app again, since a tool may book or charge | `jobs/service/client.py` `tool`, `session/tools.py`, `calls/repository/entries.py` `tool_answered` |
| the seal | within 30 s | a call is sealed once: the gateway that takes the head's lease seals it, a second request on any gateway waits for the head to say sealed | `jobs/service/client.py` `sealed`, `calls/service/seal.py` |
| a call nothing sealed | every 60 s: a spoken call silent 5 min with no agent in its room, a written one quiet 5 min (2 h on WhatsApp), a written one parked by a process that drained and taken by no other within 2 min (`app_detached`) | a worker that dies writes no `call.ended`; a process that left promised the next one, which never came | `calls/tasks.py`, `calls/service/reaper.py` |
| the commands stream | reopened without limit; a `4xx` ends it | commands have no seq: a worker that loses the stream asks again | `jobs/service/job.py` |
| the heartbeat | every 5 s, whatever the last one answered | the worker keeps its calls while the gateway is away | `jobs/service/heartbeat.py` |
| a tool call whose app's socket went | sent again to the socket that takes the call over | the model is still waiting on that call id | `calls/service/binding.py`, `session/tools.py` |
| an embedding | two more tries on a transport error, `408`, `409`, `429` or `5xx`, 0.5 s doubling to 8 s or the server's `retry-after` up to 60 s; a batch too big is split in halves | an embedding is the same vector however often it is asked | `knowledge/service/embedder.py` |
| a vendor's stream (ears, model, voice) | livekit's own: 3 retries 2 s apart; the session closes after 3 unrecoverable errors of a stage | a refusal that never succeeds ends the call on the first | `session/session.py`, `session/listener.py` |
| a reader's stream (SSE) | the client reconnects after 1 s and resumes from `Last-Event-ID` | stored before published: nothing is lost between two reads | `kit/sse.py`, `calls/endpoints/readers.py` |
| Meta's webhook | Meta delivers again for 7 days | each message id is claimed once per org before it is read | `calls/service/threads.py`, `channels/service/whatsapp.py` |

| never retried | what happens instead | why | where |
|---|---|---|---|
| a dial | a dispatch LiveKit refuses ends the call `dial_failed`; a far end that does not answer ends and seals it; each dial is one row of the ledger, counted against the org's pace and the number's day | a person is never dialled twice by a retry | `calls/service/dialing.py`, `jobs/service/job.py`, `telephony/service/dial_policy.py` |
| a ring handed to the sandbox by SIP | the leg rings 10 s at most; one the sandbox does not answer leaves the ring with production's agent | the caller is never left with nobody | `telephony/service/hand_over.py`, `telephony/service/sip.py` |
| a lookup (recall, search) | the turn waits 250 ms spoken, 3 s written, and goes on without what did not come back | a turn is waiting | `session/lookups.py`, `knowledge/service/lookups.py` |
| opening a call | once; a gateway away fails the job | opening writes `call.ringing` and counts the call against the quota | `jobs/service/client.py` `open` |
| the tenant's app | a tool unanswered by its `timeout_s` is an error the model reads in the same turn; a console's verb waits 120 s | the app's side effects are the app's: the platform never sends a call twice | `session/tools.py`, `calls/service/dev.py` |
| a reply to a WhatsApp contact | Meta's refusal is an `error` entry `whatsapp_not_sent` on the call | a send whose answer was lost may have reached the contact | `calls/service/threads.py` |
| a judge | a judge whose model broke is skipped and says why; the call seals all the same | the seal never fails on a judge | `judging/service/judges.py`, `calls/service/seal.py` |
| memory at hang-up | one try within 8 s unless the settings say; what fails is logged | memory is a courtesy to the next call | `calls/service/seal.py` |
| the overflow's sentence | said once, then a phone caller's call back is written down | the caller hears it once | `jobs/service/overflow.py` |
| Twilio's API | one request, 30 s; its refusal is its own sentence | an import or a purchase waits for a person, never a call; a purchase twice is two numbers | `telephony/service/twilio.py` |
| a statement to Postgres | the endpoint answers `503` | the worker's client outlasts it; the gateway holds no retry of its own | `postgres.py`, `app.py` |
