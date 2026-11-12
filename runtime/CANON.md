# Contributing to the runtime

> The canon of `src/runtime/`, the package being built beside `src/pinecall_runtime/`. At the cutover
> this page becomes `CONTRIBUTING.md` and the old package goes.

This package is written to one convention, so that anybody who knows it knows where every line
lives before opening the tree, and what a file holds from its name. The convention is held by
`tests/conventions/`: a file in the wrong place, a layer that imports upwards, a route that holds a
rule or a name nobody outside uses fails the suite, not a review. A rule with no test is not on
this page.

The ideas are Rails' and SOLID's. From Rails: convention over configuration, the name is the
contract, a thin controller over a domain that holds the rules, and what is written three times
lives once. From SOLID: a module has one reason to change; a new kind is added, never edited in;
an implementation keeps what its interface promises; an interface is small and declared by who uses
it; a domain depends on what it declares, never on what is above it. Three things of Rails are
left out on purpose: rules inside the ORM model (async SQLAlchemy has neither sane lazy loading
nor callbacks), ambient current-user state, and autoload.

## The layout

```
src/runtime/
  app.py api.py worker.py runner.py cli/   the entrypoints: they build and wire, nothing else
  config.py enums.py exceptions.py         one process's words: its settings, the shared enums, the errors
  actor.py auth.py scoping.py              who a request is, how its key is resolved and required, the org it is scoped to
  postgres.py signal.py redis.py livekit.py one process's connections
  shared_state.py handles.py               what the gateways hold in common, and one process's handles with their getters
  kit/            the toolkit: generic code, no business noun, imports nothing above itself
  wire/           every shape that crosses a process: the SDKs' protocol, and what the gateway,
                  its workers, its runner and the other gateways tell each other; golden-pinned
  <domain>/       a bounded context, always the same files (below)
  migrations/     Alembic, shipped in the wheel; an applied revision is never edited
tests/            mirrors src/ one to one; tests/conventions/ holds this page
```

## A domain's files

Every domain folder holds these and nothing else. A file that would be empty is left out.

| file | holds | imports (of ours) |
|---|---|---|
| `models.py` | the domain's tables, one class each, named like the table, singular; what each table is for retention (`Kept`, `Sealed`) | `kit.db`, `enums` |
| `schemas.py` | the pydantic bodies its endpoints read and answer | `kit.schemas`, `enums`, `wire` |
| `repository.py` | every statement on the domain's tables; returns models, or a typed row for a read model | its `models` and lower domains', `kit.repository`, `scoping` |
| `service.py` | the rules and the use cases, as functions that take and return values; the domain's errors; the `Protocol`s of what it needs from above | `repository`, `models`, `exceptions`, `kit`, `wire`, lower domains' `service` |
| `auth.py` | the domain's dependencies: the scopes that open its endpoints, its loaders (a resource loaded and authorised, or the refusal), and the getters of the objects its endpoints are handed | the root `auth`, `handles`, its `service`, and the types its loaders return (its `models`, a typed row of its `repository`) |
| `endpoints.py` | the router: dependencies → one service call → schema | `auth`, `schemas`, `service` |
| `tasks.py` | the loops the domain owns, each one pass declared with `@kit.loops.loop` | `service` |

A file that outgrows one module becomes a package of the same name, one module per noun
(`calls/service/inbox.py`, `telephony/endpoints/carriers.py`); its `__init__.py` names exactly
what other domains import. An object that lives for hours and holds state (a log, a socket
registry, a session) is not a use case: it is a module of the domain beside the canon's files, and
the domain's page in this file's "engines" list names them.

## How a domain is cut

A **domain** is one context: its own tables, its own endpoints, its own tasks, consumed by others
through its service. A **package inside a domain** is a sub-context that cannot exist without its
parent and shares its tables (`calls/log/`, `cli/setup/`). A **module** in a layer package is one
noun. The test of a cut: a group of modules that imports nothing of the rest of its domain and has
consumers of its own is another domain. A `service/` package over sixteen modules fails until this
page carries a sentence saying why it is one context.

The domains, bottom up; a domain imports the `service` of a domain below it, as a module, never a
name out of it, and never upwards:

```
platform · billing · mail · accounts · signin · compliance · providers · agents · knowledge
· whatsapp · fleet · telephony · session · judging · alerts · calls · insights · live · flows
· evals · hosting · studio · retention · jobs · hosts
```

A domain reads the `models` of a domain below it as it reads its own. What a lower domain needs of
a higher one is handed to it: a `Protocol` the lower domain declares, implemented above and passed
in by the entrypoint. Endpoints are the top of every domain and may call any domain's service;
nothing imports an `endpoints` module but `api.py`. `jobs` is the worker's side and `hosts` the
runner's: nothing in the gateway imports them.

## Beside the canon's files

A module of a domain that is none of its seven files is named here, and in
`tests/runtime/conventions/canon.py`, with what it is. Nothing else may sit beside them.

| domain | module | what it is |
|---|---|---|
| `providers` | `stage.py` | a value object: a stage of a call as values, what an agent asks for (`Model`, `Voice`) and the stage resolved (`Running`, `Pipeline`). Services of six domains speak in it |
| `providers` | `catalog.py` | a value object: the providers row, the one shape of a document the box keeps and the one reader of its keys. It is pydantic, the document being JSON an operator edits |
| `agents` | `declaration.py` | a value object: what an agent's class declares (its tools, its turns, its words), and the declaration whole |
| `agents` | `settings.py` | a value object: what the org sets on an agent over its class (its settings, its lexicon), and the versions a call ran on |
| `session` | `call.py` | `Call`: the state that outlives a turn, and the Protocols of what it reaches (the context, the platform) |
| `session` | `writing.py` | `Writing`: the call's entries in order, sent to its log in batches by one task |
| `session` | `session.py` | `Session`: the call on livekit's AgentSession, built on its place: opened, heard, re-staged, ended |
| `session` | `commands.py` | the one table of what each command does to a call, the envelope a stream is read with, the refusal |
| `session` | `line.py` | `Line`: who has the line, and the agent's ears and voice with it |
| `session` | `hold.py` | `HoldMusic`: the melody, its grace, when it sounded |
| `session` | `agent.py` | `CallAgent`: livekit's Agent with the hooks of a turn |
| `session` | `prompt.py` | the prompt's blocks, the request of each turn, the greeting, a supervisor's notes |
| `session` | `history.py` | the history: how it opens, how it is rebuilt from a log, a note added to it |
| `session` | `tools.py` | `Toolbox`: the app's tools, the lookups, a voicemail reached, `end_call` |
| `session` | `lookups.py` | `Lookups`: recall and search before each turn, within a budget |
| `session` | `hearing.py` | what the ears are told: the turn policy, agreement, the agent heard back, the keyterms |
| `session` | `repeats.py` | what the agent said since the caller last spoke |
| `session` | `transcript.py` | the agent's words as they play: the entry, the lexicon read back |
| `session` | `listener.py` | `Listener`: what livekit says, written as entries; the turn's times |
| `session` | `metrics.py` | livekit's metrics and usage as the wire's |
| `session` | `stages.py` | the stages a call runs: what was built, whether it is spoken, a vendor lost or back |
| `session` | `voice.py` | a session built for a spoken call |
| `session` | `text.py` | a session built for a written call |
| `session` | `room.py` | `CallRoom`: who is in the room, the caller's codes, transfers, the room verbs |
| `session` | `widget.py` | `Widget`: the DataChannel to a browser widget |
| `session` | `recording.py` | `Recorder`: the call's file and the other voices |
| `session` | `echo.py` | the caller's audio cleared of the agent's own voice |
| `session` | `clock.py` | a call's time: its ceiling, a chat's quiet, the idle lines |
| `session` | `started.py` | the `call.started` entry |

`providers/service/` has more than sixteen modules and is one context: which vendor runs each
stage of a call, on whose key, told what, at what price. One row, one table of keys and one
registry of plugins, read by twenty of its modules; where an org's traces go (`telemetry`) and what
this machine can run (`machine`) stand apart and were decided into it.
| `judging` | `library/` | the judges and personas the box ships: pages a person can read, read by `service/library.py` and by no other module |

`session` is an engine: one call running for as long as it lasts. Each of its modules above is an
object that holds the call's state, or the one noun those objects share; `service.py` beside them
is what a host (the gateway for a written call, a worker's job for a spoken one) calls.

`telephony/service/` has more than sixteen modules and is one context: how a number reaches an
agent and an agent a number. The account a number lives in (by its kind: a module each, behind
one `Protocol`), its fence, its trunk and rule on the SFU and its row are read and written
together; the routes and the legs in a call's room were decided into it.

## The rules

1. **One noun, one file.** A module's one-line docstring names one thing, and the filename is
   that thing. *Held by:* the docstring test; the names test.
2. **Layers.** `endpoints` never imports `repository`, `models` or SQLAlchemy; `repository` never
   imports `service` or FastAPI; `service` never imports FastAPI; `models` imports `kit.db` and
   `enums` alone. Across domains, the order above. *Held by:* the import walk, cycles included.
3. **An endpoint is transport.** Its body is its dependencies, one call to a service, and a schema
   validated from what the call returned. A verb that is not CRUD is a resource of its own. A
   WebSocket or SSE route holds its framing and nothing else. *Held by:* a route body of more than
   fifteen statement lines fails.
4. **A use case receives what it uses, by name.** No function takes a bag of collaborators. The
   lifespan yields one typed state; each object on it has one getter, declared in the owning
   domain's `auth.py` (for an object a lower domain is handed from above, the `auth.py` of the
   domain that declares its `Protocol`); a resource reaches an endpoint loaded and authorised by a dependency. A
   session is asked for in the signature by its kind: `Session` (the request's org) or
   `BoxSession` (every org). *Held by:* `.state` appears only in getters; `box_wide` never in an
   `endpoints` module.
5. **A service speaks in values.** It takes and returns models and dataclasses; the endpoint does
   `Schema.model_validate(value)`. One concept has one shape per layer. pydantic lives in `wire/`
   and `schemas.py`; the one exception is the shapes a vendor's client parses that vendor's
   answers with, which stay beside the client. *Held by:* a `service` module importing its domain's
   `schemas`, or the reverse, fails.
6. **Who knows what it is, answers.** Three or more kinds asked about from several modules: one
   module per kind implementing a `Protocol` the domain declares, one registry keyed by the enum,
   the differences as attributes or methods of the kind. Kinds that differ only in data: one table
   of attributes. A kind branched on in one module, or two kinds: one `match` in one function.
   Never a bool or a string compared at each consumer. *Held by:* a comparison against a member of
   a registered enum outside its registry module fails; every `Protocol` has one conformance test
   that each implementation runs.
7. **One state, one owner.** The fields that make a state live in one object, and only its methods
   change them. *Held by:* that object's tests, which prove every transition and every forbidden
   one.
8. **`kit/` is generic.** No business noun; of ours it imports `kit`, `enums` and `exceptions`
   alone, and a web framework only in its four modules about HTTP (`middleware`, `sse`,
   `websockets`, `http`). What is written a third time moves there. *Held by:* the import walk.
9. **Every loop has an owner.** A loop is one pass, a function in its domain's `tasks.py` under
   `@kit.loops.loop(name, every_s=…)`. The entrypoint binds what the pass needs, by name, and
   starts it on the process's `Loops`, which survives a failed pass, backs off, and keeps each
   loop's heartbeat. *Held by:* `while True` in a
   `service` module fails unless the function is a bounded wait inside a request and says so in
   its name (`wait_for_…`); a loop that died shows on `/metrics`.
10. **A facade is a contract.** A `service/__init__.py` exports what another domain imports and
    nothing else; a domain's own endpoints import the noun's module. *Held by:* an exported name no
    other domain imports fails.
11. **SQL at home.** Statements appear only in `repository` modules. *Held by:* the AST walk.
12. **One table, one model, one owner**, and every model declares what retention does with it.
    *Held by:* each `__tablename__` once; a model with an `org` column and no `Kept` fails.
13. **Errors.** Every error subclasses `PinecallError` and carries a `status`; a domain declares
    its own in its service; endpoints never raise `HTTPException`; `app.py` has the one handler. A
    vendor's failure is an `UpstreamError` carrying `vendor`, `retryable` and `retry_after_s`,
    translated once where the vendor is called.
14. **Entrypoints wire.** Only `app.py`, `api.py`, `worker.py`, `runner.py` and `cli/` build
    objects from settings. A CLI verb is a typed function that calls a service and prints; a module
    is named for the word typed.
15. **Size.** A module is at most 500 lines; a module of shapes alone at most 800; a line at most
    120 characters, written by `ruff format`.
16. **Tests mirror the tree** one to one, on a real Postgres and Redis, with LiveKit and the
    vendors faked.
17. **Comments say why.** A docstring is one line and says what. A comment is written only for a
    fact, a trap or a reason, and names its source.

## The names

Modules are nouns, classes are singular nouns, functions are `verb_object`. The verbs:

| verb | means |
|---|---|
| `get_x` | one thing by its id; refuses when there is none |
| `find_x` | one thing, or `None` |
| `list_x` | several, in a stated order |
| `x_of(owner)` | the one thing its owner has: `policy_of(org)` |
| `create_x` · `update_x` · `delete_x` | the three writes |
| `put_x` | replace whole, creating if absent |
| a domain verb | what the business calls it: `seal`, `dial`, `invite`, `admit` |

A past participle is never a function's name (`kept`, `listed`, `planned`); a name that is a
sentence is a comment. One word per concept, everywhere: code, schemas, pages, logs.

| say | never | means |
|---|---|---|
| endpoint | door | one route of the API |
| env | world | one of an org's two environments |
| scope | corner | an org, an env and the holder a request acts as |
| actor | bearer, acting | the verified key and person behind a request |
| settings | tuning, config, knobs | what an org sets on an agent from the console |
| declaration | declared, declarations | what an agent's class declares |
| stage | (as anything else) | one of a call's three: hearing, thinking, speaking |
| transcript | case (as a reading) | a finished call as a judge reads it |
| case | — | one row of the dataset of calls to learn from |
| seat | (as a worker's slot or a line's place) | a member's place in an org |
| subscriber | reader (as a live follower) | who follows a log as it is written |
| email | letter | a message the box sends |
| phone_leg | leg | one side of a call on the phone network |
| fence · entry · seal · dispatch · offer · lane | — | kept: the engine's and telephony's own terms |

## The database and the wire

The runtime runs on the database the previous runtime left: `models` mirror the live tables column
for column. A change to a table is a new Alembic revision generated from the model, additive
whenever the old runtime must still run against it. The wire's shapes are pinned to the SDKs'
goldens and do not change with a refactor.

## Commands

```
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
~/pinecall-v2/tools/remote-test [pytest args]     every suite runs on the test box, never here
```
