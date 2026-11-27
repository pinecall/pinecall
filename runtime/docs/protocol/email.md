# Email

An agent answers email written to a mailbox of the org's own. The org brings the mailbox as an
account (IMAP to read it, SMTP to answer from it), routes its address to an agent on the channel
`email`, and the gateway reads the inbox and answers each email in the agent's words, set in the
org's HTML layout and threaded under the email it answers. Nothing points at the box: the box reads.

## The mailbox — `PUT /v1/carrier`

`{kind: "email", address, password, imap_host, smtp_host, username?, imap_port?, smtp_port?,
smtp_username?, smtp_password?, sender_name?, label?}` (`numbers`). `address` is the account's id,
lowercased. IMAP is spoken over TLS (993 unless said) and logs in as `username`, the address when
left out. SMTP is spoken over TLS from the first byte on 465 (the default) and with STARTTLS on any
other port (587); it logs in as `smtp_username` and `smtp_password` when the replies leave through a
relay with a login of its own (Amazon SES's SMTP credentials, say), and as IMAP does otherwise.
`sender_name` is the name the contact reads beside the address. Both logins are tried as the account
is kept, and a refusal is `400` in the server's words. Each host must resolve to public addresses
alone. Bringing the mailbox again with no `password` keeps the one it had, and with no
`smtp_password`, for the same `smtp_username`, the relay's: a server is changed without its
passwords typed again, and what is kept is tried with the rest. The secrets are sealed and never
read back; `GET /v1/carrier` and `/v1/carriers` answer a mailbox's `settings` (`imap_host`,
`imap_port`, `username`, `smtp_host`, `smtp_port`, `smtp_username`, `sender_name`) for a form to
show again.

## The address — `POST /v1/numbers`

`{number: "<the address>", agent, channel: "email", account?}` routes the address to the agent in
the key's environment, as a number is routed ([numbers.md](numbers.md)). The address must be the
account's own. Its path (`GET /v1/numbers/{address}/path`) says it waits for the first email, then
that emails reach the box; `DELETE /v1/numbers/{address}?channel=email` lets it go, and the inbox is
read no more. A number and an address are told apart by the `@`: every door that names a number
takes an address the same way.

## An address an app reads

`{…, app: "<the app's name>"}` on `POST /v1/numbers` (the channel `email` alone) routes the address
to an app instead of to its agent's conversations: each email is the app's event `mail.received`
([flows.md](flows.md)) and opens no call. It is `{to, from, from_name, subject, text, message_id, date}`:
the email's words read whole (quotes and all, the HTML part as text when there is no plain one; 12000
characters at most), its `Message-ID`, and its `Date` as ISO 8601 (null when it says none that reads).
Nothing is filtered but the mailbox's own emails and an empty one: a portal's notice or an order is
written by a machine, and the app's flow is what reads it (an `extract` step asks a model what it says,
and a `template` or a `text` writes to the person it names). `GET /v1/numbers` names the app of each
address that has one (`app`); bringing the address again with no `app` gives it back to its agent.

## How the inbox is read

Every gateway passes over the routed mailboxes every 20 s, and each mailbox is read by one gateway at
a time: the one whose lease on its row of `email_inboxes` runs (90 s, renewed each pass). The first
pass reads nothing and only notes where the inbox stands (its `UIDVALIDITY` and newest UID): a
mailbox routed to an agent is not made to answer its past. Each later pass fetches, oldest first, at
most 20 messages newer than the last one read, marks each read, and moves the cursor past it. An
inbox whose `UIDVALIDITY` changed is taken from where it stands the same way. A pass the server
refuses leaves the cursor where it was and writes the refusal on the row (`last_error`).

An email is not answered when nobody wrote it as a person: the mailbox's own address, a sender such
as `mailer-daemon`, `postmaster` or `no-reply`, `Auto-Submitted` other than `no` (RFC 3834),
`Precedence: bulk`, `list` or `junk`, a `List-Id` or `List-Unsubscribe`, or a blind copy. What is
read of the rest is the plain part (the HTML one, as text, when there is none), cut at the line a
client quotes the past under ("On … wrote:", "El … escribió:", Outlook's header block) and at a
signature's `-- `; attachments are not read.

## Threads and calls

An email thread is one written conversation: one contact's emails on two subjects are two. A
thread is named by its first message's id, the first of `References` (or `In-Reply-To`, or the
email's own `Message-ID`), and its key carries it (`org|env|address|contact|email|<id>`). A new
thread opens a call on the channel `email`, `medium: text`, whose `call.started` names the contact
by `caller.email` and carries `metadata: {email_thread, subject}`; it continues the contact's newest
call with the agent, on any channel, as every written call does ([whatsapp.md](whatsapp.md)). A
thread quiet for two hours is over: its next email opens a new call that carries the last one on.
An email call the contact opened greets nobody: the contact already wrote, and one email is answered
by one email, so the agent's greeting is not said and its first turn is the answer.

## The reply

Each `turn.agent` of an email call is one email to the contact, from the address written to: its
subject `Re:` and the subject answered (said once), `In-Reply-To` the email answered (the newest of
the thread), `References` the chain before it and that email, `Auto-Submitted: auto-replied`, a
`Message-ID` of the address's domain, and a `Date` (RFC 5322 requires it; every email the box sends
carries one). Its HTML is the org's layout with the reply's words set where
it says `{{content}}`; its plain part is the words alone. An org that set `text_only` has no HTML
part: the email is one `text/plain` part. The words are read for paragraphs, lists (`-`, `1.`),
`**bold**`, `*italics*`, links (`[words](https://…)` and bare addresses) and images
(`![what it shows](https://…)`, as wide as the email at most); everything else is text, escaped.
In the plain part the marks are taken off and a link's or an image's address stands beside its
words. A reply SMTP refuses is an `error` on the call, `email_not_sent`,
in the server's words. The framework's rule for the channel (`email` of `GET
/v1/studio/channel-rules`) tells the model to write the whole reply in one message.

## The agent writes first — `POST /v1/agents/{slug}/text`

The endpoint an agent texts first by ([numbers.md](numbers.md), "SMS") writes the first email when `to`
is an address: `{to, subject, text?, from?, consent?, metadata?, instruction?}` (`talk`) answers
`202 {call, agent, to, from, env}`. `from` is one of the addresses the agent answers email at in the
key's environment, the first unsaid; `to` is lowercased. `subject` is required (200 characters at
most), and refused on a number. `metadata` and `instruction` are a dial's ([numbers.md](numbers.md),
"Dialling out"): `metadata` (8 KB of JSON at most) rides the call's `call.started` beside
`email_thread` and `subject`, which win a key they share, and `instruction`, what the email is for,
is kept there as `instruction` and read by the agent for the whole conversation.

`text` is the email's words, as an SMS's are: a `say` on the call (`supervisor.verb`, by whoever
holds the key), logged as the agent's turn, and nothing greets before it. With no `text`, the agent
writes the email itself, as a dialled call with no greeting given opens: the model's first turn,
on `instruction` when there is one, else on the agent's own greeting, else on its prompt alone, with
the call's metadata in the app's view. It writes it whatever conversation the call carries on.

The email goes from the routed address through the mailbox's SMTP, set in the org's layout as a
reply is, under `subject` and a new `Message-ID` of the address's domain, with no `In-Reply-To` and
`Auto-Submitted: auto-generated`: it answers nothing, and RFC 3834 §5 names what an automatic process
writes that is no response to another message so (a contact's autoresponder still does not answer
it). That id names the thread: the call's `call.started` says it as `email_thread`, and the
contact's reply, whose `In-Reply-To` and `References` name it, lands on the same call, which the
agent answers in the thread. What the agent writes before the contact answers is a reply to its own
first email. Each address opens a thread of its own: a second email to the same contact is a second
thread.

The call is `outbound`, on the channel `email`, and carries on the contact's newest call with the
agent as an inbound email call does. It passes every guard an SMS does, on the same ledger, keyed
on the address: a stranger unless the org dials anywhere, the consent on file or given with the
request (`consent_everywhere` decides whether one is owed: the TCPA's are a phone's), the org's
calling hours, the pace and `per_number_day`. An address names no zone of its own: the hours are
kept in the agent's `timezone`, and an agent that sets none is not written to while the org keeps
calling hours (`403`, `quiet_hours`). A contact who asked for no more messages is `403`; nobody
holding the agent is `409`; an address the agent answers email at none of is `404`. An email SMTP
refuses is an `error` on the call, `email_not_sent`, as a refused reply is.

## The layout — `/v1/org/email/layout`

| door | does |
|---|---|
| `GET` | `{html, own, text_only}`: the org's layout, or the plain one (`own: false`) while it chose nothing; `text_only: true` when its emails go as text alone, `html` then the plain one, which nothing is set in |
| `PUT {html}` | keeps the org's layout; it must say `{{content}}` exactly once, and is 200,000 characters at most; `{{subject}}` is replaced wherever it is, escaped |
| `PUT {text_only: true}` | no template and no HTML: the org's emails are one `text/plain` part. `html` and `text_only` together, or neither, is `400` |
| `DELETE` | back to the plain layout; `404` when the org had chosen nothing |
| `POST /preview {text, subject?, html?, text_only?, plain?}` | `{subject, html, text}`: the words as a reply would be, set in `html`, in the plain layout with `plain`, or in what the org keeps; `html` is `null` when it goes as text alone (the org's choice, or `text_only`); nothing is sent |

All take `numbers`. An org has three ways to send with no template of its own design: nothing chosen
(the plain layout: the reply as simple HTML on white, in the reader's own font, nobody's brand, its
links and images live), `text_only` (no HTML at all), or a layout that is little more than
`{{content}}`.
