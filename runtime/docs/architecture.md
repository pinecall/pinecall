# Architecture — what each folder does, and what it may import

One package, `runtime/` (PyPI `pinecall-runtime`), shaped like a Rails application: one folder per
bounded context, every domain the same files, in a fixed bottom-up order no domain imports against.
`CONTRIBUTING.md` is the canon (the layout, the rules, the vocabulary); `tests/conventions/` holds
it as tests that fail the commit. This page says what each folder is for and how a call moves
through them. Every fact of a call is an entry appended to the call's log, and everything else (the
app socket, the console, the fold of its state, the usage feed) reads entries. The media side is
LiveKit's `AgentSession`, used as is.

The package is being written bottom up. The gateway's domains are in the tree up to `studio/`; the
worker's side (`jobs/`, `worker.py`), the runner's (`hosts/`, `runner.py`), `retention/` and the
operator's terminal (`cli/`) are named here as the canon lays them out and are not in the tree yet.

## If you know Rails

The same shape, with the names Python and FastAPI give things. One app, one database, convention
over configuration: a file is where its name says, and does one thing.

| in Rails | here | one example |
|---|---|---|
| `config/routes.rb` | `api.py` mounts each domain's router; the paths are on the endpoints | `@router.get("/v1/agents/{slug}/settings")` |
| `app/controllers/` | `<domain>/endpoints.py`: dependencies, one service call, a schema back | `agents/endpoints/settings.py` |
| `app/models/` (the tables) | `<domain>/models.py`: one SQLAlchemy class per table, declaring and never querying, and what the table keeps (`Kept`) | `agents/models.py` · `AgentConfig` |
| ActiveRecord queries, scopes | `<domain>/repository.py`: every statement on the domain's tables, returning models or a typed row | `AgentConfigRepository.find_newest` |
| `app/services/`, the model's business methods | `<domain>/service.py`: the rules and the use cases, as functions that take and return values; the domain's errors | `setting_writes.put_settings` |
| strong parameters, serializers | `<domain>/schemas.py` (pydantic): what an endpoint reads and answers; `wire/` for what crosses a process | `PutSettingsRequest`, `SettingsResponse` |
| `before_action`, Pundit | `<domain>/auth.py`: which scopes open which endpoints, and the resource a path names, loaded and authorised, as dependencies | `WordsKey`, `KnownAgent` |
| ActiveJob, cron | `<domain>/tasks.py`: the loops the domain owns, each one pass declared with `@loop` and started by the lifespan | `live/tasks.py` · the reaper |
| `db/migrate/` | `migrations/` (Alembic), shipped in the wheel; an applied revision is never edited | `20261016_000001_call_facts_hold_the_line.py` |
| `config/application.rb`, credentials | `config.py` (every variable, one place), the vault for every secret the box holds | `PINECALL_DB_POOL` |
| `lib/` | `kit/`: generic code with no business noun in it | `kit/sse.py`, `kit/websockets.py` |
| `bin/rails`, rake tasks | `cli/`: the operator's terminal, one module per group of verbs | `pinecall-runtime facts rebuild` |
| the application record | **the call's log**: every fact of a call is an entry appended to it; summaries, facts, usage and state are read models folded from it | `calls/log/store.py`, `calls/folds/facts.py` |

Where Rails has one process, this has three: the **gateway** (`app.py`, the API and every socket),
the **worker** (`worker.py`, one LiveKit job per spoken call) and the **runner** (`runner.py`, the
apps the box hosts). They share the database and talk through it, through the signal between
gateways (Redis) and through the gateway's own endpoints; a worker never opens the database.

A request's path, in five lines: `api.py` finds the route → `auth.py`'s dependencies verify the
key and its scopes and load what the path names → `endpoints.py` reads the body as a `schemas`
shape → one `service.py` function decides, reading and writing through `repository.py` → the
answer is a `schemas` shape built from the value the service returned, and a refusal is a
`PinecallError` with its status, answered by the one handler in `app.py`.

## The layout

```
src/runtime/
  app.py lifespan.py builders.py api.py worker.py runner.py cli/   the entrypoints: they build and wire, nothing else
  config.py enums.py exceptions.py         one process's words: its settings, the shared enums, the errors
  actor.py auth.py scoping.py              who a request is, how its key is resolved and required, the org it is scoped to
  postgres.py signal.py redis.py livekit.py one process's connections
  shared_state.py handles.py               what the gateways hold in common, and one process's handles with their getters
  kit/            the toolkit: generic code, no business noun, imports nothing above itself
  wire/           every shape that crosses a process: the SDKs' protocol, and what the gateway,
                  its workers, its runner and the other gateways tell each other; golden-pinned
  <domain>/       models.py schemas.py repository.py service.py auth.py endpoints.py tasks.py, each a package when it grows
  migrations/     Alembic, shipped in the wheel; migrations/sql/ is the history that made the live schema
```

A domain owns its tables (`models.py`: one SQLAlchemy class each; `calls/models/` is a package);
its `endpoints` call services and read schemas; a `service` holds the rules and the use cases as
functions that take and return values, never a schema; a `repository` holds every statement on the
domain's tables; `auth` names which scopes open which endpoints and loads what a path names;
`tasks` the loops the lifespan starts. Across domains, a module imports the `service` of a domain
**below** it, as a module (`from runtime.billing import service as billing`), never a name out of
it and never upwards; what a lower domain needs of a higher one it declares as a `Protocol` and is
handed by the entrypoint. A domain reads a lower domain's `models` as its own. A few value modules
are read by any domain as `models` is, each named in `CONTRIBUTING.md`: what an agent declares and
what the org sets on it (`agents/declaration.py`, `agents/settings.py`), what a call is and how it
is projected (`calls/context.py`, `calls/projection.py`, `calls/recordings.py`), a stage as values
and the providers row (`providers/stage.py`, `providers/catalog.py`). Endpoints may call any
domain's service; nothing imports an `endpoints` module but `api.py`.

## The domains, bottom up

| domain | what it holds |
|---|---|
| `platform/` | the box's own: its named settings, the brand, attempts counted, the schema brought to this release (`service/schema.py`: the SQL history on a new database, then Alembic's revisions), the database's health, the pages the box serves |
| `billing/` | quotas and admission: an org's limits in an env against what it used there, before it uses more; the usage totals the database's triggers keep, and their rebuild |
| `mail/` | the emails the box sends: the mailboxes it sends through, the outbox, and the frame every email is set in |
| `accounts/` | who is asking: orgs, their members, the people they are, keys (and the keys a gateway verified lately), and the actor a key resolves to |
| `signin/` | how a person gets a key: a password, a one-use code, a paired terminal, a sign-up, the org's own provider (SSO), Google |
| `compliance/` | what an org owes: its policy (retention, what a call says first), who read what, a recording's own key, consent, and what it may dial (the guards, the ledger of dials) |
| `providers/` | the providers row (the catalog: defaults, models, voices, rates, the judge's and the caller's models, the embedder), the vendors this build runs (livekit's plugins), the keyring a call runs on and what the box lends, the stages built, prices, voices, where an org's traces go |
| `agents/` | an agent as the gateway holds it: what its class declares (`declaration.py`), what the org sets on it per scope (`settings.py`) and the version on a canary's share, the lexicon, the widget's look, the hold audio, its lines and documents |
| `knowledge/` | knowledge bases with their cutter and hybrid search, contact memory, what a call taught at hang-up, the embedder, the goldens of the index and of memory |
| `whatsapp/` | Meta's Cloud API: the webhook it delivers to, a reply sent, and every message read once |
| `fleet/` | who takes a call, the gateway's choice and not LiveKit's draw: the fleet each env dispatches to, the roster of workers heard, a room kept until a worker opens it and offered to the worker with the most slots free, the sweep |
| `telephony/` | the phone network: an org's accounts at its carriers, numbers imported and bought and the agent each reaches (the routes), the carriers the box knows and the networks 5060 opens to (the fence), the SFU's trunks and rules, a call's legs in its room, a ring handed to the sandbox |
| `session/` | one LiveKit `AgentSession` for voice and text, in a worker or in the gateway: the pipeline built, every turn, tool call and metric written as an entry, the call's time, the room, hold music, tools, the widget's channel, the recording |
| `judging/` | what a judge and a persona are, Pinecall's library of both (`library/`), a finished call as a judge reads it, the hang-up panel, cases grouped |
| `alerts/` | what an org is told (a monitor crossed, the spend unusual, a quota out, a vendor that failed a call), on the agent's log and posted to its webhook; and the operators' own, a newborn org with no call that went well |
| `calls/` | the log, which is the record: the store and its writer, the relay between gateways, the logs open in this process and their feeds (`log/`); what is folded from a log, its state, facts, usage, latencies and phone legs (`folds/`); and what is listed, read and metered of a call |
| `insights/` | each sealed call folded into its day, and the windows of whole days read back from the folds |
| `live/` | a call while it is served: opened, bound to the app socket that holds its agent, parked and handed on, commanded, sealed once; the app socket, the WhatsApp threads, the dial, a visitor's way in with its tokens and codes, the supervisor's desk, the reaper |
| `flows/` | what an app does around its calls: the events an app is owed until its process hears them, and its flows' runs, each a journal of steps with the time, the event or the call that wakes it; the function runs in the app's process, never here |
| `evals/` | the harness above the calls: a run of goldens and its matrix, the simulated caller on a line (written or spoken, its ambience and tempo), setups compared, a replay, the calibration |
| `hosting/` | the apps the box runs for an org, the gateway's side: releases, secrets, the runner's beats, an app's page, and the time each served |
| `studio/` | an agent built in the console: its definition checked and declared as an SDK would, its tools' requests held to the public internet, the gateway holding it on an app socket of its own, its export as a class |
| `retention/` | what the box keeps and forgets across every domain: the nightly run, erasure (a call, a contact, an org, an agent) and its trail, the export |
| `jobs/` | the worker's side of the box: its client to the gateway (every endpoint it calls, its batches down one socket per call), its heartbeat and the last minute it carries, the job that runs one call, the overflow's sentence, the recorder, the traces |
| `hosts/` | the runner's side: its client to the gateway, the plan of each beat, and the two places it runs an app's process, a pod on the hosting cluster or a process of this machine |

Below them, `kit/` holds what has no business noun (the vault, the repository's base, a commit's
after-effects, the declared loops, SSE, WebSockets, S3, Opus, Prometheus text, the sealed file,
DNS, time, text), `enums.py` the words every table and wire shape share, `wire/` every shape that
crosses a process; `config.py` every variable, `exceptions.py` every error with its HTTP status,
`actor.py` and `auth.py` who a request is, `postgres.py` the engine, the sessions and row-level
security, `signal.py` and `redis.py` the signal the gateways tell each other things on,
`livekit.py` each env's LiveKit client.

Above them, the entrypoints build objects from settings and nothing else: `lifespan.py` wires the
gateway once (the engine, the vault, LiveKit, the signal, the logs, the live side, the roster) with
`builders.py`, and starts every loop a domain declared; `app.py` is the FastAPI app, its middleware
and the one handler a refusal is answered by; `api.py` mounts every domain's router, the box's
pages last; `worker.py` is livekit's `AgentServer` under the fleet's name, and the fleet's
overflow; `runner.py` the runner of hosted apps; `cli/` the operator's terminal, one module per
group of verbs, each verb a typed function that calls a service or the gateway's operator
endpoints.

## The path of a call

1. A carrier or a browser reaches LiveKit; LiveKit dispatches the room to the fleet of the
   call's env (`PINECALL_FLEET`), and a worker takes the job (`jobs/`).
2. The job asks the gateway to open the call (`POST /v1/calls`, `live/service/openings.py`): the
   gateway writes `call.ringing` to a new log (an outbound call's first entry, `call.dialing`, was
   written when it was placed), finds the agent's app socket, and answers the minutes left.
   `call.started` is the session's, once the media is up.
3. `session/voice.py` builds the pipeline from the org's providers, `session/session.py` starts
   the `AgentSession` and writes every turn, tool call and metric as an entry. The entries travel
   in batches (`session/writing.py`): one task per call sends whatever is queued, up to 64, down
   the call's socket (`WS /v1/calls/{call}/entries`), and while it is out the next batch fills, so
   an idle call sends each entry alone and a busy one batches itself. Each entry is stamped when
   it is queued. Past 4 096 waiting, an ephemeral entry is shed; a durable one never is. In the
   gateway every append of every call goes through one writer (`calls/log/writer.py`) and its two
   lanes, one transaction at a time each: what arrives while a transaction is out, up to 500
   entries, is the next group, the heads locked and read in one statement, the facts folded once.
   A log is in a group once, so its seqs keep the order its requests came in. Each request is
   answered after its commit.
4. A tool call crosses the app socket (`live/service/socket.py`, behind `WS /v1/apps`) to the
   tenant's process and back; the gateway writes `tool.call` and `tool.result`.
5. At hang-up the job seals the log (`POST /v1/calls/{call}/sealed`, `live/service/seal.py`):
   the summary, the price, memory and the judges' verdicts are folded from the entries. A call is
   sealed once: a second request waits for the first, and a seal that broke after its summary goes
   on from the score.

## What is retried, and what never is

A retry is written only where doing a thing twice changes nothing, or where not doing it loses
something a call cannot get back. The worker's client (`jobs/`, on `kit/retry.py`) retries
while the gateway is away (unreachable, or a `5xx`), waiting 0.5 s and doubling to 5 s; a `4xx`
is an answer and is never retried.

| what | retried how | why | where |
|---|---|---|---|
| a batch of a call's entries, every one a worker writes | without limit, the same batch after the same `after` | a call has one writer from its open to its seal, and the head counts what it took, so a retry is answered with the seqs it was given; an entry dropped is a hole in the log | `jobs/` (the worker's client), `session/writing.py`, `live/service/entries.py`, `calls/log/store.py` |
| a tool call | while the gateway is away, up to the tool's `timeout_s` (30 s unless declared) plus 5 s | the gateway runs one round trip per call id: a retry joins the one still running, and one already finished is answered with the `tool.result` the log holds and never sent to the app again, since a tool may book or charge | `jobs/` (the worker's client), `session/tools.py`, `live/service/tools.py`, `live/tool_calls.py` |
| the seal | within 30 s | a call is sealed once: the gateway that takes the head's lease seals it, a second request on any gateway waits for the head to say sealed | `jobs/` (the worker's client), `live/service/seal.py` |
| a call nothing sealed | every 60 s: a spoken call silent 5 min with no agent in its room, a written one quiet 5 min (2 h on WhatsApp), a written one parked by a process that drained and taken by no other within 2 min (`app_detached`), after being handed to any process that took its agent since; a call another gateway sealed, or one erased, is let go of | a worker that dies writes no `call.ended`; a process that left promised the next one, which never came; a call counts against its org's `concurrent_calls` on the gateway that opened it until then | `live/tasks.py`, `live/service/reaper.py`, `live/service/handoff.py` |
| the commands stream | reopened without limit; a `4xx` ends it | each command travels under an id of its own: a worker that loses the stream asks again, of any gateway, and drops what it applied | `live/endpoints/worker.py`, `jobs/` |
| the heartbeat | every 5 s, whatever the last one answered | the worker keeps its calls while the gateway is away | `jobs/` |
| a tool call whose app's socket went | sent again to the socket that takes the call over | the model is still waiting on that call id | `live/service/handoff.py`, `session/tools.py` |
| an embedding | two more tries on a transport error, `408`, `409`, `429` or `5xx`, 0.5 s doubling to 8 s or the server's `retry-after` up to 60 s; a batch too big is split in halves | an embedding is the same vector however often it is asked | `knowledge/service/embedder.py` |
| a vendor's stream (ears, model, voice) | livekit's own: 3 retries 2 s apart; the session closes after 3 unrecoverable errors of a stage | a refusal that never succeeds ends the call on the first | `session/session.py`, `session/listener.py` |
| a reader's stream (SSE) | the client reconnects after 1 s and resumes from `Last-Event-ID` | stored before published: nothing is lost between two reads | `kit/sse.py`, `calls/endpoints/logs.py` |
| Meta's webhook | Meta delivers again for 7 days | each message id is claimed once per org before it is read | `live/service/whatsapp.py`, `whatsapp/service.py` |

| never retried | what happens instead | why | where |
|---|---|---|---|
| a dial | a dispatch LiveKit refuses ends the call `dial_failed`; a far end that does not answer ends and seals it; each dial is one row of the ledger, counted against the org's pace and the number's day | a person is never dialled twice by a retry | `live/service/dialing.py`, `jobs/`, `compliance/service/dial_guards.py` |
| a ring handed to the sandbox by SIP | the leg rings 10 s at most; one the sandbox does not answer leaves the ring with production's agent | the caller is never left with nobody | `telephony/service/hand_over.py` |
| a lookup (recall, search) | the turn waits 250 ms spoken, 3 s written, and goes on without what did not come back | a turn is waiting | `session/lookups.py`, `knowledge/service/lookups.py` |
| opening a call | once; a gateway away fails the job | opening writes `call.ringing` and counts the call against the quota | `jobs/` (the worker's client), `live/service/openings.py` |
| the tenant's app | a tool unanswered by its `timeout_s` is an error the model reads in the same turn; a console's verb waits 120 s | the app's side effects are the app's: the platform never sends a call twice | `session/tools.py`, `live/service/dev.py` |
| a reply to a WhatsApp contact | Meta's refusal is an `error` entry `whatsapp_not_sent` on the call | a send whose answer was lost may have reached the contact | `live/service/whatsapp.py` |
| a judge | a judge whose model broke is skipped and says why; the call seals all the same | the seal never fails on a judge | `judging/service/judges.py`, `live/service/seal.py` |
| memory at hang-up | one try within 8 s unless the settings say; what fails is logged | memory is a courtesy to the next call | `live/service/seal.py` |
| the overflow's sentence | said once, then a phone caller's call back is written down | the caller hears it once | `jobs/` |
| Twilio's API | one request, 30 s; its refusal is its own sentence | an import or a purchase waits for a person, never a call; a purchase twice is two numbers | `telephony/service/twilio.py` |
| a statement to Postgres | the endpoint answers `503` | the worker's client outlasts it; the gateway holds no retry of its own | `postgres.py`, `app.py` |
