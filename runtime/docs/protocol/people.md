# People — how a person gets a key, what a key is, and the org's people

A person has one key per device, minted when they sign in, and it acts as them: the scopes of
their role, the org they signed into, and the environment each request names (`pinecall-env`, the
sandbox when unsaid; production only with production access, read from their row on every
request). It is kept while it is used: minted with thirty days to live, given thirty again by each
use, and `401 this sign-in ended at …` once thirty days pass with none, when that device signs in
again. A server has a token of its own, made by a person for one environment, with the date it was
made with or none. The endpoints below mint,
list and stop both, and manage the people they belong to. Every refusal is `{"detail": "…"}` with
its status; a key, a password or a link is in exactly one answer, the one that made it.

## Before a key — `GET /.well-known/pinecall`

No key. What a sign-in page reads first:

```json
{"version": "0.1.1", "signup": false, "min_password": 8, "mail": true,
 "brand": {"name": "Pinecall", "logo_url": null, "accent": "#5b3df5"}, "google": false,
 "turnstile": null}
```

`signup` is `PINECALL_SIGNUP`, and the console shows its sign-up only where it is true;
`min_password` is `PINECALL_MIN_PASSWORD` (0 is no rule); `mail`
says whether the platform itself can post a letter (an org's own mailbox is not counted), so the page
knows whether "Forgot your password?" can promise one; `brand` is the platform's. `turnstile` is
Cloudflare Turnstile's site key where the operator set one (`PINECALL_TURNSTILE_SITE_KEY`): the page
draws the widget and a sign-up, its resend and a forgotten password below carry the token it yields
as `turnstile`; the gateway verifies it with Cloudflare for that door, on this platform's name, and
refuses `403 the captcha was not passed` without it, as it does when Cloudflare does not answer.
`null`, and no door asks for one. A password never carries one: a phone, a terminal and a console
served from somewhere else type passwords too, and none can draw Cloudflare's widget, so the
password doors stand on the throttle below instead. `google` is whether the platform keeps a
Google client ([the-box.md](the-box.md)): the page draws "Continue with Google" where it is true.

## Who a key is — `GET /v1/whoami`

Any key. The org as an id and as the slug people type, the key's id and label, the environment this
request acts in, its scopes, whose it is, and whether it may act in production:

```json
{"org": "org_…", "slug": "clinica-norte", "key_id": "k_…", "label": "ana-laptop",
 "env": "sandbox", "scopes": ["app", "calls", …], "subject": "m_…", "name": "Ana García",
 "email": "ana@clinica.test", "operator": false, "visiting": false, "production": true}
```

`email` is the one name a person carries into every org; a server's token has none. `operator`
says the person runs the platform; `visiting` that they are inside an org they are no member of.
Never the key nor its hash. With no key it is `401 this endpoint takes an API key`; with one that
opens nothing — revoked, mistyped, another deployment's — `401 this key opens nothing here`, which
says to sign in again or mint a new one, and never which of the three it was.

## Your own account — `GET /v1/me`

A person's key, in an org they are a member of; a server's token and an operator's visit are `403`.
What the console's User settings reads and writes:

```json
{"id": "m_…", "email": "ana@clinica.test", "name": "Ana García", "role": "admin",
 "verified": true, "has_password": true}
```

`PATCH /v1/me {name}` changes what this org calls the person, on their seat and on the keys they
hold; another org of theirs keeps the name it gave them. `PUT /v1/me/password {current, password}`
changes their one password: `204`, and every other key of theirs is revoked, in every org, while
the one that asked goes on. The current password is what proves the person, never the key alone, so
a stolen key cannot keep the account: a wrong one is `403 that is not your current password` and is
counted with the tries of a sign-in (below), a new one under `min_password` is `400`, and somebody
with no password (`has_password` false: they only ever signed in through Google or their org's
provider) is `409` and sets one through the link of a forgotten password. `GET /v1/me/keys` lists
the live keys their own sign-ins to this org left, the latest used first, as
`{fingerprint, label, created_at, last_used_at, current}`: `current` is the key of this request, and
any of them is stopped with `POST /v1/keys/{fingerprint}/revoke`. `POST /v1/me/keys/revoke` stops
every one of them but the key that asked, `{revoked: n}`, from the next request on. The address is
not changed here.

## Signing in — `POST /v1/login`

No key. The body says one of two things, and a body with both or neither is `400`:

```json
{"email": "ana@clinica.test", "password": "…", "org": "clinica-norte", "device": "phone", "turnstile": "…"}
{"code": "lc_…", "device": "chrome"}
```

A password gives a key of that person's in the org named, or, unnamed, the first org the password
opens. A wrong address, a wrong password and a wrong org are one sentence, `401 nobody answers to
that email and password`, and cost the same time. Only once the password matched does the endpoint say
more: `403` a member disabled, `403` an org that signs in with its provider only (naming
`/v1/login/sso?org=…`), `403` somebody invited who has not chosen a password. `device` labels the
key in the org's list, so it is revoked on its own.

Every address is five tries a minute from one place, whatever the password: the sixth is
`429 too many attempts for …: try again in a minute`. A password is also twenty tries a minute from
one place across every address, and twenty at one address from wherever — a list of addresses tried
from one machine, or one address tried from many, meets the same sentence as a person who mistyped —
and the sentence never says which count it was. The same counts hold `POST /v1/login/orgs`; the
five a minute alone hold `POST /v1/login/reset` and `POST /v1/login/sso/discover`. Behind the
platform's own Caddy the place is the person's address. A code is never counted, being one use and
minted by a page already signed in, and no password door asks for a Turnstile token.

A code gives a copy of the key that minted it: the same org, environment, scopes and person, revoked
when it is, labelled `console` unless `device` says. A server's copy dies on its date; a person's is
a sign-in of its own, kept its thirty days from each use. A code is spent once and lives five minutes;
spent, dead or invented it is `404`. Every endpoint that mints a key answers the same shape, the key
this once:

```json
{"key": "pc_live_…", "key_id": "k_…", "org": "org_…", "label": "phone", "env": "production",
 "scopes": [...], "subject": "m_…", "name": "Ana García"}
```

A person's key starts `pc_live_` and opens both environments.

`POST /v1/login/codes`, with any key, mints `{code, expires_at}`: a browser signs in with it, so a
key never rides a URL. A server's key gives the browser a copy of itself, and revoking a key
revokes every copy made of it, and every copy of those. `POST /v1/login/orgs {email, password}` lists the orgs a password opens,
`{orgs: [{org, slug, name, role}]}`, minting nothing.

## Another org — `GET /v1/login/orgs`, `POST /v1/login/org {org}`

A person's key. The list is every org of the person, oldest first, with `role`, `status`, whether
this key is the one opening it (`here`) and `member: true`. A person who runs the platform also sees
every other org, `member: false` and `role: "operator"`. The switch mints the same person's key in
another org of theirs; switching to one where they are still `invited` takes the seat (a proven
address and a password elsewhere; an org that signs in only with its provider seats nobody this
way). A person who runs the platform enters any org as a visit, with an admin's scopes and no seat. A
server's token names nobody and is refused both.

## A terminal — `/v1/login/pairings`

`pinecall login` asks `POST /v1/login/pairings {device}` for a word, `{code: "cli_…",
expires_at}`, and opens `/cli?c=<word>` in a browser. The page reads `GET
/v1/login/pairings/{code}` (`{device, expires_at, answered}`, spending nothing) and a signed-in
person approves with `POST /v1/login/pairings/{code}` (`{device, org, org_name}`, the org by its
id and by the name the page says it signed in to): the terminal gets a key of its own, for the
same person, labelled with its `device` and dying with the browser's key. The terminal asks `GET
/v1/login/pairings/{code}/key?wait_s=25`, which the gateway holds until a browser approves (up to 25 s, the most it holds): `202 {}` when the wait ran out with nobody approved, `{key}` once, `404` after. Without `wait_s` it answers at once. A word
lives ten minutes; one collected, dead or invented is the same `404`, and a second approval `409`.

## An app connected as you — `/v1/oauth/…`

An assistant (Claude, ChatGPT, an editor) that reaches Pinecall through an MCP server is signed in
the way a terminal is, a browser approving it, with OAuth 2.1's words so that any of them does it
unaided. The gateway is the authorization server; the token it gives is a key of the person's, the
same kind a terminal gets. It keeps no table for any of it: a registration is its own id, a code is
a one-use secret, the key is a row of the keys.

`GET /.well-known/oauth-authorization-server`, no key, read by any page (RFC 8414):

```json
{"issuer": "https://cloud.pinecall.io",
 "authorization_endpoint": "https://cloud.pinecall.io/connect",
 "token_endpoint": "https://cloud.pinecall.io/v1/oauth/token",
 "registration_endpoint": "https://cloud.pinecall.io/v1/oauth/register",
 "revocation_endpoint": "https://cloud.pinecall.io/v1/oauth/revoke",
 "response_types_supported": ["code"], "grant_types_supported": ["authorization_code"],
 "token_endpoint_auth_methods_supported": ["none"], "code_challenge_methods_supported": ["S256"],
 "scopes_supported": ["pinecall"], "client_id_metadata_document_supported": true,
 "authorization_response_iss_parameter_supported": true}
```

**Who the app is.** Its `client_id` is one of two things. An `https` address is a Client ID
Metadata Document: the gateway fetches it (a name that resolves onto the internet alone, asked at
the address checked, 64 KiB at most) and takes its `client_name` and `redirect_uris` when the
document's own `client_id` is that address. Or the app registers, `POST /v1/oauth/register
{client_name, redirect_uris}` with no key (RFC 7591; whatever else it says of itself is ignored):
`201 {client_id: "pcc_…", client_name, redirect_uris, token_endpoint_auth_method: "none", …}`. The id
is the registration itself, sealed under the vault, so nothing is kept and a stranger registering a
million writes nothing. Either way an app names one to ten addresses it may be sent back to:
`https` anywhere, `http` on the person's own machine alone (`127.0.0.1`, `localhost`, `::1`, at any
port of the one registered), or the app's own scheme (`cursor://…`); never `javascript:`, `data:`
or `file:`, never one with a fragment. Anything else is `400` `invalid_redirect_uri`; an id that is
neither kind, or a registration this gateway never sealed, `400` `invalid_client`.

**The approval.** The app sends the person's browser to `/connect` with OAuth's parameters
(`response_type=code`, `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method=S256`,
`state`; `scope` and `resource` are accepted and change nothing). That is the console's page: it
signs the person in first if it must, then asks `GET /v1/oauth/authorization?client_id=…&redirect_uri=…&code_challenge=…`
with the person's key, which checks all three and answers what the page shows, `{client_name,
redirect_host}`. On **Connect** the page posts `POST /v1/oauth/authorization {client_id,
redirect_uri, code_challenge, code_challenge_method, state, org}` with the person's key (`org` is
another org of theirs, when they chose one): the gateway mints a key for that person in that org,
labelled with the app's name, keeps it sealed under a one-use code that lives five minutes, and
answers `{redirect, org}`, the app's address with `code`, `state` and `iss` added to its query. The
page sends the browser there. A server's token is `403`: an app is connected as a person. A person
who says no is sent back with `error=access_denied` by the page itself.

**The exchange.** `POST /v1/oauth/token`, a form, no key (RFC 6749 section 4.1.3):
`grant_type=authorization_code`, `code`, `code_verifier`, `client_id`, and `redirect_uri` when the
app sends it. The verifier's SHA-256 must be the challenge the code was approved with, and the
`client_id` the one it was given to:

```json
{"access_token": "pk_…", "token_type": "Bearer", "scope": "pinecall"}
```

answered once, `Cache-Control: no-store`. The key is a sign-in like any other of the person's: it
opens what their role opens, in both envs by the `pinecall-env` header, is listed with their other
sign-ins (`GET /v1/me/keys`), and is kept thirty days from its last use. So there is no refresh
token and no `expires_in`: an app that goes a month unused is answered `401` and asks the person
again. A refusal carries OAuth's words beside the sentence, `{"detail": …, "error": "invalid_grant",
"error_description": …}`, always `400`: `invalid_grant` for a code spent, expired, another app's or
not this verifier's (a wrong guess leaves the code to its own app), `invalid_request` for a field
missing or a challenge that is not `S256`, `unsupported_grant_type` for any other grant.

**The end.** `POST /v1/oauth/revoke`, a form with `token`, no key (RFC 7009): the key opens nothing
from then on; `200 {}` whatever the token was. The person ends it too, where they end any sign-in.

A page of the app's own may post the three forms from any origin (no credentials are involved, and
the gateway answers `Access-Control-Allow-Origin: *` there); every other endpoint keeps to the
origins the box allows.

## A forgotten password — `POST /v1/login/reset {email, turnstile}`

No key. Always `202 {}`, for an address known or not (`403` first where the platform has Turnstile
and the token is missing or refused: nothing is mailed, and nothing is said of the address). Where the person is active in an org that
signs in with passwords, one letter goes, through the platform's own mailbox and never an org's, with
a one-use link to `/invitations/<token>`; the link proves the address, so the password it sets is
the person's one, in every org. A member still invited gets none, since their invitation is the
link. A deployment with no mailbox mints nothing, so a link an admin handed over is never spent by a
letter that cannot go.

## An invitation — `POST /v1/invitations/{token} {password, device}`

No key: the token is the credential, and lives a week. The password is set for the person in
every org they are in (one password per person), the member is active, and the answer is the key
shape above with `member` beside it. A token spent, dead or invented is one `404`; a password
under `min_password` is `400`.

## The org's people — `/v1/members`

`team`. `GET` lists every member, oldest first, the disabled too:

```json
{"id": "m_…", "email": "ana@clinica.test", "name": "Ana", "role": "developer", "agents": [],
 "status": "active", "scopes": [...], "operator": false, "production": false, "verified": true}
```

`POST {email, name, role, agents, production}` invites, `201 {member, token, expires_at, mailed, link}`,
within the org's `seats` (`429` past them). The invitation is mailed where a mailbox can post it;
`mailed` says it was queued. The token is handed to the admin only when the address is in no other
org: the link sets the person's one password, so for somebody known elsewhere it is mailed only,
and `token` is `null`. Nobody is seated by being named: the member is `invited` until the person
takes the seat, by the link, or, proven elsewhere and with a password, by opening the org
(`POST /v1/login/org`, or a sign-in that names it). A sign-in that names no org never takes an
invitation. An address already a member is `409`.

A key grants only what it holds: a manager invites a `qa` and is refused an `admin` (`403` naming
what the key opens), and production access only by somebody who has it.

`agents` is the agents the member works on; an empty list is every agent of the org, and every
member starts with one. A person's key whose list is not empty is refused, `403` naming the list,
at every endpoint that names an agent outside it: in its path (`/v1/agents/{slug}/…`), as `?agent=`, in
its body (a token, a code, a number routed, an eval run or voiced, a call opened, a callback), in
`WS /v1/chat?agent=` and a socket's `agent.register`, and at a call's own endpoints (its events, state,
recording, settings, seats, verbs, judging, erasure) by the agent the call was of. An endpoint that
names no agent (`/v1/agents`, `/v1/sessions` without `?agent=`, `/v1/events`) is not narrowed by
it. A server's token holds no list, and a visit to another org is not bound by the list of the
visitor's own.

`PATCH /v1/members/{id} {role?, agents?, status?, production?}` changes what is named. Nobody
changes their own role or production switch, or disables themselves (`409`); an admin always opens
production (`409` taking it away); an invited member becomes active only by accepting (`400`).
Disabling revokes every key of theirs at once; the rows stay, since the log names who did what.
`DELETE /v1/members/{id}` takes a member out for good, keys revoked, seat freed, `204`; never
yourself and never the org's last active admin (`409`). `POST /v1/members/{id}/reset` is an
admin's one-use link for an active member, handed and mailed as an invitation is; `409` for
anybody not active. `PUT /v1/members/{id}/password {password}` sets the member's password with no
link, the box's floor held (`400` under it): an invited member becomes active, a disabled one is
`409`; the answer is the member's row, never the password.

## The org's keys — `/v1/keys`

`GET` with any key lists by fingerprint every server's token and the asker's own person keys;
a key with `keys` sees every person's too. Never a key:

```json
{"fingerprint": "…", "label": "clinica web", "kind": "server", "env": "production",
 "name": null, "created_by": "Ana", "created_at": "…", "last_used_at": null,
 "revoked_at": null, "scopes": ["app", "calls", "evals", "knowledge", "talk"]}
```

`POST {label, env, scopes?, expires_at?}` with a person's key that opens `app` makes a server's
token for one environment, `pc_live_` or `pc_test_`, answered once; a production token only by somebody
with production access. It opens `app`, `calls`, `talk`, `knowledge` and `evals`, or, with
`scopes`, only the ones named of those (`400` for any other, or none). With `expires_at`, a moment
to come with its offset, it opens nothing from then on and every endpoint answers `401 this key
expired at …`; without it, it never expires. The listing carries each key's `expires_at`. `POST /v1/keys/{fingerprint}/revoke`
stops your own key, a token you made, or any with `keys`; anything else, revoked or not the org's
is one `404`. The row stays.

## Sign-up — `/v1/signup`

Shut unless the operator sets `PINECALL_SIGNUP` (`404` naming it); the console's `/signup` is the
page that knocks, and it shows itself only where `/.well-known/pinecall` says `signup` is true.
Every self-hosted gateway serves that page, which is why the switch is the gateway's and not the
page's. The address counted is the request's own, behind the trusted proxies.

`POST {org, name, email, person, password, device, turnstile}` keeps the sign-up and mails six digits:
`202 {email, code_expires_at}`, never the code, and no org yet. `org` is the slug; left out, the
slug is made of `name` (accents dropped, lowercase words joined by dashes), so a page never derives
one — a sign-up with neither is `400`. A deployment that cannot mail takes
none (`503`), and one with Turnstile refuses `403` a token missing or refused, before anything is
counted. Every address is answered alike, so the endpoint says nobody whether one has an
account: an address with a password signs up with it, and with another is mailed that it has an
account instead of a code; one invited somewhere is mailed to accept that first. A slug taken is
`409`. `POST /v1/signup/verify {email, code}` makes
the org, allowed what the platform's admission gives a newborn org, its admin active, and answers
`201` with the key shape plus `slug`, `member`, and a login `code` for the console; the console
keeps the key and opens the sandbox on it. A code lives
15 minutes and six tries; a wrong, burned or expired code is `400` in its words, and an address
nobody signed up with reads as a wrong code. `POST /v1/signup/resend {email, turnstile}` mails a new code
and kills the first; `202 {}` whoever asks.

## Continue with Google — `/v1/login/google`, `/v1/signup/google`

Where the operator keeps a Google client, `GET /v1/login/google?pairing=` is `302` to Google with
a state, a nonce and a PKCE challenge, asking which of the person's Google accounts; none kept is
`404`. The callback exchanges the code and checks the id_token as an org's provider's is checked
(the issuer, the audience, the nonce), and refuses an address Google has not verified. Then:

- **the address is a member somewhere**: it signs in to the oldest org it took, else the oldest it
  was invited to — seated, Google having proved the address — passing over an org that signs in
  only with its own provider; `302` to `/?login=<code>`, or `/cli?c=<word>&login=<code>` when a
  terminal waits. A password the person also has stays theirs: either way in opens the same account;
- **nobody knows it, and sign-ups are open**: `302` to `/signup?google=<token>` (and `&c=<word>`
  for a terminal), a one-use token that lives ten minutes. `GET /v1/signup/google/{token}` reads
  `{email, person}` spending nothing; `POST /v1/signup/google {token, name, org?, device}` makes the
  org as a mailed code's sign-up does — `201`, the same shape — with no password and no code: the
  admin signs in through Google, or chooses a password with a reset. A slug taken is `409` and keeps
  the token, to pick another; an address let in elsewhere since is `409`; a dead token `404`;
- **sign-ups are shut**: `302` to `/?refused=<why>`, as every refusal at the callback is; a closed
  Google page is "the sign-in with Google was not finished".

No password and no Turnstile token at either: Google vouched for the address, and the token was
minted by the callback. Both count against the place's sign-in throttle.

## The org's provider — `/v1/org/sso`, `/v1/login/sso`

`team`. `PUT /v1/org/sso {issuer, client_id, client_secret, domains, role?, required}` keeps the
org's OpenID provider after its issuer answered its discovery (an issuer that is not https never
reaches the network, nor one whose name resolves to nothing or to any address that is not
public, before each request; one that does not answer is `400`, nothing kept). The secret goes in and
never comes out; `role` seats an uninvited address of the domains with that role, and counts as
granted by the key. `GET` answers `{configured, issuer, client_id, domains, role, required,
redirect_uri, proofs}`, the URI to register at the provider. `DELETE` lets passwords in again.

A domain is the org's word until it proves it: each one in `proofs` is `{domain, txt, verified}`,
and the org publishes `txt` (`pinecall-verify=<token>`) as a TXT record at the domain, then asks
`POST /v1/org/sso/domains/{domain}/verify`, which reads the record now and answers the proof
verified (`400` saying what is at the domain instead, `404` for a domain the SSO does not name).
Until a domain is verified, discovery offers the provider to nobody of it and the callback seats
nobody of it: an org naming a domain that is not its own sends none of that domain's people to
its provider. A record once seen stands. `required: true` is `409` until one domain is verified,
or nobody could sign in. The domains declared before this proof existed read verified.

`GET /v1/login/sso?org=&pairing=` is `302` to the provider with a state, a nonce and a PKCE
challenge; an org unknown or without a provider is the same `404`. The callback exchanges the
code, checks the id_token (the issuer, the audience, the nonce, a verified address of the org's
domains), seats the person and is `302` to `/?login=<code>`, or `/cli?c=<word>&login=<code>` when
a terminal waits; any refusal there is `302` to `/?refused=<why>`, and only a state nobody began
is `400`. No key is ever in a URL. `POST /v1/login/sso/discover {email}` names the orgs whose
provider signs in that address's domain, among the domains they proved, and nothing about who
exists.

## The org's mailbox — `/v1/org/mail`

`team`. `PUT {host, port, security, username, password, from}` keeps the SMTP account the org's
letters go out through before the platform's: a server on the internet, reached over TLS (`security`
is `starttls` or `tls`; `none` is `400`, the platform's own relay alone). Every address its name
resolves to must be public: one inside the platform's network, or a name that resolves to nothing, is
never reached, and the letter's error says so. It sends nothing. `GET` answers `{configured, host, port, security, username, from, verified_at,
last_error}`, never the password, and `DELETE` goes back to the box's. `POST /v1/org/mail/test
{to}` sends one letter and waits: `{sent, error}` with what the server said, `409` when nothing
can send.

## The platform — `GET /v1/ops/whoami`

The operator's key, or a person the platform made an operator: `{operator: true, version, domain,
name, org}`, `name` and `org` null for the platform's own key. The console draws its Box screens when
this answers `200`.
