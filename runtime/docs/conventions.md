# Conventions — how a file of this runtime is written

`CONTRIBUTING.md` is the canon: the layout, the twelve rules and the vocabulary, each held by a
test under `tests/conventions/` that fails the commit. These are the choices a test cannot check,
and the reader is owed them in one place.

## Modules

- A module is at most 500 lines, a module of shapes (`schemas.py`, `wire/`) 800, an entrypoint
  300. What grows past it is two concerns: a `service.py`, `repository.py` or `endpoints.py`
  becomes a package of the same name, one module per noun, its `__init__.py` naming what other
  domains use.
- A folder holds at least two files; a concept with one file is a file, not a folder.
- A module is named for its concept, never a role: no `utils`, `helpers`, `base`, `manager`,
  `handler`, `factory`, `provider`, `adapter`.

## Names

- An endpoint's body is `<Verb><Noun>Request`; what it answers is `<Verb><Noun>Response`, or
  `<Noun>Row` when it is a row; the query of a listing is `<Noun>Query`: `OpenCallRequest`,
  `OpenCallResponse`, `OrgRow`, `InsightsQuery`.
- An event is a fact in the past tense: `CallStarted`, `ToolCalled`. A command is an imperative:
  `CallDial`, `AgentSay`.
- A repository or service function is `verb_object`: `get_org`, `list_keys`, `issue_key`,
  `erase_call`; never the past participle (`opened`, `kept`, `forgotten`). An endpoint function
  reads as its verb and noun too: `open_call`, `stream_org_events`. A parameter is `body`,
  `query`, `actor`, `session`, `scope`.
- A variable is the noun of what it holds: `entry`, `account`, `number`, `row`. A boolean reads
  as a question: `is_sealed`. A name that is a sentence (`a_blank_is_not_a_change`) is a comment,
  not a name. A data field keeps the wire's or the table's word, whatever it is.
- One word per concept, the vocabulary's: `endpoint`, `env`, `scope`, `actor`, `sign_in`,
  `one_time_secret`, `email`, `phone_leg`; the banned column is a test. A domain word is used
  only if `glossary.md` defines it.

## Data

- A pydantic model for what crosses a boundary and is validated there: the wire (`wire/`), an
  endpoint's body (`schemas.py`), a sealed credential, a row of `box_settings`. A row becomes a
  body with `Row.of(row)` (`model_validate` from its attributes), never a dict built by hand. The
  wire's models refuse unknown keys.
- `@dataclass(frozen=True)` for what the runtime builds and passes around itself: a scope, a plan,
  a claim, what a service answers to another.
- A `Literal` type is trusted once inside: the wire and the schema's enums enforce it; a
  `parse_*` refuses at the edge (the CLI, a column).
- No class with one public method: it is a function. A class only where state outlives one call:
  a store with its sessions, a session, the registry.

## Functions

- Five parameters at most, keyword-only after the second; a sixth is a dataclass. No boolean that
  selects a behaviour: two functions.
- Return early; nesting three deep at most; no `else` after `return`.
- A behaviour a command needs (voice only, a live room) is a `ClassVar` on the command's model,
  refused in one place in the session; never a chain of `isinstance` in a dispatcher.

## Errors

- Raise a class of `exceptions.py`, or a domain's own subclass declared in its `service`, with the
  sentence a person reads; the class carries the HTTP status and `app.py` has the one handler.
  `HTTPException` is never raised by hand.
- Never a bare `except`; a caught exception is re-raised as ours or logged with `exc_info=True`
  and the reason the call goes on.

## The database

- SQL lives in `repository.py` and the engine modules (`select`, `insert`, `update`, `delete`,
  `text()`); `models/` declares and never queries; a service never touches SQLAlchemy's query API.
- A request's session is one transaction, committed when the endpoint returns and rolled back when
  it raises (`postgres.Session`). A task of the box's opens its own (`sessions.begin()`), as the
  box (`box_task`) or as an org (`scope_to`).
- Every transaction of a tenant's request acts for the key's org (row-level security); an
  endpoint that reads across orgs on purpose says so with `box_wide()`.
- A statement past 30 s is cancelled; what is long on purpose (an erasure, an export, a rebuild)
  runs in `unbounded(session)`.
- The models mirror the live tables column for column (`org`, not `org_id`; `env`, not
  `environment`); `alembic check` is empty. An applied revision is never edited: the fix is a new
  one.

## Tasks and time

- Every task has an owner: a loop lives in its domain's `tasks.py`, is started by the lifespan
  and reported dead on `/metrics`; a task a request starts is awaited or cancelled by the object
  that holds it.
- Endpoints read time from the log's clock, so a test's clock and the window checks agree; no
  test sleeps real time.

## Comments and docstrings

- One-line docstring on every module, public function and class: one sentence about behaviour,
  no `Args:`/`Returns:` sections. The signature with its types is the argument list.
- A comment says only what the code cannot: an external fact, a trap, a reason, and names its
  source (an issue, a date, a vendor's document).
- A module docstring never defines the word with the word.

## Deprecating something on the wire

The first deprecation sets the pattern: the field or command keeps a `deprecated` class
attribute naming the version it goes and its replacement, and a test refuses one past its
version. Until then, nothing on the wire is deprecated.

## A migration

A deploy restarts the gateway, the workers and the migration at different moments, and rolling
back is installing the wheel before: so a migration never breaks the release before it. A change
of shape goes in three steps, each its own release: **expand** (add the new table or column, one
the old release need not write: nullable, or with a default), **release** (the code that reads
and writes the new shape and stops reading the old), **contract** (drop what nothing reads). A
revision is generated from the model (`alembic revision --autogenerate`) and read before it is
committed; the one that contracts names, in its docstring, the release that stopped reading what
it drops.
