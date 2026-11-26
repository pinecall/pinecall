# The phone

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `line`

Who answers the agent's number right now and who could take it; which phone is the person's own, so their calls reach their copy.

`line show` says whose process a ring at the agent's number lands in. `from <number>` says which phone is the person's own, once: a call from it reaches their sandbox agent (`agent` names which; left out, the one the org holds) at the box's test line, which the answer names, or at a production number, where everybody else reaches production. `claim` takes the line for this copy, `release` gives it back, `forget` drops the phone.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `from` · `forget` · `claim` · `release` | required | show whose process a ring lands in; from says which phone is the person's own; forget drops it; claim takes the line for this copy; release gives it back |
| `agent` | text |  | the agent's name; the project's only agent when left out. `from`: the agent a call from the phone reaches |
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

`numbers list` shows which number reaches which agent in the sandbox; `available` what the org's carrier accounts own. `import` points a number an account owns at an agent; when the org has several accounts, name the one that owns it in `account`, or ask the person which. `buy` gets a new number in `country` (and `area_code`) on the deployment's own account and points it at the agent; a bought number counts against the org's `numbers` limit (`usage` shows it), an imported one never does. One number answers on several channels, each its own route: `channel: "whatsapp"` for the number a WhatsApp account is, `channel: "sms"` for a Twilio number's text messages (Twilio is then told to post them to Pinecall; a number whose messages go to another service is refused until `move: true`). What the number answers on the other channels stays. Both first answer the steps they would take and write nothing; call again with `dry_run: false` to do them, after the person agreed. Letting a number go is never a tool: `pinecall numbers drop` in a terminal.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `list` · `available` · `import` · `buy` | required | list the org's numbers; available is what its carrier accounts own; import points one of them at an agent; buy gets a new one on the deployment's account — import and buy are a dry run unless dry_run is false |
| `number` | text |  | `import`: the number, in +E.164; for `email`, the mailbox's address |
| `agent` | text |  | `import`, `buy`: the agent that answers it |
| `channel` | `phone` · `whatsapp` · `sms` · `email` |  | `import`, `buy`: phone unless said. One number answers on several: import it once a channel. `sms` is a number of a Twilio account, whose messages Twilio then posts to Pinecall; `email` is a mailbox account's address, whose inbox Pinecall reads |
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

The org's carrier accounts — Twilio, a SIP peer, WhatsApp, a mailbox — and one account's networks and how outbound calls leave. Never a secret.

`carriers` lists the org's carrier accounts and shows one. Adding one takes its secret, and the rule is that no key is printed or passed through an assistant, so it is never a tool: give the person the command to type in their own terminal, `pinecall carriers add twilio --account-sid AC… --user SK…` (`sip`, `whatsapp` and `email --address … --imap-host … --smtp-host …` the same way), which reads the secret with nothing echoed.

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

## `dial`

Have an agent call a phone number, with the state its call opens in. The org's dial guards decide: who may be called, when, and how often.

`dial` places a call as the agent and answers before anything rings: the call's id, the number shown and the environment. Somebody must be holding the agent, or the dial is refused. A dial the org's guards refuse (a stranger, quiet hours, no consent, too many) says which guard refused it. `call` reads the call's log afterwards.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text | required | the agent that places the call: its slug |
| `to` | text | required | the number to call, in +E.164 |
| `from` | text |  | which of the agent's own numbers the far end sees; the first when left out |
| `state` | an object |  | the state the agent's call opens in |
| `metadata` | an object |  | what the call's `call.started` carries |
| `greeting` | text |  | the words this call opens with, over the agent's own greeting |
| `instruction` | text |  | what this call is for: the agent reads it for the whole call and, with no greeting, opens on it |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

```json title="called with"
{
  "agent": "reminder",
  "to": "+14155550142",
  "instruction": "Remind Ana of her cleaning tomorrow at 9:30 and ask her to confirm."
}
```

```json title="answered"
{
  "call": "call_5f0c2a9d41c84e1f9d2b7c1a6e3f8b20",
  "agent": "reminder",
  "to": "+14155550142",
  "from": "+14155550134",
  "env": "production"
}
```

## `text`

Have an agent write to a contact first: one SMS to a number, from a number it answers SMS at, or the first email of a thread to an address, from an address it answers email at. The org's dial guards decide: who may be reached, when, and how often.

`text` writes to a contact as the agent and answers with the conversation it was said on: the call's id, the number or address it left from and the environment. What the contact answers reaches the agent on that conversation, with these words before it. To an address it is an email: under `subject`, from an address the agent answers email at (`numbers` imports one with `channel: email`), its words `text` or, left out, written by the agent on `instruction` as a dialled call with no greeting opens; the contact's reply lands on the same conversation. Somebody must be holding the agent, and the agent must answer SMS at a number (`numbers` imports one with `channel: sms`) for an SMS. A contact whose SMS conversation is still open is written on it; any other passes the org's guards as a dial does (a stranger, no consent, quiet hours, too many today), and a refusal says which guard and sends nothing. A contact who asked for no more messages is refused whatever else is true: `compliance consent` says who did.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text | required | the agent that writes: its slug |
| `to` | text | required | the contact's number, in +E.164, or their email address |
| `text` | text |  | what the contact reads; required for an SMS, and an email's is the agent's own to write when left out |
| `from` | text |  | which of the agent's SMS numbers, or email addresses, it leaves from; the first when left out |
| `subject` | text |  | an email's subject, required for one: the thread's, and every reply's after it |
| `metadata` | an object |  | what the conversation's `call.started` carries |
| `instruction` | text |  | what this conversation is for: the agent reads it throughout and, with no `text`, writes its email on it |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

## `template`

Have an agent send a contact one WhatsApp template, the message approved at Meta that opens a conversation there. In production it is sent and Meta charges the number's account; in the sandbox it is answered `simulated` and never sent.

`template` sends one WhatsApp template as the agent and answers where it went: the number it left from, the environment, `simulated`, and Meta's id of the message. Outside the 24 hours after a contact's last message a template is the only thing WhatsApp lets a business write, and it is the one message Meta charges for. In the sandbox nothing is asked of Meta: the answer is the same with `simulated: true` and no `message_id`, nobody is written to, and the agent needs no WhatsApp number; `prod: true` sends it, from a number the agent answers WhatsApp at (`numbers` imports one with `channel: whatsapp`). A contact who asked for no more messages is refused in both: `compliance consent` says who did. What Meta refuses (a template it does not know, a number not on WhatsApp) comes back in its own words. Give `text`, the words the template says once filled, and they open the contact's conversation as its first turn: the answer carries `call`, what the contact answers lands on it with those words before it, and somebody must be holding the agent. A contact whose conversation is still open is written on it, with no template sent. With no `text` the template is said on no conversation, and what they answer opens one as any message does.

| parameter | takes | | what it is |
|---|---|---|---|
| `agent` | text | required | the agent that writes: its slug |
| `to` | text | required | the contact's number, in +E.164 |
| `template` | text | required | the template's name, as Meta approved it |
| `language` | text | required | Meta's code of the language it was approved in: `es_AR`, `en_US` |
| `variables` | a list of texts |  | what fills the body's {{1}}, {{2}}…, in order |
| `from` | text |  | which of the agent's WhatsApp numbers it leaves from; the first when left out |
| `text` | text |  | what the template says once filled: given, it is the first turn of the contact's conversation, so what they answer reaches the agent with those words before it |
| `metadata` | an object |  | what that conversation's `call.started` carries |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

## `email`

How the org's agents' emails are set: an HTML layout shown, kept, tried on words (nothing sent) or cleared back to the plain one, or text alone with no template.

`email` keeps the org's email layout: an agent answers an email in its own words and they are set in it, `{{content}}` where the reply goes, `{{subject}}` where the subject shows; with none, a plain one. `text` is for an org that wants no template: its emails go as their words alone, one text part and no HTML, until a layout is `set` or it is `clear`ed. `preview` answers the subject, the HTML and the plain part a contact would read, and sends nothing: try a layout on it before `set`. A mailbox is a carrier account (`carriers`), and its address is given to an agent with `numbers import` on the channel `email`.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `show` · `set` · `text` · `preview` · `clear` | required | show how the emails are set; set keeps html as the org's layout; text sends them as text alone, no template and no HTML; preview sets words as a reply would be, sending nothing; clear goes back to the plain layout |
| `html` | text |  | `set`, `preview`: an HTML page that says {{content}} once, where the reply goes, and {{subject}} where the subject should show |
| `text` | text |  | `preview`: the words an agent would write: paragraphs, - lists, **bold**, *italics*, links |
| `subject` | text |  | `preview`: the subject the reply answers |
| `text_only` | true or false |  | `preview`: the email as text alone, with no HTML, whatever the org keeps |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |

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

## `compliance`

The org's rules for who may be called and written to: the policy, what a contact who texts STOP or HELP is told, what stands for one number, and the do-not-call list.

`compliance policy` reads the org's rules: how long a call is kept, when and how often a number is rung, who needs a consent on file, what an outbound call opens with, and what a contact who texts STOP or HELP is told. `sms` changes that last part alone, one field at a time: `stop_reply`, `help_reply`, `stop_words` (the words of the contacts' own language, beside STOP, UNSUBSCRIBE, CANCEL, END, QUIT). A contact who texts a stop word is taken off before the model reads anything and is written to no more until they text START; that is not a setting. `consent` says what stands for one number (consented, on the list, nothing on file) with every fact about it, newest first: who stopped, when, and in which words. `dnc` lists the numbers on the list. The rest of the policy, a consent given and a number put on the list by hand stay `pinecall data` verbs a person types.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `policy` · `sms` · `consent` · `dnc` | required | policy reads the org's rules; sms sets what a contact who texts STOP or HELP is told; consent says what stands for one number; dnc lists the numbers nobody calls or writes to |
| `number` | text |  | `consent`: the number, in +E.164 |
| `stop_reply` | text |  | `sms`: the one sentence a contact is told when they are taken off; an empty string tells them nothing |
| `carrier_stop_reply` | true or false |  | `sms`: true goes back to the default — the carrier confirms a stop word, and the platform's sentence follows an opt-out the agent took |
| `help_reply` | text |  | `sms`: what a contact who texts HELP is told; an empty string leaves the word to the carrier and the agent |
| `stop_words` | a list of texts |  | `sms`: more words that stop the messages, beside the standard ones; an empty list keeps the standard ones alone |
| `after` | text |  | `dnc`: where the page before ended |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |
