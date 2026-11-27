# Messenger and Instagram

An agent answers what is written to a Facebook Page of the org's own, on Messenger, and to the
Instagram professional account linked to that Page. Both are Meta's Messenger Platform: the org
brings the Page as an account with its own Meta app's secret, routes the Page's id to an agent on the
channel `messenger` and the Instagram account's id on `instagram`, and Meta delivers every message to
the box's webhook, signed by the org's app. The agent only answers: nothing on these channels opens a
conversation the contact did not start.

## The Page — `PUT /v1/carrier`

`{kind: "messenger", page_id, access_token, app_secret, instagram_id?, label?}` (`numbers`). `page_id`
is the account's id; `access_token` a Page access token of the org's Meta app: the dashboard's
(Messenger ▸ Messenger API Settings ▸ Generate access tokens) carries `pages_messaging` alone and
answers Messenger, and Instagram takes one with `instagram_basic` and `instagram_manage_messages`, made in
the Graph API Explorer (docs.pinecall.io/integrations/messenger-and-instagram/, step 4); `app_secret` the app's secret (App settings ▸ Basic), which signs
every body Meta delivers for the Page and its Instagram account; `instagram_id` the Instagram
professional account linked to the Page. As the Page is kept the gateway checks the token opens the
Page's conversations (a refusal is `400` in Meta's words) and subscribes the Page to the app for
`messages`, `messaging_postbacks`, `message_deliveries` and `message_reads`. The dashboard's token reads
nothing of the Page: the Instagram account is the
one the org says, and the account is named by its `label`. A token that may read the Page
(`pages_read_engagement`) has Meta name both, and Meta's word wins. Bringing the Page again with a new
token alone keeps its secret and its Instagram account. `GET /v1/carrier` and `/v1/carriers` answer a
Page's `settings.instagram_id`.

The webhook is the one WhatsApp's is (`GET /v1/whatsapp/subscription` says its callback URL and verify
token), and the gateway gives it to the app itself as the Page is kept: with the app's own token (its
id, read off the Page token, and its secret) it subscribes the app's `page` object to `messages`,
`messaging_postbacks`, `message_deliveries` and `message_reads` at that callback, and its `instagram`
object to `messages`, `messaging_postbacks` and `messaging_seen` when the Page has an Instagram
account. Verifying the callback in Meta's dashboard alone chooses no field, and Meta then delivers
nothing.

## The Page and its Instagram account — `POST /v1/numbers`

`{number: "<the Page's id>", agent, channel: "messenger", account: "<the Page's id>"}` and
`{number: "<the Instagram account's id>", agent, channel: "instagram", account: "<the Page's id>"}`
route each to an agent in the key's environment, as a number is routed ([numbers.md](numbers.md)).
`account` is required (a Page is never hooked), and the id must be the Page's own on Messenger and
its linked account's on Instagram. Every door that names a number takes these ids with
`?channel=messenger` or `?channel=instagram`; its path says it waits for the first message, then that
messages reach the box.

## A message

A body Meta signs for a Page is `{"object": "page", "entry": [{"id": "<Page>", "messaging": [...]}]}`,
and for its Instagram account `{"object": "instagram", ...}` under the account's id. Only an org's own
app signs these: the box's app answers no Page. Each `messaging` event of a contact's is one message:
its `message.text`, the title of a button they tapped (`postback`), or a voice note, whose audio Meta
links to and is heard as WhatsApp's is. Our own sends come back as echoes (`is_echo`) and are not read;
`delivery` and `read` events become `message.status` on the conversation, as WhatsApp's receipts do.

The contact is Meta's id of them on that account (a PSID on Messenger, an IGSID on Instagram), said as
the caller `messenger:<id>` or `instagram:<id>`: never a phone number. Their name is asked of the Page
once, when their conversation opens (`first_name last_name` on Messenger, `name` on Instagram); one Meta
does not give leaves them unnamed. A conversation is one per contact and account, open while it has
idle time left, and a contact who writes again is carried on as on WhatsApp.

## A reply

The agent's words are sent from the Page with its token, `POST /{page_id}/messages` with
`messaging_type: RESPONSE`, to Messenger or to the Instagram account alike, cut in parts under Meta's
ceilings (2000 characters on Messenger, 1000 on Instagram). Each message is marked seen, and "typing…"
is shown while the model writes. Meta takes a response within 24 hours of the contact's last message
(up to 7 days after an ad that opened the conversation); past them it refuses, the refusal is in the
log in Meta's words, and nothing is retried with a message tag.

## What Meta asks of the org

The Page and the Instagram account belong to the org's own Meta app, as its WhatsApp number does. The
app needs `pages_messaging` and `pages_manage_metadata`, `instagram_basic` and
`instagram_manage_messages` for Instagram, and `pages_read_engagement` for Meta to name the Page and its
Instagram account by itself; the Instagram account must be professional, linked to the
Page, with "Allow access to messages" on. While the app is in development, Meta delivers only the
messages of people with a role on it; answering the public takes Advanced Access, after Meta's App
Review and the business's verification.
