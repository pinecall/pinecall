# Contributing to the runtime

This package is written to one convention, so that anybody who knows the convention knows where
every line lives before they open the tree. The convention is held by `tests/conventions/`: a
file in the wrong place, a layer that imports upwards or a word from the banned list fails the
suite, not a review.

## The layout

```
src/pinecall_runtime/
  app.py api.py worker.py runner.py cli/         the entrypoints: wiring only; cli/ one module per group of verbs
  config.py exceptions.py postgres.py redis.py livekit.py   one process's foundations
  kit/            the toolkit: generic code with no business noun in it
  enums.py        the words every table and wire shape share (Env, Channel, Role, …)
  wire/           the protocol the SDKs implement (events, commands, state, metrics); golden-pinned
  <domain>/       a bounded context, always the same files (below)
  migrations/     Alembic, shipped in the wheel; the live schema is the baseline revision, never edited after
tests/            mirrors src/ one to one; tests/conventions/ holds this page
```

## A domain's files

Every domain folder holds these and nothing else. A file that would be empty is left out; the
names never change. One folder of data stands beside them: `judging/library/`, the judges' and the
personas' texts the box ships.

| file | holds | imports (of ours) |
|---|---|---|
| `models.py` | the domain's tables, one SQLAlchemy class each, named like the table, singular; a package (`calls/models/`) when they are many | `kit.db`, `enums` |
| `schemas.py` | the pydantic bodies its endpoints read and answer | `kit.schemas`, `enums`, `wire` |
| `repository.py` | every query on the domain's tables, as `Repository` subclasses; returns models | its `models` and lower domains', `kit.repository`, `postgres` |
| `service.py` | the rules and the use cases, as functions; the domain's errors | `repository`, `models`, `exceptions`, `kit`, `wire`, other domains' `service` |
| `auth.py` | the `Annotated` dependencies naming which scopes open which endpoints | `kit.auth`, `repository` |
| `endpoints.py` | the router: dependency → body → one service call → schema | `auth`, `schemas`, `service` |
| `tasks.py` | the background work the domain owns, started from the lifespan | `service` |

A `service.py`, `repository.py` or `endpoints.py` that outgrows one module becomes a package of
the same name, one module per noun (`calls/service/seal.py`, `knowledge/repository/memories.py`,
`accounts/endpoints/keys.py`), with the package's `__init__.py` naming what other domains use.

`calls/` and `session/` are engines and hold the extra modules listed here: `calls/` the log's
(`store`, `writer`, `relay`, `fanout`, `logs`, `facts`, `reducer`, `readers`, `private`,
`histogram`, `latencies`, `metering`, `recordings`, `context`); `session/` the call on LiveKit
(`call`, `writing`, `session`, `agent`, `prompt`, `tools`, `lookups`, `hearing`, `voice`, `text`,
`room`, `widget`, `hold`, `recording`, `clock`, `listener`, `echo`, `repeats`). An engine module imports
`repository`, `models`, `kit`, `wire` and the services of the domains below its own, never its
own `service`. `jobs/` is the worker's side of the box: its client to the gateway, its
heartbeat, and the job that runs one call; nothing in the gateway imports it. `retention/` is
what the box keeps and forgets across every domain: retention, erasure, export; it sits above
them all, since it deletes from their tables.

## The twelve rules

1. **Canon.** A domain folder contains only the files above.
2. **Layers.** Inside a domain: `endpoints` never imports `repository`, `models` or SQLAlchemy;
   `repository` never imports `service` or FastAPI; `service` never imports FastAPI; `models`
   imports `kit.db` and `enums` and nothing else of ours. Across
   domains, a domain imports the `service` of a domain **below** it, as a module
   (`from pinecall_runtime.billing import service as billing`), never a name out of it, and never
   upwards. The domains, bottom up:

   ```
   platform · billing · accounts · compliance · providers · agents · knowledge · channels
   · fleet · telephony · session · judging · alerts · calls · evals · hosting · studio · retention · jobs
   ```

   `judging` is what a judge and a persona are and how a finished call is read and judged; it sits
   below `calls` because the seal judges every call. `evals` is the harness that plays calls — runs
   of goldens, simulated callers, replays — and sits above them.

   A domain reads the `models` of a domain below it as it reads its own: a table is a table.
   A domain's value objects are the one exception that crosses the service rule, read by any domain:
   `agents/declaration.py` (what an agent declares) and `calls/context.py` (what a call is); they
   import nothing above `kit`, `enums` and `wire`. What a lower domain needs of a higher one is
   handed to it — a callable, or a `Protocol` the lower domain declares — never imported: the
   dial guard is handed whether a number ever called, the registry the logs it writes to.
   Endpoints are the top of every domain and may call any domain's service; nothing imports an
   `endpoints` module but `api.py`, and no `endpoints` module imports another.
3. **SQL at home.** `select`, `insert`, `update`, `delete` and `text()` appear only in
   `*/repository.py` and the engine modules. A `models` module declares and never queries.
4. **One table, one model, one owner.** Every `__tablename__` once, in the `models` of the domain
   that owns the table; `migrations/env.py` imports every domain's models, so Alembic's metadata is
   whole and `alembic check` is empty on `main`.
5. **Shapes.** pydantic models live in `wire/` and `*/schemas.py`, nowhere else. A row becomes a
   body with `Schema.model_validate(row)`, never a dict built by hand.
6. **Boring names.** Modules are nouns, functions are `verb_object`, classes are singular nouns.
   The vocabulary below names one word per concept; the banned words are a test.
7. **Errors.** Every error subclasses `PinecallError` and carries a `status`. A domain declares
   its own in `service.py`. `endpoints` never raise `HTTPException`; `app.py` has the one handler.
8. **Entrypoints wire.** Only `app.py`, `api.py`, `worker.py`, `runner.py` and `cli/` build
   objects from settings; each module is at most 300 lines. The CLI is a Typer app: a verb is a
   typed async function, as an endpoint is, that calls a service (or the gateway's operator
   endpoints through `cli/client.py`) and prints through `cli/output.py`; `cli/command.py` holds
   the one `Context` (connections opened on first use, closed after the verb) and the one way a
   verb fails (one sentence, exit 1; a misconfiguration, exit 2).
9. **Size.** A module is at most 500 lines; a module of shapes alone (`schemas.py`, `wire/`) at
   most 800. A `service.py`, `repository.py` or `endpoints.py` that grows becomes a package, one
   module per noun. A line is at most 120 characters, and `ruff format` writes every one.
10. **Tests mirror the tree** one to one, run on a real Postgres and Redis with LiveKit and the
    vendors faked, in parallel, each under ten seconds; the suite under five minutes.
11. **Every task has an owner:** a loop lives in its domain's `tasks.py` and is registered in the
    lifespan; one that dies is reported on `/metrics`.
12. **Comments say why.** A docstring is one line and says what. A comment is written only for a
    fact, a trap or a reason, and names its source (an issue, a date, a vendor's document).

## The vocabulary

One word per concept, everywhere: code, schemas, docs, logs.

| say | never | means |
|---|---|---|
| endpoint | door | one route of the API |
| env (`Env.production`, `Env.sandbox`) | world | one of an org's two environments |
| scope | corner | an org, an env and the holder a request acts as |
| actor | bearer, acting, reader | the verified key and person behind a request |
| sign_in, sign_in_attempt | knock | authentication and its rate limit |
| one_time_secret | word | a code or token spent once |
| email | letter | a message the box sends |
| phone_leg | leg | one side of a call on the phone network |
| fence | — | the networks a SIP trunk admits (kept: a telephony term) |
| entry | — | one line of a call's log (kept) |
| seal | — | the end of a call's log (kept) |
| dispatch | — | the gateway's choice of worker for a room (kept) |
| offer | — | a room put to a worker (kept) |
| lane | — | one of the writer's two queues (kept, engine only) |
| get_x / list_x / create_x / update_x / delete_x | the past participle (`opened`, `kept`, `forgotten`, `heard`, `said`) | a repository or service verb |

A name that is a sentence (`a_blank_is_not_a_change`) is a comment, not a name.

## The database

The runtime runs on the database the previous runtime left: every table is as its migrations made
it, and `models/` mirrors those tables column for column (`org`, not `org_id`; `env`, not
`environment`). A change to a table is an Alembic revision generated from the model and read
before it is committed. Applied revisions are never edited. The `call_log` triggers, the usage
functions and the row-level security policies are declared with `alembic-utils` so a revision can
carry them.

## Commands

```
uv sync                       the venv and every tool
uv run ruff check . && uv run ruff format --check .
uv run pyright && uv run mypy src
uv run alembic check          the models are the schema
uv run pytest                 the suite, in parallel, on the test database
```
