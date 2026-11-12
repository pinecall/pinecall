# runtime — how to work here

The Pinecall runtime: the gateway that answers the API and the worker that runs the calls, on
LiveKit. One Python package, `runtime` (`src/runtime/`, PyPI `pinecall-runtime`), deployed on
Kubernetes with the charts and the Terraform of the repository's `infra/`. **`CONTRIBUTING.md` is
the canon** (the layout, the rules, the vocabulary) and this page only says how to work.

Code, comments, commits and pages are in English. A commit subject is a plain sentence saying
what is now true (`git log --oneline` shows the style).

## Where the package stands

The package is being written, bottom up, domain by domain. Built: the foundations, the toolkit, the
wire, and every domain of the canon's order up to `jobs`: the gateway's side whole, and the worker's
(`worker.py`). Not built yet: `hosts` (the runner, `runner.py`) and the operator's terminal (`cli/`),
which is what starts a process. So **nothing runs from this tree yet**: no
image is built from it, `pinecall-runtime` is no command, and the `local*`, `image` and `deploy`
targets of the Makefile wait for the processes. The package it replaces, `pinecall_runtime`, left
the repository on 2026-11-12 (its last commit is `8c76bf0e`); production runs an image built before
that.

What is held meanwhile: `ruff`, `pyright` strict and `mypy` clean on the whole tree, and the
convention tests. A domain's behaviour tests are written when the processes exist.

## Commands

```
uv sync                           the venv and every dev tool (Python 3.13)
make check                        ruff (lint and format), pyright strict, mypy, the convention tests
```

No suite runs on a laptop here: the tests run on the project's test machine.

## The map

`src/runtime/`, one folder per bounded context, every domain the same files (`models.py schemas.py
repository.py service.py auth.py endpoints.py tasks.py`, each a package when it grows), in a fixed
bottom-up order a domain never imports against:

```
platform · billing · mail · accounts · signin · compliance · providers · agents · knowledge · whatsapp
· fleet · telephony · session · judging · alerts · calls · insights · live · flows · evals
· hosting · studio · retention · jobs · hosts
```

Below every domain: `kit/` (the toolkit, no business noun), `wire/` (the protocol the SDKs
implement), `migrations/` (Alembic, the live schema its baseline; `migrations/sql/` is the history
that made that schema, read, never run) and the process's foundations (`config.py enums.py
exceptions.py actor.py auth.py scoping.py postgres.py signal.py redis.py livekit.py shared_state.py
handles.py`). Each domain owns its tables in its `models.py`. Above them: the entrypoints (`app.py
lifespan.py builders.py api.py`), wiring only. `calls/`, `live/`, `session/` and `evals/` hold
engine modules beside the canon's files, each named in the canon.

## What the machine holds (`tests/conventions/`)

The canon's rules are tests: the layers (an AST walk of every import, no cycles), the canon's
files, the facades, the names and the banned words, the sizes, what an endpoint and a service may
hold, every model's retention, every raw `text()` statement prepared on the test database with its
JSON parameters typed, and no suppression of ruff or pyright. `tests/conftest.py` gives them the
test database, migrated once by the package's own migrations. `tests/wire/golden/` is the golden
call log the SDKs copy: when the wire moves, their copies move with it.

## Decisions that stand

- **One gateway, one database, one name, two envs.** The env of a request is its key's or, for a
  person, the `pinecall-env` header's (the sandbox when it names none). Each env has its own
  worker fleet.
- **No vendor is named in code.** Every installed livekit plugin is a vendor; defaults, box keys,
  what the box lends and the prices are the providers row (the catalog), edited from the console.
- **The wire is ours** (`wire/`), pinned to the SDKs by `tests/wire/golden/`. Money is US dollars
  everywhere.
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
