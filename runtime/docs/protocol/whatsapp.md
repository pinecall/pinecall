# WhatsApp — Meta's webhook, one conversation per contact

A WhatsApp number answers like a phone number: a route of channel `whatsapp` says which agent,
and a conversation is a written call on the app that holds that agent, in the route's environment.

## Whose Meta app delivers a number's messages

A WhatsApp number lives in a Meta app, and Meta delivers that number's messages to the webhook of
that app, signed with that app's secret. Two apps are known to a deployment:

- **An org's own.** An org that made its Meta app brings the number as an account with the app's
  secret (`PUT /v1/carrier {"kind": "whatsapp", "phone_number_id", "access_token", "app_secret"}`,
  [numbers.md](numbers.md)). Replies to its contacts go out on its token, and a body is taken for
  that number when it carries the signature of that secret. Bringing the account again with no
  `app_secret` keeps the one it had: a token is renewed far more often than an app changes.
- **The platform's.** One Meta app of the operator's, for numbers that live in it. Its secret, its
  handshake word and a token replies go out on are the sealed row `credentials/whatsapp` of
  `box_settings`: `{app_secret, verify_token, access_token?}`. An account brought with no
  `app_secret` is a number of this app. A deployment without the row answers no number of its own;
  its orgs' own apps still subscribe.

```
console → Numbers → Add a number → WhatsApp
  {"number": "+59829000000", "agent": "recepcion", "channel": "whatsapp", "account": "1055…"}
```

The number a WhatsApp account answers at is asked of Meta: `GET /v1/numbers/available` lists it
beside the Twilio numbers, with the account it lives in, and `POST /v1/numbers {number, agent,
channel: "whatsapp", account}` routes it. A token Meta refuses (a temporary one expires in a day;
a system user's does not) leaves the account listed with no number, said in the gateway's log.

## What an org types in its Meta app — `GET /v1/whatsapp/subscription`

The scope `numbers`. `200 {callback_url, verify_token, field}`: the address of the webhook below at
the deployment's public name, the word the org's app subscribes with, and the one webhook field to
subscribe to (`messages`). The word is `<org id>.<mark>`, the mark being the vault's own on the org:
the gateway knows it again and stores nothing. It is typed once, in the app's WhatsApp ▸
Configuration; an app already subscribed is asked nothing when the vault's key changes.

## The webhook — `GET` · `POST /v1/whatsapp/webhook`

`GET` is Meta subscribing: `hub.mode=subscribe` and a `hub.verify_token` that is the word given to
an org, or the platform's own (each compared in constant time), echo `hub.challenge` back as plain
text; any other word is `403`.

`POST` is a delivery. The signature (`X-Hub-Signature-256: sha256=<HMAC-SHA256 of the raw
body>`) is checked on the bytes as they came. A body the platform's app signed is taken whole. Any
other is read for the phone number ids it names and for nothing else (eight at most: an org's app
serves a handful), and the accounts under those ids that brought an `app_secret` are tried: a
message is taken when the secret of its own number's account signed the body, and only for a route
of that account's org through that account. So an org's secret vouches for its numbers and for no
other, whatever the body says the number written to is. A body no known app signed is `403`. Past
the signature the answer is `200 {received: n}`, because Meta disables a webhook that keeps failing:
a delivery receipt, an image, a number nobody routed are a line in the log and nothing else.

Meta delivers a message again when it thinks it unanswered, for up to 7 days, and each message is
read once. Its id is claimed per org (`whatsapp_seen`) before it is read, and the claim is the
insert itself, so of two deliveries at once, to one gateway or two, one reads it; a later delivery
of a message read is `200` and dropped. A message is read once it is on its conversation's queue
or kept for nobody (below). A reading that fails gives the claim back and the delivery is `500`,
so Meta's next one reads it; a delivery that arrives while another is still reading it is `503`,
so Meta keeps it until that reading is done; a claim a process died holding is read again by the
first delivery ten minutes after it. The nightly retention run forgets the ids past 7 days.

## What is read, and what the contact sees

A text is read as it was written; a tap on a reply button, a row of a list or a template's quick
reply as the words on it. A voice note is fetched from Meta on the number's token (8 MB at most) and
heard by the ears the org's calls hear with, on the same keys, with no language named: what it says
is the message. A note for an open conversation is heard by the conversation's own task, never
inside the webhook's request; one for an agent nobody holds is heard as it arrives, since what waits
is kept as its words. An image, a sticker, a document, a location are dropped and said in the log.

As a message is taken up it is marked read at Meta (`status: read`: the contact's two blue ticks),
and with `typing_indicator` when the model is about to be asked, which shows "typing…" until the
reply goes out or 25 seconds pass. With a person on the line (a supervisor's takeover) it is marked
read alone. A refusal of either is a line in the log: the message is answered all the same. A reply
longer than the 4,096 characters Meta takes goes out as several, cut at a paragraph, a line or a
word.

Meta then says where each reply stands, in bodies that carry `statuses` and no message: `sent`,
`delivered`, `read`, or `failed` with its reason. Each is a durable `message.status` entry on the
contact's open conversation, `{message_id, status, to, error}`
([events-control.md](../wire/events-control.md)), written by the gateway that holds the
conversation: one that lands on another gateway is handed to it, once. A receipt is vouched for as a
message is, so one an org's own app signed is said on that org's number alone. A receipt for a
conversation that went quiet is dropped: its log is sealed.

## A conversation

Each message goes onto its contact's conversation, keyed by the org, the environment, the number and the
contact, and messages are answered one at a time, in order. The first opens a written call on the
socket holding the agent; the next ones stay on it. Every durable `turn.agent` of that call — the
model's, the agent's `say`, a supervisor's — goes to the contact through Meta's Graph API, and a
send Meta refuses is an `error` entry `whatsapp_not_sent` on the call's own log.

A conversation quiet for two hours is over: its call ends `timeout` and the next message opens a
new one. That new call carries on the contact's newest call with the agent, on whatever channel
(`continues` on its `call.started`): it opens on the turns of that call and of those it carried on
itself, ten calls back at most, and greets nobody. A conversation that comes back within the two
hours is taken up on its own call, the newest on its own channel. Two hours is under Meta's 24-hour customer-service window, which only that close keeps. A
turn past the org's quota ends the conversation unanswered. A gateway that restarts takes up a
conversation that still had idle time left, from its log, with its history.

## The agent writes first — `POST /v1/agents/{slug}/template`

Outside the 24-hour window Meta lets a business write only a **template** it approved, and it is the
one message Meta charges for, on the account of whoever owns the number. A key with `talk` sends one
as the agent:

```http
POST /v1/agents/front-desk/template
{"to": "+5491155550134", "template": "visit_request", "language": "es_AR", "variables": ["Marta", "Friday at 11"],
 "text": "Hola Marta, recibimos tu consulta. ¿Coordinamos una visita el viernes a las 11?", "metadata": {"listing": 2821756}}
```

`202 {agent, to, from, env, template, simulated, message_id, call}`. `variables` fill the body's `{{1}}`,
`{{2}}`… in order; `from` names the number it leaves from when the agent answers WhatsApp at
several. It is sent from the number's own account on the org's token, and `message_id` is Meta's id
of the message.

**`text` puts it on the contact's conversation.** It is what the template says once filled, which
only the caller knows: Meta keeps the template's body. Given, those words are the first turn of an
outbound WhatsApp call of the contact's (`call` in the answer), whose `call.started` carries
`metadata` as a text's does. What the contact answers lands on that call, with those words before
it, so a "sí" is read as the answer it is; the console's thread shows the message; and a
conversation that went quiet is carried on by the contact's next one, as any is. The template goes
to Meta first, so its refusal opens nothing, and the turn itself is sent by nobody. A contact whose
conversation still has idle time left wrote inside the 24 hours: the words are said on it as one
more message, no template is sent, and `message_id` is `null`. Somebody must be holding the agent
(`409` otherwise). With no `text` the template is said on no conversation, `call` is `null`, and
what the contact answers opens a call as any message does. Until 2026-11-26 that was the only way,
and an agent knew what it had asked a contact only by what its app kept.

**The sandbox sends nothing.** There the answer is the same with `simulated: true` and no
`message_id`: Meta is not asked, nobody is written to, nothing is charged. An agent's goldens hand a
conversation over dozens of times a run, and each of those would be a paid message on a real
person's phone. An agent with no WhatsApp number in the sandbox is answered so with no conversation
(`call: null`); one that has a number there has its conversation opened on `text` as in production,
with nothing sent. An app sends its templates through this door, in both environments, and holds no
token of Meta's.

Refused before anything is sent: `400` for a number that is not `+`, the country's code and the
number; `403` for a contact who asked for no more messages, in either environment; in production,
`404` when the agent answers WhatsApp at no number and `409` when that number has no account of the
org's to send from. What Meta refuses (a template it does not know, a number not on WhatsApp) is a
`502` in its own words.

The same send is the CLI's `pinecall template <agent> <name> --to <number> --language <code> [--var …]
[--text …]` (`cli/docs/the-cli.md`, "`template`"), the MCP server's tool `template`, the console's
**Write first with a template** on a WhatsApp number's page, and a flow's step
(`step.template(to, Agent, name, { language, variables, text })` in the three SDKs; [flows.md](flows.md),
kind `template`). A hosted app that is in no flow asks the door itself, with the `PINECALL_URL` and
`PINECALL_KEY` it is started with. No row is kept of a template sent with no `text`: the answer is
the record, and an app writes it on its call's log.

## Nobody holding the agent

A message whose agent no app holds waits on the agent's own log (`message.waiting`). The moment an
app declares the agent, what waited is answered, oldest first, and taken off the queue
(`message.taken` naming the call). A message older than the 24-hour window is taken off with no
call. A gateway that starts reads the queue back off the logs.

## The desk

The console's Calls ▸ Threads (`/v1/agents/{slug}/threads`) shows every contact of an agent, their calls merged into
one thread. A person with `talk` writes on the open conversation with
`POST /v1/agents/{slug}/threads/{contact}/messages {text}`: `202 {contact, call}`, sent as the
agent. `409` when the contact's newest call is not WhatsApp, when the window closed, or when the
conversation went quiet and is sealed. A supervisor's `takeover` on the call holds it: the
contact's messages are kept on the log and the model is not asked until `release`; `end` ends the
conversation and the log says a supervisor did.
