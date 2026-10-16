# Evals — goldens run through the app, a call checked again, the simulated caller

An agent is tested in rings. A **golden** is a scripted conversation: the state it opens in, its
turns (the caller's lines and the facts the app's backend injects, each line with what must follow
it), and what holds at the end. A **run** plays every
golden under every model named, as written calls through the app socket that holds the agent,
and **judges** each call into a matrix of models by goldens. A **persona** is a caller a model
plays, one improvised line at a time, written or out loud. Every call that hangs up is judged
once more by the panel of hang-up judges, and its verdicts are the last entry of its log.

Every endpoint below takes a key with the `evals` scope and acts in the key's org and environment.

## A suite — `POST /v1/evals/run`

```
$ pinecall test --model anthropic/claude-haiku-5-5
POST /v1/evals/run
{"agent": "recepcion",
 "goldens": [{"name": "reserva", "state": {"stage": "book"},
              "memory": ["prefiere la mañana"], "today": "2026-09-08",
              "turns": [{"say": "quiero el jueves",
                         "then": [{"tool": "find_slots", "args": {"day": "jueves"}},
                                  {"reply": {"says_any": ["10:15"],
                                             "intent": "offers a Thursday slot"}}]},
                        {"event": {"name": "slot_freed", "data": {"at": "10:15"}}},
                        {"say": "sí, esa", "then": [{"tool": "book"}, {"nothing_else": true}]}],
              "expect": {"not": ["gratis"], "register": "usted"}}],
 "models": [{"provider": "anthropic", "model": "claude-haiku-5-5"}],
 "app": null, "voice": false}
```

The run drives the app that holds the agent in the key's scope (`app` names one, as
`WS /v1/chat?app=` does); nobody holding it is `404`. Each golden is one written call on the same
session a real caller gets, tuned where the app holds the agent, on the org's keys:

- it opens with no greeting: a golden starts in the middle of a conversation;
- its `state` rides the call's `call.started` (its `state` field), and the app opens the call in
  it before the first render, as `WS /v1/chat?state=` does; the run declares no state of its own;
- the turns play in order, forty at most: a `say` turn is the caller's line, run as livekit's own
  test run (`AgentSession.run`); an `event` turn is the app's `call.event`, so an event the agent
  never declared is refused by name (`400`) and the call ends. An `event` turn takes no `then`:
  what the agent does with the fact is judged in the next line's turn;
- `memory` answers `recall` for this call alone; `search` is the real index;
- `today` is the day the model is told it is; absent, the real one;
- after an event the run waits for the log to go quiet: the app reacting is the only signal.

**A turn's `then`** is asserted, in order, on that line's run, with livekit's own assertions where
it has one:

| step | holds when | by |
|---|---|---|
| `{"tool", "args"?, "within_ms"?}` | the turn's next tool call is this one, with these arguments among its own | livekit's `next_event(type="function_call")` |
| `{"no_tool"}` | no call of this tool in the turn | livekit's `contains_function_call` |
| `{"reply": {"says"?, "says_any"?, "not"?, "intent"?, "within_ms"?}}` | the turn's next message says these phrases (by code, case-blind), and `intent` holds of it | livekit's `next_event(type="message")`, its `judge(llm, intent=)` on the run's judge model |
| `{"end": "agent"}` | the call ended in this turn, by this side | the session |
| `{"nothing_else": true}` | nothing follows the step before it in the turn | livekit's `no_more_events` |

The first step that breaks ends the golden there: no later turn is played, and `expect` is not
asked, since the conversation it describes never happened. Each step is a metric of the turn's
number (`t1.tool:find_slots`, `t1.reply`, `t1.intent`, `t2.no_tool:book`, `t3.nothing_else`, `t4.end`; a
second of the same name in a turn is `#2`); an `intent` is one judge call.

**`expect`** holds over the whole conversation, once every turn held: `tools` and `not_tools`
(code), `says`, `says_any` and `not` (code, reported as `says`, `says_any` and `silence`),
`register` (code), `grounded` and `judges` (the judge model).

Each entry of `models` is a column; none is the agent's own, named `declared`. **The answer is the
run as it starts**, stored and `running`, with `calls` and `matrix` empty: the gateway plays it
after answering, so no request is held for the minutes a suite takes. Follow it at
`GET /v1/evals/runs/{id}` — its row is rewritten before each call opens and after each is judged —
on each `run.changed` of the org's feed (`GET /v1/events`), which names the run and its agent. Done,
the row reads:

```json
{"id": "run_3f0c…", "agent": "recepcion", "started_at": 1790000000.1, "finished_at": 1790000031.4,
 "status": "done",
 "calls": [{"golden": "reserva", "model": "anthropic/claude-haiku-5-5", "call": "call_…"}],
 "matrix": {"models": ["anthropic/claude-haiku-5-5"], "goldens": ["reserva"],
            "metrics": ["t1.tool:find_slots", "t1.reply", "t1.intent", "t3.tool:book",
                        "t3.nothing_else", "silence", "register"], "judge_calls": 1,
            "runs": [{"model": "…", "golden": "reserva", "summary": {…},
                      "scores": [{"metric": "t1.tool:find_slots", "score": 1.0, "passed": true,
                                  "reason": "…", "criteria": "…", "judge_calls": 0}]}],
            "failures": []},
 "error": null}
```

A cell carries its call's own `call.summary`, never a number of its own; a cell where a judge did
not hold carries `asked`, every request the model was sent, to reproduce it. A golden that gives
`memory` on an agent whose policy keeps none is a cell that broke on the metric `memory`, with no
call opened for it: its facts had nowhere to go, and the rest of the run plays.

`status: "failed"` is the run stopping early, and `error` says why: the app let go of the agent
(`the app detached after 1 of 3 goldens`), the org ran out of a quota (and `credits.exhausted` is
on the agent's log), the fifteen-minute deadline passed, or the gateway playing it stopped. The
cells judged so far stay. A failing golden is a score, never a status.

One run per agent at a time: a second is `409` naming the run in flight.

`voice: true` says each golden out loud through the environment's fleet: the room is dispatched, the
caller's lines are spoken (under `interferer_db` of the `ambience` named — a television unless
said — and `packet_loss`, when set), the room is deleted, and the call is judged once its worker sealed it. The worker builds the
session from the declaration, so a spoken run refuses `models` and a golden that pins `today`; it
has no test run to assert steps on, so it refuses a golden with an `event` turn or a `then`, and
judges the final `expect` alone.
The golden's `state` rides the dispatch, and the worker writes it on the call's `call.started`.

`GET /v1/evals/runs?agent=&since=&limit=` lists the runs of the key's org in its environment, newest
first; `GET /v1/evals/runs/{id}` is one of them, and another org's is `404`.

A run may also name the org's **cases** (below): `cases: ["jueves-tarde"]` plays those by name,
whatever their status, so a case still waiting for a person can be reproduced, and `dataset: true`
plays every case of the agent a person approved, that is not held out and not kept in the
repository, which is what a nightly run asks for; a case held out is played only when a run names
it, which is what a release asks for. `version: 4` builds every call of the run on that version of
the agent's settings in the scope of the app that holds it, instead of the one standing (a
candidate, a canary's: see [settings-api.md](settings-api.md)); a version the scope never had is
`404`. Beside `models`, it is how a run compares a candidate with what runs now. A run of cases is
refused in production (`403`): a case is a real caller's words, and it is played only in the
sandbox, as written calls through the app a developer holds there, never through production's
app, whose tools act for real, and never out loud or on a phone.

## The dataset — `POST` · `GET /v1/evals/cases`, `PATCH` · `DELETE /v1/evals/cases/{id}`, `GET /v1/calls/{call}/golden`

Real calls are the dataset, and the loop that keeps it is: a call a judge broke on is kept at
hang-up as a **pending** case; a person reads it, reproduces it (`cases: [name]` on a run),
fixes the agent, and approves it into the nightly or dismisses it. A case is a golden made of the
call: its turns (each caller line a `say`, each fact the app injected an `event`, in the order the
log has them), the state it opened in (the first `state.changed` before the caller spoke), the
facts `recall` gave it (as the golden's `memory`), and the day it ran. No turn carries a `then`: a
person writes what the agent should have done.

**Born at hang-up.** After the panel (below), a call whose score did not pass is kept as a case
`pending`, by `the hang-up panel`, named after the first judge that broke, the caller's first
four words and the call's last six characters (`promises-me-llaman-manana-por-29d7c7`). Its
`expect` is what the broken verdicts say must not happen again, and never what was right:

| broke | the case's `expect` |
|---|---|
| `consent` | `not_tools`: the tool that ran unasked, by the seqs the verdict cites |
| `grounded` | `grounded: true` |
| any other judge of the library, the org's own, the agent's own | `judges: [name]`, asked again of the replay |
| `expected-outcome` | nothing: its expectations are a simulated caller's, and a case plays written lines |

A call a simulated caller made is kept too, `source: "simulation"` with the `persona` that played
it; one whose caller said nothing, or a call already kept, is not. At most **50** cases wait per
agent: past it a broken call is judged as ever and not kept, until a person decides some. A write
that breaks is logged and the call seals all the same.

**Grouped — `GET /v1/evals/groups[?agent=]`, `GET` · `PATCH /v1/evals/groups/{id}`.** A case kept at
hang-up joins its agent's open group for the first judge that broke (`group` on the case): fifty
calls one judge broke on are one thing to read. A group is `{id, agent, judge, cause, status,
since, cases, simulations, proposal?, proposed_at?}`; its `cause` is the first reason until a
diagnosis writes one. `PATCH {status: approved | dismissed, judge_was_wrong?, note?}` decides the
group and every case still waiting in it; `judge_was_wrong` with `dismissed` writes a calibration
label on each of its calls. A closed group is never reopened: the next broken call opens another.

**Diagnosed — `POST /v1/evals/groups/{id}/propose`.** One request to the judge model reads the
group's judge and question, up to five of its newest calls with the reason and the lines each
verdict cites, the prompt the newest ran on, the agent's settings and tools, and answers a
`proposal`: `{cause, kind: setting | code | knowledge | none, where, change, confidence}`. It is one
eval, none on the org's own key (`evals.spent`, `kind: "propose"`). A `setting` proposal is applied
with `POST …/apply` (a key that opens `pipeline` or `words`): `change` becomes the setting named by
`where` in a new version of the key's corner, noted `case <id>`, checked as any set is; the person
replays it with `pinecall test --case` and pushes it on. A `code` proposal names the tool or the
prompt block and what it must do; it is the developer's assistant's to make (`pinecall mcp`, the
`cases` tool), never applied here (`409`). `POST …/persona` writes a persona like the group's
newest call's caller and keeps it as the agent's own, tagged `from-case` (one eval).

**Kept by hand.**

```
POST /v1/evals/cases
{"call": "call_…", "name": "jueves-tarde", "expect": {"says_any": ["jueves"]}, "held_out": false}

{"id": "case_3f0c…", "agent": "recepcion", "name": "jueves-tarde",
 "golden": {"name": "jueves-tarde", "state": {"stage": "book"},
            "turns": [{"say": "Quiero cita el jueves"}],
            "today": "2026-09-29", "expect": {"says_any": ["jueves"]}, "promoted_from": "call_…"},
 "source_call": "call_…", "source_env": "production", "held_out": false,
 "author": "m_ana", "created_at": 1790000000.1, "status": "approved", "broke": [],
 "source_version": 4, "kept_in_repo": false}
```

A case kept by hand is `approved`. An `expect` left out is the one the call's broken verdicts
give, as at hang-up. The key must read the call, as a replay's does: a production call is kept
with a key of production. The case is the org's, in both environments, and played in the sandbox.
A call still going is `409`, one whose caller said nothing is `409`, and a name the agent has
already is `409`.

**Read as a golden, kept nowhere.** `GET /v1/calls/{call}/golden?name=&from_seq=` answers the
golden the call makes, with the same derived `expect`; `from_seq` opens it in the state the call
was in at that seq and plays only the lines after it: what `pinecall runs promote` writes to the project's
`test/candidates/` for a case that names the code (a stage, a tool, an event) and belongs in the
repository.

**The inbox.** `GET /v1/evals/cases?agent=&status=` lists the org's cases, the pending first,
newest first, and says how many wait: `{cases, pending, pending_at_most}`. `PATCH
/v1/evals/cases/{id}` writes what a person decided, each field set:

| field | does |
|---|---|
| `status` | `approved` (the nightly plays it), `dismissed`, or `pending` again; the person and the time are kept |
| `held_out` | played only when a run names it |
| `kept_in_repo` | written into the repository as a golden: the nightly leaves it to the file |
| `judge_was_wrong` + `note` | with `dismissed` only: the judge that broke should have held, kept as a calibration label of the call (below), in the call's own world, so the key must read the call; a judge the case did not break on is `400`, and so is a `note` without a judge |

`DELETE` forgets one, and another org's, or one nobody kept, is `404`.

A case is tenant data like the call it came from, and never outlives it: erasing the call, the
contact who made it, or the org erases the case in the same transaction (`retention/service/erasure.py`),
and so does the nightly retention run, which erases through the same path. The calls a run
plays a case in are calls of the sandbox like any other, under the org's retention there.

## The judge judged — `POST /v1/evals/calibration`, `GET /v1/evals/calibration?agent=`

A person who knows says what a judge should have answered on a finished call:
`POST /v1/evals/calibration {call, judge, held, note?}` keeps it (a second label of the same
call and judge replaces the first), in the call's environment, by the key's person. `GET` answers each
judge against those labels, beside the verdict the seal counted for it on the same call:
`{judges: [{judge, labelled, compared, agreed, rate, trusted}], labels_to_judge, agrees_at_least}`.
A judge is judged once 10 labels have its verdict beside them, and `trusted` is false while it
agrees with fewer than 80 % of them: it is reported, never dropped silently, and until 10 it is
null. Erasing the call takes its labels.

## The judges

Every judge is one question a model answers about a finished call (below, *Judges*). Once every
turn of a golden held, its final `expect` is held to them and to checks settled by code:

| check | when | settled by |
|---|---|---|
| `tools` · `not_tools` | `expect.tools`, `expect.not_tools` | code, the second naming the seq of the call that ran |
| `silence` · `says` | `expect.not`, `expect.says` | code, case-blind; the turn is named |
| `says_any` | `expect.says_any` | code, case-blind: any one of the phrases is enough, for an expectation with several right answers (`de 9 a 14`, `de nueve a dos`); the reason names the one said, or every one when none was |
| `register` | `expect.register` | code: no word of the other register (`tú`, `usted`) |
| `grounded` | `expect.grounded` | the library's judge, asked of the golden's call |
| any judge, by name | `expect.judges` | the library's, the org's own or the agent's own judge asked of the golden's call, whether or not the org switched it on; a name nobody wrote breaks the golden |

## A finished call

`POST /v1/evals/replay/{call}` `{banned?, budget?}` runs six checks by code alone: consent,
the banned words, the errors the session did not recover from, each latency's **worst turn**
against the budget (seconds, under livekit's names; the default is 2 s end to end, 1 s to the
model's first token, 0.6 s to the voice's first byte), how much of the talking the agent did,
and how it took being interrupted.
A call nobody wrote and another org's are the same `404`.

`e2e_latency` is the caller's wait to the agent's first sound, one value per reply, a preamble
before a tool counted as the reply ([metrics.md](../wire/metrics.md)). Two of the budget's keys are
the runtime's own measures. `talk_share` is the agent's part of the time anybody spoke on the call,
0 to 1, and is judged by the `talk` check, which is `skipped` when the budget names none.
`interruption_delay` is how long a barge-in took to be obeyed: from the caller starting to speak
over the agent to the agent leaving `speaking`, one value per reply written as interrupted, read
off `user.state` and `agent.state`. Neither has a default: a budget that leaves them out does not
judge them.

`interruptions` reads every reply of the agent's written as interrupted: the caller's words that
cut it off must be followed by a reply of the agent's, and that reply must not start over the one
cut off (its first four words the same as the cut reply's). A reply the agent went on with before
the caller said anything (a cough, a false start: livekit resumes it) and a caller who hung up
after cutting in are not judged; a call where nothing was cut off, or nothing cut off wanted an
answer, is `skipped`. The detail names the seqs of the cut reply, the caller's words and the reply.

```json
{"call": "call_…", "agent": "recepcion", "passed": true,
 "verdicts": [{"check": "consent", "status": "deferred", "detail": "…"}, …]}
```

`POST /v1/evals/judge/{call}` runs the hang-up panel on a finished call now and writes its
`call.score` on the sealed log: a call whose org judged nothing then, or whose judge failed. A
call judged already is `409` unless `?again=true`; a call still going is `409`. The agent's own
judges are the ones written when the endpoint runs, not when the call ended.

## At hang-up

The seal judges every call when three things hold: the org judges its calls (`PUT /v1/org/judging`),
the platform's providers row names a `judge` model, and that judge's `ceiling_usd` is above zero.
The panel is the library's judges switched on for the agent, then the org's own, then the
agent's own, each asked once.

**The judge model** is the agent's `judge` (its class's, else its settings'), else the org's
(`PUT /v1/org/judging {on, model}`, the model tried on the org's keys in both environments before it is kept; the agent's, in the environment its settings are for), else
the providers row's on the platform's key. A model the org names runs on its own key for the
vendor when it has one — a local model's server among them, through `options`
`{"base_url": …}` — and then its answers are never billed (`call.score.own_key`) and no
ceiling of the platform's applies; on a key the platform lends, or on the platform's own judge,
the org pays for its answers in **evals** (below), and the providers row's `ceiling_usd` is what
one call may spend: a judge reached past it is `skipped`, saying so, as is one whose model failed,
and the call seals all the same. The judge is asked for a forced tool call, so a local model must
call tools. `judge_calls` counts the model's requests (a trigger's yes-or-no among them),
`judge_cost_usd` prices them at the row's rates, and `evals` counts the judges that answered. An
org that judges nothing gets `not_judged` saying so; a call an eval run opened is judged by the
run. Each `held` and `broken` is counted into the day's drift, by the version of the agent's
settings the call ran and the hash of the judge's question, which `GET /v1/insights/drift` reads
to say which judge's pass rate moved ([console-api.md](console-api.md)); `na` and a classification
are not. A call that did not pass is kept as a pending case (the dataset, above).

## Judges — `GET` · `PUT` · `DELETE /v1/org/judges[/{name}]`, `/v1/agents/{slug}/judges[/{name}]`

A judge is a name, a question, how it answers, when it runs and what it reads. It answers
`verdict` (`held` or `broken`), `choice` (one of two or more `choices`, written `classified`
with the `choice`) or `score` (1 to 5, `classified` with the `score`); any of them may answer
`na`, the question did not apply. Only a verdict judge sets `passed`. It runs `always`, only on a
call a simulated caller played (`simulations`), or on a `trigger`: a short yes-or-no asked first,
and a no is `na` without the question. It always reads the whole call, both sides' turns and the
tool calls between them, each line under its log position, and cites the positions it rests on —
first the positions, then the reason, and the answer last, decided by that reason, since a model
fills the fields in that order and one that decided first argued its way to the other answer.
It answers its own question alone: what else the conversation got wrong is another judge's, never
decides its answer and has no place in its reason, and a call that gives its question nothing to
judge is `na`. `reads` adds `prompt` (the agent's prompt as the call ran it), `evidence` (the day the call
began, the text it carried, the tool answers, the states) and `facts` (the org, the direction, the irreversible tools
and the confirmations, an opt-out, the disclosure sentence, how it ended, what a simulated caller
expected).

**The library** is Pinecall's, the same for every org, each judge's question in the runtime's
`evals/library/judges/` under a version: `consent`, `grounded`, `promises`, `disclosed`,
`identified`, `honoured-stop`, `ended-well`, `expected-outcome`, `relevance`, `repetition` and
`sentiment`, every one off until the org or the agent switches it on. Each row of the library
says in `why` what the judge saves an org from, and `recommended` whether Pinecall says to switch
it on first: every one but `relevance`, `repetition` and `sentiment`, which grade a call rather
than guard it. Some settle as `na` by a fact before any model is asked:
`consent` and `promises` when no irreversible tool ran, `identified` on a call that came in,
`expected-outcome` when the simulated caller expected nothing; an `na` is never an eval.

```
$ pinecall judges add offers-next-slot --asks 'The agent offered the next free slot.'
PUT /v1/agents/recepcion/judges/offers-next-slot
{"question": "The agent offered the next free slot.", "when": "always", "reads": ["prompt"]}

{"judges": [{"name": "consent", "owner": "pinecall", "on": false, "question": "…", "answer": "verdict",
             "choices": [], "when": "always", "trigger": "", "reads": ["facts"],
             "summary": "…", "version": 1, "why": "…", "recommended": true}, …,
            {"name": "offers-next-slot", "owner": "recepcion", "on": true, "question": "…",
             "answer": "verdict", "choices": [], "when": "always", "trigger": "",
             "reads": ["prompt"], "author": "m_ana", "set_at": 1790000000.1}]}
```

A list is the library first, then the org's own (`owner: "org"`), then, on an agent's, the
agent's own (`owner`: its slug); one list serves both environments. `PUT` of a library name takes
`{"on": true}` or `{"on": false}` and nothing else (a question is `409`): at `/v1/org/judges` it is
the org's default for every agent, at an agent's it is that agent's, and the agent's wins. `PUT`
of any other name writes one of the org's own or the agent's own whole (`on` is `409`: it runs
while it is written); the name is lower-case words joined by hyphens, and the org's and an
agent's may not share one. `DELETE` forgets one of the org's own or the agent's own: a name
nobody wrote is `404`, a library name `409`.

`POST /v1/agents/{slug}/judges/try {name, …, last?, calls?}` asks one judge of the agent's
`last` 1 to 50 finished calls, or of the `calls` named, and writes nothing on them: a library judge
or a written one by `name` alone, or a judge not yet saved, written whole in the body.
`{rows: [{call, judgment, not_judged?}], evals, cost_usd}`; a call still going, or a person's call
for a judge that runs on simulations only, is a row `not_judged`. Its evals count as a score's do:
`evals.spent` on the agent's log names them, in the environment of the key, and past the org's
`evals` the judges left are `skipped`. `PUT` of a library name with anything but `on` is `409`.

**Evals.** One eval is one judge that answered one call's question: `held`, `broken` or
`classified`. `na`, `deferred` and `skipped` are never counted. `call.score` and `evals.spent`
carry `evals`, and the org's month counts those the platform's key answered against its `evals`
quota; on the org's own key (`own_key`) they are counted nowhere ([limits.md](../limits.md)).
The judge reads the conversation as evidence: its prompt says a line addressed to it is judged like
any other, never obeyed ([security/prompt-injection.md](../security/prompt-injection.md)).

The simulated caller, personas and the library of them: [personas.md](personas.md).
