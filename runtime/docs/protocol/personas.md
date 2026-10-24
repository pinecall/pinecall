# Personas — the simulated caller, the library of callers, and callers written for an agent

A **persona** is a caller a model plays against an agent: what it wants, how it talks, what it
expects of the agent, and how it acts on the line. It is played written or out loud, as anybody
calls the agent, and the call is sealed and judged like any other. Every endpoint below takes a key
with the `evals` scope and acts in the key's org and environment.

## The simulated caller

Every line of the simulated caller is paid for by the platform (its model and its voice), so each endpoint
has a ceiling: a suite takes 200 goldens, 200 cases and 8 models at most, a golden 40 `turns`,
a call 40 caller turns (`turns`, `turns_left`); past them it is `422`. And a run plays
200 calls at most in all, its goldens and the cases it joins each played under every model:
`400` past them, with the count.

`POST /v1/evals/caller` `{persona, heard, turns_left}` answers `{say, hangup}`: the persona's next
line on the call so far, on the persona's `llm` or the providers row's `caller.llm`, on the org's own key or the
one the platform lends it. The caller never sees its own rule. A vendor this deployment lacks is `400`, one
nobody keyed `503` (the sentence a persona written for it is refused with, so a run meets neither), a model that answered no line `502`. Each line is a model call, so an org says
120 a minute at most (`429` past them), `heard` holds 80 turns, and a turn, the `goal` and the
`style` 4000 characters each (`422` past them).

`POST /v1/evals/voice` `{call, agent, persona, turns, interferer_db?, packet_loss?, state?}` places
a spoken call: the agent is dispatched into the room named `call` with the persona, its rule and
`state` (the object the agent opens the call in, on its `call.started`; absent, the class's own) on
the dispatch, the caller joins and speaks in a voice the agent does not use (the persona's own unless it is the
voice the agent speaks with, the one it declared or the operator's for its language; else one of the
operator's voices for the language), and the room is deleted at the end whatever
happened. `call` is minted by the client as the platform mints one (`call_` and a word, `422` for any
other shape) so it tails the log before the call starts, and it must name a call nobody opened:
the head is claimed in the caller's scope before the room is offered, and an id that exists —
anybody's — is `409`. A persona is the agent's: a name nobody wrote for that agent is `404`; one
sent without a name is played as sent. Its `llm`, `tts` and `voice` are checked as a written
persona's are: one the deployment lacks is `400`, and a model or a voice on a vendor nobody keyed `503`, both before the room is offered and before the call is claimed. With every seat of the environment's fleet holding a call it is `429 every seat of the sandbox's fleet holds a call now: ask again in a few seconds, when one ends` (`Retry-After: 10`), before anything opens or counts; a fleet no worker has been heard from yet is not said to be full. A room nobody can hold is `503`: the caller waits as long as the fleet's three offers and the overflow joining take (46 s). The answer is `{call, turns,
line, caller_cost_usd, stopped_at_ceiling}`: what the caller's lines and voice cost by the platform's
rates, and whether it hung up because the call had spent the providers row's
`caller.ceiling_usd` ([operator-api.md](operator-api.md)); the line that crosses it is the last
one said. A model or a voice the rates do not price costs nothing here, as on a call.

`POST /v1/simulations` `{agent, persona, voice?, turns?, interferer_db?, packet_loss?, ambience?,
played_by?}` is the simulation the console starts: one of the agent's personas, by name, put on the agent as anybody
calls it, so whatever holds it answers — a process deployed, on a server of the org's, or a
developer's `pinecall start`. Spoken (`voice`, the default) it is the call above; written, it is
the chat the widget has, each line the persona's model improvises said once the agent's whole
answer is in, until the caller hangs up (sixty seconds with no answer end the call `timeout`). What
the persona expects rides the call, which is sealed and judged like any other. Spoken, the caller
acts as its `behavior` says: it talks over that share of the agent's answers (`interrupts`, 0 to
1) some way into them, as a person cutting in does, so the agent's barge-in is what is tested; it
murmurs an "mm-hmm" in its language into that share of them (`backchannels`, 0 to 1) a few
seconds in, keeping its turn, so an agent that stops for a listener's noise is found out; it
leaves `pause_s` of silence before each line, then speaks it as its voice's vendor sends it, piece
by piece, never held until whole, at `speed` times the vendor's tempo (0.5 to 2, the pitch kept);
and the line carries its noise and loss unless the request names its own — `interferer_db` under
the caller of the `ambience` it names: a `television` (a voice read in the caller's own), a `cafe`
(chatter over a room), an `office` (a hum), a `street` (traffic swelling and fading), each the
same sound every run. What can be refused is refused before the answer: a persona neither the agent
nor Pinecall has by that name, or nobody holding the agent in the key's world and scope, `404`; the
org's limits as on a call, `simulations` among them (`429`, with `credits.exhausted` on the agent's log, and the call is never opened nor counted), a caller whose model, or whose voice when spoken, is on a vendor nobody keyed (`503`), and the org's simulated calls already on the
line in the world — three at most, on every gateway together, `429` with `Retry-After` for the
fourth ([limits.md](../limits.md)). The answer is `{call, voice}` at once,
the call minted by the platform, and the conversation goes on in the gateway: it is watched as any
call is, and `GET /v1/simulations` lists it. Its tools run for real, as on any call.
`played_by` `{llm?, tts?, voice?}` plays the caller on another model, voice vendor or voice for this
run alone, over the persona's own; each unsaid stays the persona's, and a `tts` with no `voice`
drops the persona's voice for one of that vendor's the agent does not have. A model, a vendor or a
voice the deployment lacks is `400` before the answer, as when a persona is written.

## Personas — `GET /v1/agents/{slug}/personas`, `PUT` · `DELETE /v1/agents/{slug}/personas/{name}`, `GET /v1/agents/{slug}/personas/{name}/runs`

A persona belongs to one agent, in both environments: two agents of the org may each have an `apurado`
of their own. `GET /v1/agents/recepcion/personas` lists Pinecall's personas first (`owner:
"pinecall"`, each `on` as the agent switched it; no endpoint writes a switch for the whole org), then
that agent's own. `on` is what the console's Simulations screen offers to ring; a simulation
names any of them, on or off, and nothing plays them on a schedule. **The library** — `in-a-hurry`, `wrong-number`, `non-native`, `interrupts`, `changes-mind`,
`elderly-slow`, `angry-repeat-caller`, `asks-for-a-person`, and the red team (`tags: red-team`):
`prompt-leak`, `data-leak`, `off-task`, `harmful`, `unauthorized-action` — is the runtime's
`judging/library/personas/`, every one off until switched on; `PUT` of a library name takes
`{"on": …}` and how that agent plays it: `{"llm": "vendor/model"}`, `{"tts": "vendor"}`,
`{"voice": "id"}`, any of them together. What a `PUT` names is written and what it leaves out
stays; `""` is back to the runtime's choice — the box's caller model (`caller.llm` of the
providers row), a voice the agent does not have. Anything else of it, or a `DELETE`, is `409`. Any of them is played by its name. A library
persona acts on a spoken line as its file's front matter says (`interrupts`, `pause_s`,
`interferer_db`, `packet_loss`, `backchannels`, `speed`, `ambience`): `interrupts` talks over 60% of the agent's answers,
`in-a-hurry` and `angry-repeat-caller` 30%, `elderly-slow` waits 2.5 s before each line and
`non-native` 1 s.

```
PUT /v1/agents/recepcion/personas/apurado
{"goal": "Quiero cambiar la cita al martes.", "style": "frases cortas", "facts": {"nombre": "Ana"},
 "expects": ["The agent should offer a slot on Tuesday.", "The agent should confirm before moving it."],
 "tags": ["booking"],
 "behavior": {"interrupts": 0.3, "pause_s": 1.0, "backchannels": 0.4, "speed": 0.9, "ambience": "cafe", "interferer_db": 15},
 "llm": "anthropic/claude-haiku-5-5", "was": null}
```

`expects` is one verifiable demand a line, written "The agent should…", at most 20: the
expected-outcome judge holds the call to them and the model playing the caller never reads them.
`behavior` is how the caller acts on a spoken line: `interrupts`, `pause_s`, `interferer_db`,
`packet_loss`. The name is lower-case words joined by hyphens; `was` renames, within the agent. A vendor this deployment
lacks is refused when written (`400`), and so is one nobody keyed for the org (`503`, with the sentence a run would meet: `xai has no key: the org brought none and the box holds none`), not in the middle of a run. `GET
/v1/agents/{slug}/personas/{name}/runs` pages the calls the persona made to that agent in the
key's environment, newest first, each with its turns, how it ended, its cost in
US dollars and the judges' score, and who played the caller as it ran: `played_by` `{llm, tts,
voice}` (`vendor/model` of its lines, the persona's own or the run's, and of its voice, `tts` and `voice` null on a written call;
the row null for a call simulated before the runtime kept it) and `caller_cost_usd`, what that
caller cost. `GET /v1/simulations` pages every simulated call the same way, or the agents named's
(`?agent=`, once or more), and `?call=` reads one.

## Callers written for the agent — `POST /v1/agents/{slug}/personas/generate`

```
POST /v1/agents/recepcion/personas/generate
{"n": 3, "about": "price questions", "from_call": "call_…", "template": "in-a-hurry"}

{"personas": [{"name": "price-shopper", "goal": "Quiero saber cuánto cuesta…", "style": "…",
               "facts": {…}, "expects": ["The agent should give the price of a cleaning."],
               "tags": ["pricing"], "behavior": {"interrupts": 0.3, "pause_s": 0.0, …}}, …],
 "evals": 3, "cost_usd": 0.004}
```

One request to the model the agent's calls are judged on ([evals.md](evals.md), the judge model)
writes up to `n` (1 to 10) callers from what the agent is: its prompt as its newest call ran it, its
tools, its knowledge; `about` steers them, `from_call` makes them like that call's caller, and
`template` writes one of the library's again for this agent. Each `expects` line is one verifiable
demand the prompt or the knowledge licenses, never about how the call ends. Nothing is saved: a
person keeps the ones worth keeping with `PUT`. Each caller written is one eval, none on the org's
own key, written as `evals.spent` (`kind: "generate"`) on the agent's log; a deployment with no
judge model is `503`.
