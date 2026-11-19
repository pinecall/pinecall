# Numbers — the accounts an org's numbers live in, and how a number reaches the platform

A number reaches an agent in three writes: the carrier points it at the platform, the platform admits it,
and a route says which agent answers ([telephony.md](../telephony.md) is how the three fit). The endpoints below do all three. Every one takes the org's
key with the `numbers` scope and acts in the key's environment: a `pc_live_` key imports into
production, a `pc_test_` key into the sandbox, a person's key into the environment the request names.

## The accounts — `PUT` · `GET` · `DELETE /v1/carrier`, `GET /v1/carriers`

An org holds as many accounts as it has: several Twilio accounts, a SIP peer (its own PBX or a
carrier with no API here), a WhatsApp number at Meta. Each is one row, sealed under
`PINECALL_VAULT_KEY`, named by its own id and never by its secret.

```json
{ "kind": "twilio", "account_sid": "AC…", "user": "SK…", "secret": "…", "label": "Clínica" }
{ "kind": "sip", "username": "pbx", "password": "…", "addresses": ["203.0.113.0/24"],
  "outbound_host": "sip.carrier.example", "outbound_transport": "tls" }
{ "kind": "whatsapp", "phone_number_id": "1055…", "access_token": "…", "app_secret": "…" }
```

`PUT /v1/carrier` adds an account, or replaces the secret of one the org already holds. A Twilio
account is opened once first: `user` is an API key SID (make one at Twilio → Account → API keys,
revoke it there any time) or the account SID again with the auth token, and a pair Twilio refuses
is `400 Twilio refused these credentials`. A WhatsApp number is asked of Meta the same way first
— its number and name, with the token given — and an id or a token Meta does not open is `400 Meta
does not open WhatsApp number <id> with this token: <Meta's words>`. A peer's `addresses` are the networks it calls from:
each is an IPv4 address or a network no wider than a `/24`, public (a private, shared, loopback or
documentation range is `400`), and each waits for the operator to approve it before 5060
opens to it or a trunk lists it ([operator-api.md](operator-api.md), "Carriers and the fence").
Its four `outbound_*` fields say where the platform dials it, and unsaid the platform dials with the pair it
registers with. `outbound_username` without `outbound_password` is refused.

`GET /v1/carrier` answers `{kind, account, label, networks}` (a peer's networks, each
`{network, state}`: `waiting`, `approved` or `refused`) for the org's only account, or the one
`?account=` names; with several and none named it is `409` naming them. `GET /v1/carriers` is every
one of them. `DELETE /v1/carrier` forgets an account; its numbers stay routed until each is let go.

From a terminal the same four endpoints are `pinecall carriers` — `add twilio|sip|whatsapp` with each
secret read on stdin, `list`, `show`, `drop` — and from the console they are **Numbers ▸ Add a
number** and **Accounts** ([pinecall carriers](https://docs.pinecall.io/cli/carriers/)).

An agent answers at as many numbers as the org routes to it: phone numbers from any of its
accounts, hooked by the org or bought by the platform, and WhatsApp numbers, each one row. A call the
agent places is shown as one of them, and dials through the account that number lives in.

## What the accounts own — `GET /v1/numbers/available`

`{kind, numbers: [{number, name, imported, account}]}`: every number every Twilio account of the
org owns, all of Twilio's pages, and whether this environment imported it. A SIP peer owns what it owns
and nobody here can list it: `{kind: "sip", numbers: []}`, and its import takes the number typed.

## Importing one — `POST /v1/numbers {number, agent, channel?, account?, hooked?, networks?, move?}`

Two ways to hook a number, both through this endpoint:

- **We hook it** (the default): the number is one of an account of the org. On Twilio the platform
  finds the account's trunk that points at it (by its origination URI,
  `sip:<the world's SIP name>:5060;transport=udp`, whatever the trunk is named), makes one if there is
  none, and attaches the number. On a SIP peer nothing outside is touched. With several accounts,
  `account` says which.
- **You hook it** (`hooked: true`): the org points the number at the platform itself, from any
  carrier or PBX: `sip:+59829000000@<the world's SIP name>:5060` (`PINECALL_SIP_DOMAIN` or
  `PINECALL_SANDBOX_SIP_DOMAIN`, else the platform's name, [the-environment.md](../the-environment.md)).
  Nothing outside is touched. The platform
  admits the number from the networks of the carrier named in `via`, one of
  `GET /v1/carriers/catalog` (Twilio's when unsaid), or from `networks` of the org's own, which
  wait for the operator's approval like a peer's: until then the number is routed and on no
  trunk, and the import's steps say so. A number hooked this way proves nothing of whose it is:
  on a deployment that sets `PINECALL_APPROVE_HOOKED`, the operator also approves the number itself
  (`POST /v1/ops/numbers/{number}/approve`, the numbers waiting listed by `GET /v1/ops/numbers`,
  operator-api.md), and until then a call to it is refused when it opens
  and its path says `waiting` at the fence. Unset (the default), it rings at once.

One org holds a number: importing a number another org holds is `409`, and the sentence names
neither the org nor its trunk.

**A number is a route a channel.** The same number answers the phone, WhatsApp and SMS at once, each its
own row: its own agent, its own environment, its own account (the Twilio account the number rings
through, the WhatsApp account at Meta it is written to). Importing a number on one channel adds or
replaces that channel's row and leaves the other as it is, trunk and rule included. Until 0.11.45 a
number was one row, and importing a phone number as WhatsApp replaced its phone route.

`GET /v1/carriers/catalog` is `{carriers: [{kind, name, how, networks}], sells, sip_domain}`: the carriers this
operator admits, `automatic` for one the platform drives through its API (Twilio), `guided` for one
whose portal the org types the address above into; `sells` says whether `POST /v1/numbers/buy`
has an account to buy on; `sip_domain` is the SIP name of the key's environment, the one a portal or a PBX
sends calls to on port 5060 (`sip:+59829000000@<sip_domain>:5060`), null on a deployment that has none.

```
$ curl -X POST https://cloud.pinecall.io/v1/numbers -H "authorization: Bearer $PINECALL_KEY" \
    -d '{"number": "+59829000000", "agent": "recepcion"}'
{"route": {"org": "org_…", "agent": "recepcion", "channel": "phone", "number": "+59829000000",
           "label": null, "env": "production", "managed": false},
 "steps": ["Twilio: a trunk sending calls to sip:sip.pinecall.io:5060;transport=udp: stands",
           "Twilio: +59829000000 attached to it: done",
           "LiveKit: trunk org_… admits +59829000000: done",
           "LiveKit: rule org_…:production sends it to fleet pinecall: done",
           "route: +59829000000 to recepcion in the production: done"],
 "dry_run": false}
```

Each step is looked up before it is written, so a second run of an interrupted import writes
nothing twice: every step says `stands`. `?dry_run=true` answers the same steps with `to do` and
writes nothing anywhere. A number lives on its environment's LiveKit, where an org has one inbound trunk
per fence (`<org>` for Twilio's networks, `<org>:<peer>` for a SIP peer, `<org>:<number>` for a
number hooked from networks of its own) and the environment's dispatch rule (`<org>:production` on
production's, `<org>:sandbox` on the sandbox's), dispatched to that environment's fleet. A number imported
in one environment that the other's own LiveKit still lists is taken off it first (`LiveKit of the
production: … off trunk …`). A trunk or a rule left listing no number is deleted, because one that
lists none takes every number.

Refusals: `404` no account, or a number the account does not own; `400` a channel with no number
or a number that is not E.164, a `channel: whatsapp` for a number that is not the one the org's WhatsApp Business account is (Meta names it), `422` a body missing `number` or `agent`; `409` several accounts and none named, a number another org's trunk
on this deployment already lists (livekit-sip refuses an INVITE two trunks list, so nothing is written),
or a number attached to another trunk of the same Twilio account — its name and where it points
are in the sentence, and `move: true` takes it off there first; `503` no `PINECALL_DOMAIN`; `502`
Twilio's own sentence.

## Buying one — `POST /v1/numbers/buy {country, area_code?, agent, channel?}`

Any org whose key holds the `numbers` scope, with an account of its own or none: a number bought on
the platform's own Twilio account, never the org's (the sealed `credentials/twilio` row of
`box_settings`, written by `PUT /v1/ops/numbers-account`, [operator-api.md](operator-api.md); `country` is two letters and `area_code`
digits, `422` otherwise, since both ride a path the platform signs), then hooked as an import and routed with
`managed: true`, in the key's environment. The `numbers` quota of that environment caps it, and is counted on
the managed numbers alone: `429` before Twilio is asked. `404` when Twilio has nothing for sale
there, `503` when the platform holds no Twilio account. `?dry_run=true` names the number it would buy
and buys nothing.

## The org's numbers — `GET /v1/numbers`, `GET /v1/numbers/{number}/path`

One row per number in the key's environment, oldest first: `{route, origin, rings, last_call_at, via,
account}`.
`route` is the number, its channel, the agent and the environment; `origin` is how the row was written —
`bought` (by the platform), `imported` (from one of the org's accounts), `hooked` (the org pointed the
number at the platform itself) or `typed` (by the operator, who can route a number into any org).
A row the org did not write is how it learns the operator did; importing the number again makes it
the org's. `via` is the catalog carrier a hooked number comes through, `account` the org's account it
lives in. `last_call_at` is when a
call to the number last reached the platform, or on a written channel a message to it (kept at most
once a minute), null when none ever did.

`rings` is what a call to it does now: `ok`, `waiting` (on its first call or message, though never a
mailbox, which the platform reads itself; or on the operator's
approval of a network, or of a number the org hooked where the platform asks for that) or `broken`
(nobody runs its agent),
read off the tables without asking any carrier. `GET /v1/numbers/{number}/path` says why: four
steps, each `{step, state, says, fix}` — the carrier (a Twilio number asks Twilio whether it is
still attached to the trunk pointed here), the fence, the environment's rule, the agent — with the worst
of them as `rings` and `last_call_at`; `404` for a number the org has not in the key's environment.

## SMS — `POST /v1/numbers {channel: "sms"}`, `POST /v1/sms/twilio/{mark}`

A number of a Twilio account answers SMS as one more route, beside its phone's and its WhatsApp's:
`POST /v1/numbers {number, agent, channel: "sms", account?}`. The account is the org's Twilio
account, or the platform's own for a number it bought (the number's phone route says so); a SIP
peer, a WhatsApp account or a number the org hooked itself is `409`/`400`: only Twilio's API points a
number's messages. The steps, shown by `?dry_run=true` like any import:

```
twilio: +14155550134's messages posted to this box: done
route: +14155550134 to front-desk in the production: done
```

The first sets the number's `SmsUrl` at Twilio to
`https://<the deployment>/v1/sms/twilio/<mark>`, whatever trunk its calls are on. A number whose
messages go to another service now (an address that is neither empty, Twilio's own placeholder nor
this one) is `409 <number>'s messages go to <url> now: … say move`, and `move: true` takes them.

**The address is the proof.** Twilio signs a webhook with the account's auth token, and an org
brings an API key, which signs nothing. So the `mark` is the vault's own on the number: Twilio is
given it by this deployment, through the account's API, and a post at any other address, or one
that names another number as written to, is `403`. A message is `POST`ed as Twilio's form (`To`,
`From`, `Body`, `MessageSid`) and answered `200` with an empty TwiML `<Response/>`, so Twilio says
nothing itself: the reply is the agent's.

From there an SMS is a conversation like WhatsApp's ([whatsapp.md](whatsapp.md), "A conversation"):
one thread a contact and number, a written call on the app that holds the agent, on the channel
`sms`; messages answered in order; quiet for two hours and it is over; a message for an agent nobody
holds waits (`message.waiting`). What differs: an SMS is neither marked read nor answered with a
typing sign; there is no 24-hour window; a reply longer than 1,600 characters goes out as several; a
reply Twilio refuses is an `error` entry `sms_not_sent`. Each reply is sent with a `StatusCallback`
(`…/{mark}/status`), and what Twilio says of it (`queued`, `sent`, `delivered`, `undelivered`,
`failed`) is a `message.status` entry on the open conversation, a failure with `Twilio error
<code>`. Text is read, and the audio of an MMS (`MediaUrl0` with an `audio/*` type): fetched at
`api.twilio.com` alone, on the account's pair, 8 MB at most, and heard as a WhatsApp voice note is,
by the conversation's own task. A format the ears cannot read is a line in the log. Any other
media is dropped. Letting the SMS route go
(`DELETE /v1/numbers/{number}?channel=sms`) empties the number's `SmsUrl` at Twilio when it is
this deployment's; a post for a number nobody routed is answered `200` and dropped.

**The agent writes first.** `POST /v1/agents/{slug}/text {to, text, from?, consent?}` (`talk`) sends the
contact one SMS as the agent: `202 {call, agent, to, from, env}`, the conversation it was said on. `from`
is one of the numbers the agent answers SMS at in the key's environment, the first unsaid; `text` is
1600 characters at most, sent as several messages when it is long. A contact whose conversation has
idle time left is written on it, as one more message. Any other is cold, and passes every guard a dial
does on one row of the same ledger ("Dialling out"): the number's shape, a stranger unless the org
dials anywhere, the consent on file or given with the request, the hours, the pace. The hours and the
pace are the calls' own, one count for both: under the TCPA a text is a call (47 CFR 64.1200), so a
contact rung twice today is not also written to past the org's `per_number_day`. A contact who
stopped the messages in writing is `403` in either environment, whatever consent the request
carries. Nobody holding the agent is `409`: what they answer would reach no app. The words are a `say`
on the call (`supervisor.verb`, by whoever holds the key), logged as the agent's turn and sent by the
conversation's own tap, so a refusal of Twilio's is the `error` a refused reply is. The new call is
`outbound`, carries on the contact's newest call with the agent as an inbound one does, and greets
nobody: the words given are its opening.

**A contact who stops.** A text that is, whole, one of `STOP`, `STOPALL`, `UNSUBSCRIBE`, `CANCEL`,
`END`, `QUIT`, `REVOKE`, `OPTOUT` (case, accents and punctuation aside), or a word the org added
(`sms_stop_words` of `PUT /v1/org/policy`), is honoured on the gateway it lands on, before any
conversation hears it: an `opt_out` fact on the org's list for that number (`contact_consents`,
its `source` "the contact texted a word that stops the messages", with the words and the call),
the open conversation ended `caller_hung_up`, and nothing asked of the model. From then on what
that contact writes is not answered and nothing is sent to it, until it texts `START`, `UNSTOP` or
`YES`, which writes an `express` consent and lifts it. A number on the list for the phone alone
(asked on a call, or added by hand) that writes is answered: the one who wrote asked for it.
What is silenced is a thread whose contact stopped in writing, checked before each reply.

A contact who asks in other words is the model's to hear: every SMS conversation carries the
platform's tool `stop_messages`, and the app's `call.opt_out` is taken on a written channel too.
Either writes the fact (`source` "the contact asked the agent, in writing"), sends the one
confirmation the rules allow, and ends the conversation `agent_hung_up`; what the model wrote
beside the call is not sent. The confirmation is the org's `sms_stop_reply`: null says nothing
after a stop word (the carrier confirms those itself, and a post that carries Twilio's `OptOutType`
is never answered here) and the platform's sentence when the agent took the contact off; `""` says
nothing ever. `sms_help_reply` answers `HELP` and `INFO` where they arrive; null leaves the word to
the carrier, and to the model.

## Letting one go, moving one — `DELETE /v1/numbers/{number}`, `PUT /v1/numbers/{number}/env`

`DELETE` removes the route and takes the number off its trunk and its org's rules on its environment's
LiveKit; the account keeps it, so nobody is un-bought by a typo. A number that answers on two
channels is named with the one meant, `?channel=phone|whatsapp`, on these two endpoints and on
`…/path`: without it they answer `409 <number> answers on phone and whatsapp: name the one meant
with ?channel=`, and nothing is let go or moved by a guess. Letting the WhatsApp route go leaves the
phone's trunk alone. `PUT …/env {env}` moves a number
into the other environment: its row, and off the old environment's LiveKit onto the new one's, trunk and rule;
the carrier is not touched. Where both environments share one LiveKit it moves between the two rules,
its trunk untouched. It is how a number tested in the sandbox goes live.

## Dialling out — `GET` · `POST /v1/carrier/outbound`, `POST /v1/agents/{slug}/dial`

The SFU keeps no outbound trunk: every leg is dialled with its trunk inline. What an account
needs is the other direction of its carrier. `POST /v1/carrier/outbound` (`?account=`,
`?dry_run=true`) makes it once: on Twilio the trunk's termination host
(`<box>-<account>.pstn.twilio.com`, one per account and platform), a credential list on that trunk,
and a credential per org on the list, its password minted here and kept sealed because Twilio
shows it once. Two orgs that brought the same account dial through one trunk, each with its own
credential. A credential this deployment made and no longer holds the password of is `409` naming it: it
is deleted in Twilio's console, then provisioned again. A SIP peer needs nothing made: it is
dialled at its `outbound_host`.

`GET /v1/carrier/outbound` is `{ready, kind, from_numbers, steps_missing, guards}`: whether the org
can place a call, one sentence per thing still missing, and the guards it dials under.

`POST /v1/agents/{slug}/dial {to, from?, log?, state?, metadata?, greeting?, instruction?}` places a call as the agent: `202 {call, agent, to,
from, env, log_token}` before anything rings. `state` is the state the agent's call opens in and `metadata`
what its `call.started` carries, as a web call's token names them: 8192 bytes of JSON each at most, since
both ride the room's dispatch. `greeting` (500 characters) is the words this call opens with, over the
agent's own greeting. `instruction` (2000) is what the call is for: it is the call's `metadata.instruction`,
which an agent's prompt carries, and with no `greeting` the model opens the call on it. `from` is one of the agent's own numbers in the key's
environment, the first unsaid; the call is dialled through the account that number lives in, and a
number the org hooked itself or the platform bought dials through none (`409`). Nobody holding the
agent is `409`: a phone would ring with no app to serve it. Every dial asked for is one row of the
org's `dials` ledger, taken or refused:

| refused when | status | lifted by |
|---|---|---|
| `to` is not E.164, has no country calling code, is a satellite or global-service range (`+870`, `+878`, `+881`, `+882`, `+883`, `+888`, `+979`), or has fewer than five national digits | `400` | a number somebody could answer |
| the number never called or wrote to this org **in this environment** | `403` | an operator's `dial_anywhere` |
| the number is on the org's **do-not-call list** in this environment (`do_not_call`): its newest fact is an opt-out — the caller asked the agent (`call.opt_out`), a person put it there, or the org imported it. A consent sent with the dial never lifts it | `403` | a consent recorded at `POST /v1/org/consents` |
| no **consent** on file for a `+1` number (`no_consent`), nor one sent with the dial as `consent: {kind: express\|written, source, text?, evidence?}`; any country when the org's policy says `consent_everywhere` | `403` | the consent, recorded or sent |
| outside the called number's hours in **every** zone it could be in (`quiet_hours`): for a `+1` number 8:00 to 21:00 local (the Telemarketing Sales Rule), narrowed by the org's `calling_hours` and never widened; elsewhere the org's `calling_hours`, when it set some. A number held to hours that has no zone (a `+1` toll-free one) is refused always | `403` | the hour |
| `per_minute` (6) dials already asked for in the last minute (`too_fast`) | `429` | a wait |
| `per_day` (200) dials already asked for in the last 24 hours (`too_many`) | `429` | a wait |
| the number itself rung `per_number_day` times in 24 hours (`too_often`): 3 for a `+1` number unless the org sets its own, none elsewhere unless it does | `429` | a wait |

The list, consent, the hours and the per-number count bind a call to somebody: the **sandbox** is
held to none of them, and neither is a number the person who asked verified as **their own phone**
(`PUT /v1/line/from`) — that is them testing. A consent sent with a dial is written down with the
call's id before anything rings, so the next call to the number needs none. The zones come from libphonenumber (`phonenumbers`); the org sets its hours
and count at `PUT /v1/org/policy` ([gateway-api.md](gateway-api.md) §7). `per_minute` and `per_day` count every row of the org's ledger, refused ones included, in both environments together; `per_number_day` counts the calls placed to that number alone. The count and the row are one transaction under the org's lock: two dials at once cannot both take
the last slot. A placed call runs at most `max_duration_s` (600), which the media plane enforces.
A far end that is busy, declines or never answers ends the call `busy` or `no_answer`; anything
else, `dial_failed`.

A leg dialled into a live call (a warm transfer, `room.invite`) asks
`GET /v1/agents/{slug}/outbound-trunk?to=&call=&from=`, the worker's: the shape and the pace, not
the stranger fence, and the trunk inline in the answer. A cold transfer asks
`POST /v1/agents/{slug}/cold-transfer?to=&call=` before it sends the caller on: the same guards and
the same ledger row, and no trunk, since the carrier dials a REFER on the org's own bill; a
refusal leaves the caller where they are, `call.transferred` with `ok: false`.

## The firewall

livekit-sip listens on 5060, and the cloud's firewall in front of it opens it to the signalling
networks of the carriers the operator admits and to the addresses he approved, and to nothing
else: Terraform's rule, from the catalog and the approvals ([operator-api.md](operator-api.md)).

## Reconcile at start

LiveKit keeps its trunks and rules in Redis, which can be emptied; the tables are the truth. At
start the gateway admits every routed phone number again on its environment's LiveKit with its fence and
its environment's rule, and takes it off the other environment's own LiveKit, one org's refusal logged and the
others going on; while an org is refused or a LiveKit cannot be reached (one still starting beside
the gateway), it tries the whole again, waiting 2 s, then twice as long each time, a minute at
most, until every number stands. It never touches the carrier, and it takes a number
off its org's trunks when nothing approved fences it any more. The operator's approval or refusal
of a network does the same for that org at once. Where the sandbox has a LiveKit of its own, the
start also admits there the rings production hands to a developer's own sandbox copy: one trunk
and one rule named `hand-over`, the trunk listing no number and admitting production's media
address alone, with its pair ([telephony.md](../telephony.md), "A developer's own phone").


## Consent and the do-not-call list

Every fact about a number is a row, never changed: a consent given (`express` or `written`, where it
came from, the words the person agreed to, a proof) or an opt-out, by whom and on which call. What
stands is the newest row, so a person who opted out and later consented is called again, and the
history of both is kept. An erasure of the contact leaves these rows: an opt-out has to outlive the
person's data, or the next list the org imports calls them again.

| endpoint | scope | what |
|---|---|---|
| `POST /v1/org/consents {number, kind, source, text?, evidence?}` | talk | one fact written; what stands for the number after |
| `GET /v1/org/consents/{number}` | calls | `{number, standing: consented\|opted_out\|unknown, rows}`, newest first |
| `DELETE /v1/org/consents/{number}` | talk | the number put on the list: an opt-out written, the history kept |
| `GET /v1/org/dnc?after=` | calls | the numbers whose newest fact is an opt-out, newest first, `next` for the page after |
| `POST /v1/org/dnc {numbers, source}` | talk | the org's own list, or its scrub of the National Do Not Call Registry, onto the list at once: `{added, refused}` |

The runtime does not query the National Registry: its subscription is the seller's by law. The org
scrubs and imports what it found.
