# Events and flows

What an app does around its calls, kept by the gateway so it outlives the app's process: an
**event** sent to the app is owed to it until its process says it was heard, and a **flow** is a
function of the app whose **run** the gateway keeps as a journal of steps, with the clock, the
event or the call that wakes it. The function itself runs in the app's process: the gateway never
runs a tenant's code. `{app}` is the app's name, a slug the app chose; every row is the org's and
the environment's of the key.

## An event

`POST /v1/apps/{app}/events` (`app`) takes `{name, data}` and answers `202 {id}`. The event is
kept until the app's process hears it, and it wakes every run of the app waiting for an event of
that name whose `match` it carries (below). `data` is an object of 16384 bytes of JSON at most: an
id and a few facts, never a document.

`POST /v1/apps/{app}/events/{id}/heard` (`app`) says the process handled it; `204`, and `404` for
an event that is not owed to that app.

## The work an app is owed

`POST /v1/apps/{app}/work` (`app`) takes `{wait_s}` (0 to 25, 0 when left out) and answers
`{events, runs}`: the events the app has not heard, and the runs that are `ready` to go on, each
with its journal. It answers as soon as there is either, or with both empty once `wait_s` passed.
What it hands out is held for the asker for 60 seconds: another process of the same app is not
handed the same event or run meanwhile, and a process that died gives them back when the hold ends.
At most 50 of each per answer.

## A run

| | |
|---|---|
| `POST /v1/apps/{app}/runs` (`app`) | `{flow, key, input}` starts a run; the same `flow` and `key` answer the run already started, so a start sent twice starts once. `201` with the run |
| `GET /v1/apps/{app}/runs[?flow=&status=]` (`app` · `calls`) | the app's runs, newest first, 200 at most, without their journals |
| `GET /v1/apps/{app}/runs/{run}` (`app` · `calls`) | one run with its journal |
| `POST /v1/apps/{app}/runs/{run}/steps` (`app`) | the run's next step (below) |
| `POST /v1/apps/{app}/runs/{run}/end` (`app`) | `{status: "done" \| "failed", error?}`: the function returned, or threw |
| `POST /v1/apps/{app}/runs/{run}/cancel` (`app`) | stop the run where it stands; one that is over stays as it ended |

A run reads `{id, flow, input, status, wake_at, waits_for, call, error, started_at, moved_at, steps}`.
Its `status`:

| status | it means |
|---|---|
| `ready` | its function may go on: it is handed out as work |
| `sleeping` | it waits for `wake_at` |
| `waiting` | it waits for an event named `waits_for`, until `wake_at` when it has one |
| `calling` | it waits for the call it placed, `call`, to end |
| `done` · `failed` · `cancelled` | it is over; `failed` has what was thrown in `error` |

## A step

A step is `{seq, kind, asked, result}`. `seq` counts from 1 and the journal is written in order:
the step after the last one, or `409`. A step sent again with a `seq` already written answers the
run as it is and writes nothing, so a retry is safe; one sent again as another `kind` is `409`,
since the function changed under its run. Only a `ready` run takes a new step.

| kind | `asked` | what the gateway does |
|---|---|---|
| `run` | — | keeps `result`, what the process's own code returned, so it is read back and never run twice |
| `emit` | `{name, data}` | sends the event to the app, as `POST …/events` does |
| `sleep` | `{until}` | the run is `sleeping` until that time, ISO 8601 with its zone |
| `wait` | `{event, match?, until?}` | the run is `waiting` for an event of that name whose data has every key of `match` with the same value; at `until` it gives up, and the step's result is `null` |
| `call` | `{agent, to, from?, state?, metadata?, greeting?, instruction?}` | places the call as `POST /v1/agents/{agent}/dial` does, after the same guards ([numbers.md](numbers.md)); the run is `calling` until the call ends |

Each step reads back as `{seq, kind, asked, over, result}`. A `sleep` ends with `null`, a `wait`
with the event's data, a `call` with `{answered, reason, call}`: `reason` is the call's end reason,
and `answered` is false for `no_answer`, `busy` and `dial_failed`. A dial the guards refused, or an
agent nobody is holding, is the step's result and no error: `{answered: false, refused, message}`,
written at once with the run still `ready`, so the function reads which guard and goes on. The
call's metadata carries `flow_run`, the run that placed it. Cancelling a run does not end a call it
placed.

## The limits

- An org has 10000 runs sleeping, waiting or calling at most; the next step that would park one is `409`.
- A run sleeps or waits 90 days at most.
- An event's `data`, a run's `input` and a step's `asked` are 16384 bytes of JSON each at most.
- A step's `seq` goes up to 10000.
