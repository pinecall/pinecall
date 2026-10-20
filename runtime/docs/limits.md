# Limits: what an org may use, and whose keys it runs on

A runtime holds vendor keys and **lends** them to its orgs; an org may **bring** its own to pay its own
vendors. A call runs on the org's key, else on a lent one, else is refused before it starts.

## Quotas, per environment

An org has one set of limits in production and another in the sandbox: minutes, messages,
LLM tokens, calls at once, agents, remembered facts, knowledge chunks, bought numbers, seats,
hosted apps, evals and simulations; and a budget in dollars, which both environments spend from.
A limit nobody set is no limit; zero is a limit that refuses everything, which is how a plan
leaves a feature out. The set is replaced whole, so a limit left out stops being one.

What an org used is counted from its calls' summaries and scores in that environment, every time a
call, a turn, a judge or a simulated caller asks to start. The database keeps the count, one row per org, environment and calendar month (UTC)
in `usage_totals`: a summary adds to it in the transaction that writes it, an erasure takes its
calls out, and admission reads the month it is in, so minutes, messages and tokens start again on
the first of each month (UTC), and a call is counted in the month its summary was written.
Nothing is kept in memory, so a restart counts what the database holds; `pinecall-runtime usage
rebuild` folds the table again from the summaries in the log.
What the sandbox spent never closes production, except through the budget: dollars are the same
in both environments.

- **A call** is refused past `concurrent_calls`, `minutes`, `messages` or `llm_tokens`. The calls
  at once are the platform's: every gateway counts its own and says them each second, so two gateways
  opening at the same moment may go past the limit by what they opened that second. One that
  is let in is told how many seconds are left of the minutes, and ends there.
- **A budget** (`budget_usd`, whole dollars a calendar month) refuses a new call once what the
  org's calls in both environments cost this month, as the summaries priced them, reaches it
  (`the org has spent 10.5 of its 10 USD budget this month`). A call already running is never cut
  for it, and written turns are not held to it.
- **A written turn** is held to `messages` and `llm_tokens` on every turn, with what the open
  conversation has spent so far added to the org's totals.
- **Agents, numbers, facts, seats and chunks** are refused at their limit; a push that would pass
  `knowledge_chunks` is refused whole.
- **Hosted apps** (`hosted_apps`) are counted when an app's first release is uploaded
  ([protocol/hosting.md](protocol/hosting.md)), and a Studio agent when it is made or first deployed
  to production ([protocol/studio.md](protocol/studio.md)): each is one hosted app. A later release
  of an app the org already has is never refused for it.
- **Evals** (`evals`) are the judges that answered a call (held, broken or classified) on the
  runtime's key this month, a call's score and a judge tried on calls alike; a judge on the org's
  own key is never one. Past the limit a call still seals: the judges left are `skipped`, saying
  the month's evals are used up, and `credits.exhausted` lands once for that call.
- **Simulations** (`simulations`) are the calls a simulated caller played this month: a persona's,
  a spoken golden's. One past the limit is refused before it opens, and a run that reaches it
  stops where it is. A simulated call never counts minutes, and neither does a call an eval run
  opened.

A refusal is a `429` whose sentence names the quota, what was used and the limit
(`the org has used 30 of its 30 minutes in the sandbox`), and `credits.exhausted` lands in the
agent's log with the same numbers.

## What a new org is given

What an org gets when it is made is the runtime's `admission` setting (the console's Box settings ▸ Admission, `pinecall-runtime box admission`, or `PUT /v1/ops/admission`): the
limits in each environment for a person's first org, and, when the platform gives one trial per person, the
limits for any later org of the same address. A deployment with no such setting gives a new org no
limits, which is what a self-hosted platform runs.

```json
{
  "first": {
    "sandbox":    {"minutes": 30, "messages": 300, "llm_tokens": 2000000, "concurrent_calls": 1,
                   "evals": 500, "simulations": 10,
                   "lends": ["deepgram", "cartesia", "anthropic/claude-haiku-5-5"]},
    "production": {"minutes": 0, "messages": 0, "llm_tokens": 0, "evals": 0, "simulations": 0,
                   "lends": []}
  },
  "later": {
    "sandbox":    {"minutes": 0, "messages": 0, "llm_tokens": 0, "lends": []},
    "production": {"minutes": 0, "messages": 0, "llm_tokens": 0, "lends": []}
  }
}
```

## Whose vendor keys a call runs on

An org's own key for a vendor runs any model of that vendor, whatever the runtime lends:

```bash
pinecall providers add deepgram        # the org's own key, sealed; every Deepgram model is theirs to run
```

Where an org brought no key, its calls run on the runtime's, and only on what the org's `lends`
says in that environment: **null** lends every key the runtime holds, an **empty list** lends none, and
otherwise each entry is a vendor (`deepgram`) or a vendor and a model prefix
(`anthropic/claude-haiku-5-5`). A vendor nobody holds a key for is refused before the call
opens. The operator sets it per org and environment with `pinecall-runtime orgs lends <org> --env
<env> <list|all|none>`, which keeps the org's limits (`orgs quota` keeps its lends); a new org is
born with what admission lends. The org reads it back in `GET /v1/limits` (`lends`): `pinecall
limits`, the MCP's `usage`, the console's Overview and Providers say which vendors are its own and
which the runtime lends.

`setup` gives the org `default` each key it finds as its own too, so the operator's own agents may name
a plugin's options. That copy follows the runtime's key: `pinecall-runtime box keys set <vendor>` (or
the console's Box settings ▸ Keys) puts the new key in every org whose own key was the old one, and
`box keys rm` forgets those copies with it. A key an org brought that is a different one stays its own.

A stage on a lent key runs as the operator configured it: the plugin's class and options are the
providers row's alone. An agent that names its own (`builds`, `options`, from its class or its
settings) runs that stage only on the org's own key, and is refused on a lent one — when the class
registers, when the settings are set, and when a call's stages are handed out — naming the vendor
and `pinecall providers add`. An option can point a plugin at another server; the runtime's key
goes to the vendor and nowhere else.

The **simulated caller** (its model and its voice) always runs on the runtime's keys. The
**judge model** does too, the providers row's `judge`, unless the org names its own
(`PUT /v1/org/judging`) or the agent does (its `judge`): a model on a key of the org's own, a
local one among them, is the org's to pay and its evals are never billed; one on a key the
platform lends is lent as any stage is, by `lends`. A judge model the agent or the org names is
tried when it is saved, on the org's keys in every environment it would judge in, so a model nobody
can key is refused there and never fails a hang-up. Neither the judge nor the caller spends the
org's minutes or tokens; the org pays for them as **evals** (one judge that answered one call on the
runtime's key: `held`, `broken` or `classified`, never `na`) and **simulations** (one call a
simulated caller played), which `call.score`, `evals.spent` and `call.summary` carry and the usage
feed counts ([charging-for-it.md](charging-for-it.md) §3), each held to its quota above.
