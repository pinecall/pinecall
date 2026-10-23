# Supervising a live call

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `supervise`

A live call, as a supervisor's desk sees it: its transcript as it happens (`watch`), and a move on it — whisper to the agent, say a line in its voice, take the line, give it back, transfer, end.

`supervise` is the desk `pinecall supervise` is in a terminal, for a call that is happening. `watch` answers the call's lines since `after` — the caller's, the agent's, its tool calls, every move of a desk, the end — and waits up to `wait_s` for more while the call is live; pass the `next` it answers to keep reading. `whisper` reaches the agent as an instruction for its next reply and the caller never hears it; `say` puts words in the agent's voice; `takeover` silences the agent until `release`; `transfer` and `end` act on the caller, at once. Every move lands in the caller's own log as a `supervisor.*` entry. On a call that has ended `watch` answers what it was, `live: false`, and every move is refused: `call` reads it whole. The audio of a live call is the console's Live screen (`console_url`).

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `watch` · `whisper` · `say` · `takeover` · `release` · `transfer` · `end` | required | watch reads what was said since `after`, waiting up to wait_s for more; whisper tells the agent something the caller never hears; say makes the agent say `text` verbatim; takeover silences the agent and puts a person on the line; release gives the line back; transfer sends the caller to `to`; end hangs up |
| `call` | text | required | the live call's id: `calls` lists the agent's newest, a live one marked live |
| `text` | text |  | `whisper` and `say`: the words |
| `to` | text |  | `transfer`: the number in +E.164, or the SIP address, the caller is sent to |
| `mode` | `cold` · `warm` |  | `transfer`: cold sends the caller at once; warm lets the agent introduce them first |
| `reason` | text |  | `end`: why, kept in the call's log |
| `after` | a whole number 0 or more |  | `watch`: the `next` the answer before ended at; the call's beginning when left out |
| `wait_s` | a whole number 0–50 |  | how long to wait before answering what is known so far, in seconds; 25 when left out |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "action": "watch",
  "call": "call_bf4f00ba21b3410ca6bbedcd6c963269",
  "after": 42,
  "wait_s": 5
}
```

```json title="answered"
{
  "call": "call_bf4f00ba21b3410ca6bbedcd6c963269",
  "live": true,
  "lines": [
    {
      "seq": 43,
      "desk": "whispered",
      "said": "Offer to have the manager call her back today."
    },
    {
      "seq": 45,
      "caller": "Can someone call me about it?"
    },
    {
      "seq": 56,
      "agent": "Would you like a manager to call you back today? I can note that request, but I can't promise the call will happen."
    }
  ],
  "next": 57
}
```

```json title="called with"
{
  "action": "whisper",
  "call": "call_bf4f00ba21b3410ca6bbedcd6c963269",
  "text": "Offer to have the manager call her back today."
}
```

```json title="answered"
{
  "call": "call_bf4f00ba21b3410ca6bbedcd6c963269",
  "sent": {
    "verb": "whisper",
    "text": "Offer to have the manager call her back today."
  }
}
```
