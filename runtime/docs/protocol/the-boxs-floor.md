# The platform's floor — `GET /v1/ops/events`

Part of the [operator API](operator-api.md): every org's floor changing, on one stream, for
whatever serves the platform as a whole. One org's key reads its own floor at `GET /v1/events`; this is
the same moments, every org at once, on the operator's key alone. There is no `?token=`: nothing
that reads this runs in a browser.

SSE, live only, from the moment it opens: no cursor, nothing replayed. The entries are the org
feed's: `agent.registered` · `agent.detached`, `call.ringing` · `call.dialing` · `call.started` ·
`call.ended`, `attention.requested` · `attention.answered`, `supervisor.took_over` ·
`supervisor.released`, and `call.summary` · `call.score` with `data` empty: they say the call was
sealed and judged, which is when a list redraws its row, and nothing of what it said or how it was
judged — that is read off the call. A turn is never on it. Each frame is one entry wrapped with the org whose
log it is and the environment its call runs in (`production`, `sandbox`); an agent's own entries serve
both environments, and their `env` is `null`. A reader that serves one environment, such as a notifier that
pages people for production's calls, keeps the frames of that environment and drops the rest:

```
id: 1
event: call.ringing
data: {"org":"org_…","env":"production","entry":{"seq":1,"ts":1727170000.1,"call":"CA_…","agent":"clinica-norte","type":"call.ringing","ephemeral":false,"data":{…}}}
```

`id:` is the entry's `seq` in its own log, so ids from two calls interleave and a reconnect opens
from now. `retry: 1000` opens the stream and `: ping` comes every 25 s of quiet. An entry whose log
nobody claimed yet carries no org and is left out.

The box also says what happens to it and to no org: `worker.changed`, when a worker of a fleet is
first heard, changes what the fleet's screen shows (its calls, its load, a cordon, a drain), goes
silent past `stale_after_s` or comes back. Its frame has `org` empty and `env` `null`, and its
`data` is the worker, its fleet and whether it is heard and cordoned: the fleet is read at
`GET /v1/ops/fleet`. Each gateway says the workers that beat on it.
