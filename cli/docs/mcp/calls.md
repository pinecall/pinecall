# Calls, and what they run on

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `calls`

The agent's newest calls: each one's id, channel, length, how it ended, its cost and its verdicts.

`calls` lists the agent's newest calls with their ids; `call` reads one whole.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `limit` | a whole number 1–100 |  | how many, newest first; 20 when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "limit": 2
}
```

```json title="answered"
{
  "agent": "front-desk",
  "calls": [
    {
      "call": "call_ca0bf3567bf84a528071f482b43c4a92",
      "agent": "front-desk",
      "live": false,
      "last_seq": 33,
      "status": "ended",
      "channel": "web",
      "direction": "inbound",
      "from": "web_7b7c541fea4c",
      "to": "front-desk",
      "caller": null,
      "started_at": 1791490518.67,
      "ended_at": 1791490520.76,
      "end_reason": "caller_hung_up",
      "outcome": "Your message has reached the team. Thank you for calling, and goodbye.",
      "cost": "…",
      "score": "…",
      "flags": [],
      "attention": null
    },
    "… 1 more"
  ]
}
```

## `call`

One call's log, entry by entry — every turn, tool call, result, state change, metric and verdict — a page at a time.

`call` reads one call's log the way the runtime keeps it: every entry with its seq, quiet ones included — the turns, each tool call and its result, the state after it, the latency of each turn, the cost, and the verdicts at hang-up (`call.score`). Page with `after` set to the `next` the page before answered, until `next` is null; `types` narrows a page and never ends the reading early. `live` says the call is still going.

| parameter | takes | | what it is |
|---|---|---|---|
| `call` | text | required | the call's id |
| `after` | a whole number 0 or more |  | only entries after this seq: the `next` of the page before |
| `limit` | a whole number 1–500 |  | entries in this page; 200 when left out |
| `types` | a list of texts |  | only these entry types, such as turn.agent or call.score |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "call": "call_ca0bf3567bf84a528071f482b43c4a92",
  "types": [
    "turn.user",
    "tool.call",
    "turn.agent",
    "call.score"
  ]
}
```

```json title="answered"
{
  "call": "call_ca0bf3567bf84a528071f482b43c4a92",
  "entries": [
    {
      "seq": 3,
      "ts": 1791490518.82,
      "call": "call_ca0bf3567bf84a528071f482b43c4a92",
      "agent": "front-desk",
      "type": "turn.user",
      "ephemeral": false,
      "data": {
        "text": "Hi, this is Ana Ruiz. My order A-1042 arrived broken, please tell the manager.",
        "item_id": "item_3d7916dcc7aa",
        "metrics": "…",
        "language": null,
        "speech_id": "speech_05809278d21d",
        "transcript_confidence": null
      }
    },
    {
      "seq": 11,
      "ts": 1791490519.77,
      "call": "call_ca0bf3567bf84a528071f482b43c4a92",
      "agent": "front-desk",
      "type": "tool.call",
      "ephemeral": false,
      "data": {
        "name": "takeMessage",
        "call_id": "toolu_01Gn8MKVAQeCDMeHeFytYmUY",
        "arguments": "…",
        "speech_id": "speech_05809278d21d"
      }
    },
    {
      "seq": 29,
      "ts": 1791490520.58,
      "call": "call_ca0bf3567bf84a528071f482b43c4a92",
      "agent": "front-desk",
      "type": "turn.agent",
      "ephemeral": false,
      "data": {
        "text": "Your message has reached the team. Thank you for calling, and goodbye.",
        "item_id": "item_217ff9c2410b",
        "metrics": "…",
        "speech_id": "speech_05809278d21d",
        "interrupted": false
      }
    },
    "… 2 more"
  ],
  "next": null,
  "live": false
}
```

## `pipeline`

What the agent hears, decides and speaks with — the vendors and models of each stage — and the latency each measured.

`pipeline` reads the three stages a call runs on (ears, model, voice), which vendor and model each is, and the medians the agent's recent calls measured.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{}
```

```json title="answered"
{
  "agent": "front-desk",
  "hears": {
    "vendor": "deepgram",
    "model": null,
    "voice_id": null,
    "language": null
  },
  "decides": {
    "vendor": "anthropic",
    "model": null,
    "voice_id": null,
    "language": null
  },
  "speaks": {
    "vendor": "cartesia",
    "model": null,
    "voice_id": null,
    "language": null
  },
  "greeting": {
    "say": "Thanks for calling. How can I help?",
    "reply": null,
    "allow_interruptions": null
  },
  "voices": [],
  "providers": [
    {
      "name": "anthropic",
      "does": [
        "llm"
      ],
      "aliases": [],
      "note": "",
      "standing": "ready",
      "ready": true,
      "env": null,
      "extra": "anthropic",
      "voices_listed": false,
      "availability": "offered",
      "broken": null
    },
    {
      "name": "assemblyai",
      "does": [
        "stt"
      ],
      "aliases": [],
      "note": "",
      "standing": "no key",
      "ready": false,
      "env": null,
      "extra": "assemblyai",
      "voices_listed": false,
      "availability": "bring your own",
      "broken": null
    },
    "… 43 more"
  ],
  "defaults": {
    "llm": "anthropic",
    "stt": "deepgram",
    "tts": "cartesia"
  },
  "models": {
    "stt/deepgram": [
      "flux-general-multi"
    ],
    "tts/elevenlabs": [
      "eleven_flash_v2_5"
    ]
  },
  "calls": 20,
  "medians": [
    {
      "name": "llm_node_ttft",
      "seconds": 0.41,
      "turns": 34
    },
    {
      "name": "talk_share",
      "seconds": 1,
      "turns": 20
    }
  ],
  "unavailable_reasons": {}
}
```

## `providers`

The vendors an agent may run on: what each does, whether it is ready, and whose key it would run on. Never a key.

`providers` lists every speech, model and voice vendor this gateway can run, what each does, and whose key a call would use. Bringing a key of your own is never a tool: the person types `pinecall providers add <vendor>` in a terminal, or uses the console.

| parameter | takes | | what it is |
|---|---|---|---|
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{}
```

```json title="answered"
{
  "providers": [
    {
      "name": "anthropic",
      "does": [
        "llm"
      ],
      "aliases": [],
      "note": "",
      "standing": "ready",
      "ready": true,
      "env": null,
      "extra": "anthropic",
      "voices_listed": false,
      "availability": "offered",
      "broken": null
    },
    {
      "name": "assemblyai",
      "does": [
        "stt"
      ],
      "aliases": [],
      "note": "",
      "standing": "no key",
      "ready": false,
      "env": null,
      "extra": "assemblyai",
      "voices_listed": false,
      "availability": "bring your own",
      "broken": null
    },
    {
      "name": "asyncai",
      "does": [
        "tts"
      ],
      "aliases": [],
      "note": "",
      "standing": "no key",
      "ready": false,
      "env": null,
      "extra": "asyncai",
      "voices_listed": false,
      "availability": "bring your own",
      "broken": null
    },
    "… 42 more"
  ],
  "defaults": {
    "llm": "anthropic",
    "stt": "deepgram",
    "tts": "cartesia"
  },
  "voices": [],
  "models": {
    "stt/deepgram": [
      "flux-general-multi"
    ],
    "tts/elevenlabs": [
      "eleven_flash_v2_5"
    ]
  }
}
```

## `telemetry`

Where the org's calls' traces go — its own OpenTelemetry collector — shown or cleared. Setting one is the person's, in a terminal: a header's value is a credential.

`telemetry` reads where a copy of every spoken call's spans goes over OTLP, and can stop it. Pointing it at a collector is never a tool, since a header's value is a credential: the person types `pinecall telemetry set <url> --header <name>` in a terminal, where each value is read off stdin.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `clear` | required | show says the collector, the headers' names and whether words travel; clear stops the export |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "show"
}
```

```json title="answered"
{
  "collector": {
    "endpoint": "https://otel.example.com/v1/traces",
    "header_names": [
      "x-api-key"
    ],
    "pii": false
  }
}
```

## `monitors`

The numbers the org watches over a window — latency, the judges' held rate, escalations, tool failures, spend, calls — and the line each must not cross; list them, add one, forget one.

`monitors list` says what the org watches in the env — each monitor's rule, who set it, the last day it fired and the value that crossed. `add` watches one number of the observability series (the same the console's Observability screen draws) over 1, 7 or 30 days, for every agent or one, and fires once a day as `monitor.fired` on the agent's log the first time a call's seal finds it on the wrong side of the line. `rm` forgets one. Use it when the person asks to be told when latency, the judges, escalations, tool failures, spend or volume slip.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `list` · `add` · `rm` | required | list says every monitor with the last day it fired; add watches a number; rm forgets one by id |
| `name` | text |  |  |
| `metric` | `e2e_median_s` · `llm_median_s` · `held_rate` · `escalated_rate` · `tool_failure_rate` · `spend_usd` · `calls` |  |  |
| `above` | true or false |  |  |
| `threshold` | a number |  |  |
| `windowDays` | `1` or `7` or `30` |  |  |
| `agent` | text |  |  |
| `id` | text |  | rm: the monitor's id, from list |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "add",
  "name": "slow answers",
  "metric": "e2e_median_s",
  "above": true,
  "threshold": 2,
  "window_days": 7
}
```

```json title="answered"
{
  "monitor": {
    "id": "mon_3f9a1c2b4d5e",
    "name": "slow answers",
    "metric": "e2e_median_s",
    "above": true,
    "threshold": 2,
    "window_days": 7,
    "agent": null,
    "created_by": "m_ana",
    "fired_on": null,
    "fired_value": null
  }
}
```

```json title="called with"
{
  "action": "list"
}
```

```json title="answered"
{
  "monitors": [
    {
      "id": "mon_3f9a1c2b4d5e",
      "name": "slow answers",
      "metric": "e2e_median_s",
      "above": true,
      "threshold": 2,
      "window_days": 7,
      "agent": null,
      "created_by": "m_ana",
      "fired_on": "2026-10-08",
      "fired_value": 2.41
    }
  ]
}
```

## `webhook`

Where the org posts its alerts — a monitor fired, the spend unusual, a quota out — shown, proven with a signed test post, or cleared. Setting one is the person's, in a terminal: the secret is a credential.

`webhook` reads where this org's alerts are posted beyond the agent's log ({type, org, env, agent, at, data}, with x-pinecall-event and, when a secret is set, x-pinecall-signature as sha256=<HMAC-SHA256 of the body>), proves the URL with a test post, and can stop it. Pointing it somewhere is never a tool, since the secret is a credential: the person types `pinecall webhook set <url> --secret` in a terminal, where the secret is read off stdin.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `test` · `clear` | required | show says the URL and whether posts are signed; test posts one webhook.test event and says whether the URL answered 2xx; clear stops the posting |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "show"
}
```

```json title="answered"
{
  "webhook": {
    "url": "https://hooks.example.com/pinecall",
    "signed": true
  }
}
```

```json title="called with"
{
  "action": "test"
}
```

```json title="answered"
{
  "sent": true,
  "error": null
}
```

## `usage`

What the org has used of its limits this month in the environment — minutes, messages, evals, simulations, bought numbers — whose keys its calls run on, and whether its judges cost it evals.

`usage` answers “what does this cost?”: each quota as `{limit, used}` (a null limit is no limit; minutes, messages, evals and simulations start again on the first of the month, UTC), `keys` — the vendors the org brought keys for and the ones the deployment lends it; a vendor in neither refuses the call — and `evals_billed` — false when the org's judges run on its own key, where evals are never billed. Past `evals` a call's judges left are skipped; past `simulations` a simulation is refused. `billing_url` is where the org buys more, when the deployment sells plans.

| parameter | takes | | what it is |
|---|---|---|---|
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{}
```

```json title="answered"
{
  "environment": "sandbox",
  "minutes": {
    "limit": 30,
    "used": 12.4
  },
  "messages": {
    "limit": 300,
    "used": 41
  },
  "evals": {
    "limit": 500,
    "used": 212
  },
  "simulations": {
    "limit": 10,
    "used": 3
  },
  "concurrent_calls": {
    "limit": 1,
    "used": 0
  },
  "agents": {
    "limit": null,
    "used": 1
  },
  "seats": {
    "limit": null,
    "used": 2
  },
  "numbers": {
    "limit": 0,
    "used": 0
  },
  "keys": "yours: anthropic · lent by the deployment: google, cartesia, deepgram",
  "evals_billed": true,
  "judge_model": "Pinecall's",
  "billing_url": "https://billing.pinecall.io/"
}
```
