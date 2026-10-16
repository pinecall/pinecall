# runtime — how to work here

The Pinecall runtime: one Python package (`pinecall_runtime`, PyPI `pinecall-runtime`), one wheel,
the gateway that answers the API and the worker that runs the calls, on LiveKit. It runs on
Kubernetes: the repository's `infra/`, beside this package, holds the charts and the Terraform.
Rewritten from zero on 2026-10-15 as a Rails-shaped Python application: **`CONTRIBUTING.md` is the
canon** (the layout, the twelve rules, the vocabulary) and this page only says how to work.

Code, comments, commits and pages are in English. A commit subject is a plain sentence saying
what is now true (`git log --oneline` shows the style).

## Commands

```
uv sync                           the venv and every dev tool (Python 3.13)
make check                        ruff (lint and format), pyright strict, mypy, the suites with no database
make test [T=tests/calls]         every suite on a local Postgres and Redis (colima; `make db`)
uv run alembic check              the models are the schema (empty diff)
make image                        the runtime's image at this commit
make deploy ENV=<env>             the chart released on the cluster at that image, then the live suite
make logs ENV=<env>               the gateways' and the workers' logs of the last hour
```

No suite runs on the laptop (`~/.claude/CLAUDE.md`): `~/pinecall-v2/tools/remote-test [pytest args]`
runs it on the test box, in the background.

## The map

`src/pinecall_runtime/`, one folder per bounded context, every domain the same files
(`models.py schemas.py repository.py service.py auth.py endpoints.py tasks.py`, each a package when
it grows), in a fixed bottom-up order a domain never imports against:

```
platform · billing · accounts · compliance · providers · agents · knowledge · channels
· fleet · telephony · session · judging · alerts · calls · evals · hosting · retention · jobs
```

Below every domain: `kit/` (the toolkit, no business noun), `wire/` (the protocol the SDKs
implement, golden-pinned), and the process's foundations (`config.py enums.py exceptions.py
postgres.py redis.py livekit.py`). Each domain owns its tables in its `models.py`. Above them: the entrypoints
(`app.py api.py worker.py runner.py` and the Typer app `cli/`), wiring only. `calls/` and
`session/` are engines with extra modules, named in the canon. `migrations/` (inside the package, so the wheel carries it) is
Alembic, the live schema its baseline; `migrations/sql/` is the history that made that schema, read,
never run.

## What the machine holds (`tests/conventions/`)

The canon's rules are tests: the layers (an AST walk of every import, no cycles), the canon's
files, the banned words, the sizes, `alembic check`, every raw `text()` statement prepared on the
test database with its JSON parameters typed, ruff and pyright strict with no suppression outside
the allow-list. `make check` runs them; the pre-commit hook (`make hooks`)
runs `make check` on a commit that touches `runtime/`.

`tests/conftest.py` is what every suite stands on: the test database migrated once, the catalog on
`acme` (`tests/fakes/acme.py`, a vendor installed as a livekit plugin, its model answering the
caller's last line), the gateway served by uvicorn on a free port, and a fresh org with its admin
and keys per test. `tests/app/` reaches that gateway as an SDK does: every GET answered to a valid
key without a server error, every tenant write refusing an empty body without one, the app
socket, the box's own key. `tests/test_postgres.py` holds row-level security as the app's role
meets it: a tenant reads and writes its own org alone. `tests/calls/` holds the engine: the
reducer, the meter, the latencies and the facts against the golden log, the store on Postgres
(contiguous seqs under concurrency, batches taken once, the seal and its lease, the append-only
table, a writer killed mid-append), and a whole written call, held, chatted, sealed and priced. `tests/session/` runs calls on livekit's
AgentSession with LiveKit faked (`tests/fakes/livekit.py`): the text and voice sessions, the
room, the tools' round trip, the prompt, hold music, the recording, the widget.
`tests/channels/` and `tests/telephony/` hold the routes, the legs, the hand-over, the dial
guards and a number imported, bought, moved and let go (Twilio and each env's LiveKit faked);
`tests/agents/` what a class declares; `tests/accounts/` keys and signing in;
`tests/billing/` the quotas; `tests/knowledge/` the embedder, bases, the hybrid search, a call's
lookups, memory and what a hang-up extracts, on Postgres; `tests/judging/` the judges, the cases
born at hang-up and decided, and calibration; `tests/hosting/` an upload checked and an app's
releases; `tests/jobs/` the worker's client on the served gateway, its socket and its retries.
`tests/wire/` pins the protocol to the SDKs' goldens.

## Decisions that stand

- **One gateway, one database, one name, two envs.** The env of a request is its key's or, for a
  person, the `pinecall-env` header's (the sandbox when it names none). Each env has its own
  worker fleet.
- **No vendor is named in code.** Every installed livekit plugin is a vendor; defaults, box keys,
  what the box lends and the prices are the providers row (the catalog), edited from the console.
- **The wire is ours** (`wire/`), pinned to the TypeScript and Ruby SDKs by `tests/wire/golden/`.
  Money is US dollars everywhere.
- **The log is the record**: every fact of a call is an entry appended to its log; facts, state and
  usage are read models folded from it (`calls/`).
- `PINECALL_VAULT_KEY` is required: it seals every key and secret the box holds.
- An applied migration is never edited; the fix is a new one. Each domain's models mirror its live
  tables column for column (`org`, not `org_id`).

## Secrets and what never gets committed

- Keys come from `~/.pinecall/credentials` into an env var and are never printed, logged,
  committed or pasted.
- Never committed: plans, notes, any operator's deployment (values, Terraform variables,
  addresses, buckets). This page is committed.
- Before a commit: `git ls-files --others --exclude-standard`, read whole.
