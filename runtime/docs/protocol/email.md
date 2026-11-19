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

## The reply

Each `turn.agent` of an email call is one email to the contact, from the address written to: its
subject `Re:` and the subject answered (said once), `In-Reply-To` the email answered (the newest of
the thread), `References` the chain before it and that email, `Auto-Submitted: auto-replied`, and a
`Message-ID` of the address's domain. Its HTML is the org's layout with the reply's words set where
it says `{{content}}`; its plain part is the words alone. The words are read for paragraphs, lists
(`-`, `1.`), `**bold**`, `*italics*` and links (`[words](https://…)` and bare addresses);
everything else is text, escaped. A reply SMTP refuses is an `error` on the call, `email_not_sent`,
in the server's words. The framework's rule for the channel (`email` of `GET
/v1/studio/channel-rules`) tells the model to write the whole reply in one message.

## The layout — `/v1/org/email/layout`

| door | does |
|---|---|
| `GET` | `{html, own}`: the org's layout, or the plain one (`own: false`) while it wrote none |
| `PUT {html}` | keeps the org's layout; it must say `{{content}}` exactly once, and is 200,000 characters at most; `{{subject}}` is replaced wherever it is, escaped |
| `DELETE` | back to the plain one; `404` when the org had none |
| `POST /preview {text, subject?, html?}` | `{subject, html, text}`: the words set in `html` (or the org's layout) as a reply would be; nothing is sent |

All four take `numbers`. The plain layout is the reply on white, in the reader's own font, in
nobody's brand.
