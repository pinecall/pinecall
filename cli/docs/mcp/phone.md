# The phone

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `line`

Who answers the agent's number right now and who could take it; which phone is the person's own, so their calls reach their copy.

`line show` says whose process a ring at the agent's number lands in. `from <number>` says which phone is the person's own, once: their calls reach the copy they hold (the one `start` holds) while everybody else reaches production. `claim` takes the line for this copy, `release` gives it back, `forget` drops the phone.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `from` · `forget` · `claim` · `release` | required | show whose process a ring lands in; from says which phone is the person's own; forget drops it; claim takes the line for this copy; release gives it back |
| `agent` | text |  | the agent's name; the project's only agent when left out |
| `number` | text |  | `from`: the person's own phone, in +E.164 |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "show"
}
```

```json title="answered"
{
  "agent": "front-desk",
  "env": "sandbox",
  "held": true,
  "holding": {
    "holder": "m_4f1c2a9b0e7d",
    "name": "you@example.com"
  },
  "yours": true,
  "waiting": [],
  "calling": []
}
```

## `numbers`

The org's numbers and the agent each reaches; the numbers its carrier accounts own; importing one, or buying one on the deployment's account, shown as steps before anything is written.

`numbers list` shows which number reaches which agent in the sandbox; `available` what the org's carrier accounts own. `import` points a number an account owns at an agent; when the org has several accounts, name the one that owns it in `account`, or ask the person which. `buy` gets a new number in `country` (and `area_code`) on the deployment's own account and points it at the agent; a bought number counts against the org's `numbers` limit (`usage` shows it), an imported one never does. Both first answer the steps they would take and write nothing; call again with `dry_run: false` to do them, after the person agreed. Letting a number go is never a tool: `pinecall numbers drop` in a terminal.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `list` · `available` · `import` · `buy` | required | list the org's numbers; available is what its carrier accounts own; import points one of them at an agent; buy gets a new one on the deployment's account — import and buy are a dry run unless dry_run is false |
| `number` | text |  | `import`: the number, in +E.164 |
| `agent` | text |  | `import`, `buy`: the agent that answers it |
| `channel` | `phone` · `whatsapp` |  | `import`, `buy`: phone unless it is a WhatsApp number |
| `account` | text |  | `available`, `import`: the carrier account the number lives in, when the org has several (`carriers list` names them) |
| `move` | true or false |  | `import`: take the number off the trunk it is on now (another environment's, or another agent's), as a 409 naming that trunk asks |
| `country` | text |  | `buy`: the country, two letters (ES, US) |
| `area_code` | text |  | `buy`: an area code, digits only |
| `dry_run` | true or false |  | `import`, `buy`: true (the default) answers the steps and writes nothing; false does them |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "list"
}
```

```json title="answered"
{
  "numbers": [
    {
      "route": {
        "org": "org_98889a61509c",
        "agent": "front-desk",
        "channel": "phone",
        "number": "+15550104133",
        "label": null,
        "env": "sandbox",
        "managed": false
      },
      "origin": "imported",
      "rings": "broken",
      "last_call_at": null,
      "via": null,
      "account": "AC5f7c1e0a4d9b2f4e6a8c3d5f7a9b1c2d3e"
    }
  ]
}
```

## `carriers`

The org's carrier accounts — Twilio, a SIP peer, WhatsApp — and one account's networks and how outbound calls leave. Never a secret.

`carriers` lists the org's carrier accounts and shows one. Adding one takes its secrets, so it is never a tool: the person types `pinecall carriers add` in a terminal, or uses the console's Numbers screen.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `list` · `show` | required | list the org's carrier accounts, or show one |
| `account` | text |  | `show`: the account's id |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "list"
}
```

```json title="answered"
{
  "carriers": [
    {
      "kind": "twilio",
      "account": "AC5f7c1e0a4d9b2f4e6a8c3d5f7a9b1c2d3e",
      "label": "",
      "networks": []
    }
  ]
}
```

## `callbacks`

The callers waiting to be called back, oldest first: who, on which channel, through what (the overflow, the agent's own tool, the widget).

`callbacks` lists the people waiting for a call back, each with the call it came from.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text |  | only this agent's |
| `after` | a whole number 0 or more |  | where the page before ended |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{}
```

```json title="answered"
{
  "requests": [],
  "next": null
}
```
