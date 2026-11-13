# Pinecall widget

A web component that puts a Pinecall agent on any page: a button that opens a chat straight away,
with a voice call from the browser one tap away in the panel's header, and — when the page offers
it — **Call us**, a call from the visitor's own phone that shows up live in the panel. The agent can
draw on the screen: choices, cards, products with an add-to-cart, a form it fills as the visitor
speaks. Plain JavaScript modules, no build step, no framework dependency.

It is served by your gateway at `https://<gateway>/widget/pinecall-widget.js`, and by jsDelivr from
the public repository at `https://cdn.jsdelivr.net/gh/pinecall/pinecall@main/widget/pinecall-widget.js`.
`pinecall-widget.js` imports the modules beside it (`styles.js`, `texts.js`, `cards.js`, …) by
relative path, so they are served from the same folder.

```html
<script type="module" src="https://cloud.pinecall.io/widget/pinecall-widget.js"></script>
<pinecall-widget agent="pip" name="Pip" company="Brightside Dental" token-url="/pinecall/token"></pinecall-widget>
```

A fuller one, with everything a site can turn on:

```html
<pinecall-widget agent="pip" name="Pip" company="Brightside Dental" tagline="books your cleaning"
                 lang="en" greeting="Hi, I'm Pip. Shall I find you a time for a cleaning?"
                 token-url="/pinecall/token" code-url="/pinecall/code" dictation-url="/pinecall/dictation"
                 position="bottom-right" theme="auto" text-add-to-cart="Book it">
</pinecall-widget>
<style>
  pinecall-widget { --pc-accent: #0f766e; --pc-accent-soft: #eef7f5; --pc-radius: 12px; }
</style>
```

## The panel

The button opens the panel and a chat in it at once; the agent's greeting comes first (`greeting`
stands in for it until the agent's own first words take its place). While the agent thinks, three
dots wait where its answer will be; its words are then typed out at a reading pace, and what it
shows on screen comes after them, so the answer is read first.

The header holds three things: the call, a menu, and **×**.

- **The call**: a voice call in the browser, a call of its own with the chat's lines still on screen
  and its cart carried over; its hang-up button comes back to the chat, which carries the voice call
  on in writing. Or, with `phone` or `code-url`, **Call us**. With both, a small menu under the
  button asks which.
- **The menu** (⋯), what a visitor does now and then:
  - **New conversation**: the conversation under way ends, and a new one opens.
  - **Your conversations**, while there is a conversation from before to read again.
  - **The theme**, light or dark, unless the page forced a `theme`.
  - **Maximize** (not on a phone, not `inline`).

Closing the panel is not hanging up, and neither is the page going away (a reload, a link to another
page of the site, a tab closed): the conversation waits **30 seconds**, and the next open carries it on
where it was, on this page or another, its resume token kept in this browser. Past that the call
ends, and the next open is a new conversation with the lines of the one before still on screen. A
visitor whose line dropped is waited for five minutes. **New conversation** is hanging up: said at
the gateway's door with the call's own token, the call ends at once (and so does carrying another
conversation on in its place).

The panel is the visitor's to size: they drag its edges or its corner, double-click the corner to
reset, or maximize it (Escape restores); the size they leave is kept in this browser. On a phone
(520px wide or less) the panel is the whole visible screen, the keyboard shrinks it, and the page
under it holds still. When the page routes a link of its own that the visitor tapped in the
conversation ([`pinecall:ui`](#events)), the chat steps aside on a phone, and the agent's newest line
waits over the button until it is tapped.

With `dictation-url` (or a `dictationProvider`), the field has a microphone: the visitor's words are written in as they speak,
greyed while they are still being heard; they can edit and send, and a pause of four seconds sends
them. On a voice call the microphone is the call's, and dictation steps aside.

## The tag

Attributes are read once when the element connects, except `token-url`, which is read for every
token. Use one tag per agent; several can share a page.

| attribute | | |
|---|---|---|
| `agent` | required | the agent's slug, as `pinecall start` prints it |
| `token-url` | required, unless `tokenProvider` is set | your token endpoint ([below](#token-url)) |
| `name` | optional | what the agent is called on screen (its initial is the avatar), `Assistant` when left out |
| `company` | optional | whose agent it is, under the name |
| `tagline` | optional | the line under the name, after the company |
| `lang` | optional | the language of the widget's own words: `en` (default) or `es`. The agent answers in whatever language the visitor speaks either way. Dictation is asked for in this language |
| `text-<key>` | optional | any one of the widget's words, in place of the language's ([below](#the-words)): `text-add-to-cart="Book it"` |
| `greeting` | optional | the agent's first line, shown the moment the panel opens and replaced by the agent's own first words; plain text |
| `label` | optional | the button's text, beside its icon. Without it the button is a round icon, and the label (`Talk to <name>`) is its accessible name |
| `icon` | optional | `none` leaves the button without its icon (and so shows its label) |
| `button` | optional | `none` draws no button at all: open the panel with `toggle()` from anything of yours |
| `position` | optional | `bottom-right` (default), `bottom-left`, `top-right`, `top-left`, or `inline`: the button right where the tag is, in the page's own flow |
| `theme` | optional | `auto` (default: follows `prefers-color-scheme`, and the visitor may switch it from the header, their choice kept in this browser), `light` or `dark` (forced, no switch) |
| `autostart` | optional | the opening click starts a voice call directly, the microphone asked inside it; refused, the chat opens with the reason |
| `call` | optional | `off` takes the browser voice call away (and `autostart` with it) |
| `phone` | optional | the number **Call us** shows when there is no `code-url` ([below](#call-us)) |
| `code-url` | optional | your code endpoint: **Call us** shows the number and a 4-digit code that ties the phone call to this page ([below](#code-url)) |
| `log-url` | optional | your log relay: with `phone` and no code, **Call us** follows the agent's live phone call, with a **Show tools** toggle ([below](#log-url)) |
| `gateway` | optional | gateway origin for codes, their calls' logs and hang-ups; defaults to the script's origin (`cloud.pinecall.io` for the jsDelivr copy) |
| `dictation-url` | optional | your dictation endpoint: the field gets a microphone ([below](#dictation-url)) |
| `dictation` | optional | `off` takes dictation away even with a `dictation-url` |
| `history` | optional | `off` keeps nothing in this browser. By default the conversation under way survives a reload, and the visitor's last 20 conversations with this agent are kept ([below](#your-conversations)) |
| `look` | optional | `dot`: the button is a face that speaks with the agent's voice, and a click is a voice call with no panel ([below](#the-talking-dot)) |
| `tutor` | optional | **experimental**, with `look="dot"`: the dot walks the visitor through the page with a pointer of its own ([below](#the-dot-as-a-tutor)) |
| `walks` | optional | with `tutor`: a button beside the dot plays the agent's recorded walks with no call; `walks="sandbox"` reads the sandbox's |
| `ask` | optional | with `tutor`: the site's door, a path of its own server, for what the visitor types in the walks' menu |
| `shape` · `color` | optional | with `look="dot"`: the face's shape, `circle` (default), `squircle` or `blob`, and its colour, any CSS colour (else `--pc-accent`) |
| `captions` | optional | with `tutor`: whose words show in writing, `both` (default), `agent`, `caller` or `none` |

| property | |
|---|---|
| `tokenProvider` | `(scope, agent, resume) => Promise<token JSON>`, in place of `token-url` |
| `dictationProvider` | `(language) => Promise<{ url, hear? }>`, in place of `dictation-url`: the field gets its microphone |
| `codeProvider` | `(agent) => Promise<code JSON>`, in place of `code-url` |
| `texts` | `{ key: "words" }`: any of the widget's words, over `lang`'s and the `text-*` attributes; it can be set at any time |
| `views` | with `tutor`: `{ toolName: (host, result, tools) => … }`, the page's own cards for the results of the agent's tools |

| method | |
|---|---|
| `toggle()` | opens the panel, or closes it when open |
| `talk()` | opens the panel straight into a voice call in the browser: a page's own "Talk" button; a microphone refused leaves the chat |
| `event(name, data)` | tells the agent what the visitor did on the page ([below](#telling-the-agent-what-the-visitor-does)); rejects while no conversation is open |

## Your endpoints

The org's API key stays on your server, which exposes these endpoints; the widget sends the
agent's slug with each request, so one set of endpoints serves every agent (reject slugs your site
doesn't serve). Use a production key with the `talk` scope (tokens, codes, dictation) and `calls`
(logs), sent as `Authorization: Bearer <key>`.

### On an app's own page

A page Pinecall serves for an app (`app.page("site")`) has no server of yours. Its doors,
`/pinecall/token` and `/pinecall/code`, are Pinecall's: they ask for a captcha first and take no
agent's name, so `token-url` cannot point at them. Give the tag its tickets with `hosted()` of
`@pinecall/room`, which speaks to them, on the deployed page and under `pinecall start` alike:

```html
<pinecall-widget agent="riley" name="Riley"></pinecall-widget>
<script type="module">
  import { hosted } from "https://cdn.jsdelivr.net/npm/@pinecall/room@0.11/+esm";
  const doors = hosted();
  const widget = document.querySelector("pinecall-widget");
  widget.tokenProvider = (scope, _agent, resume) => doors.tokens(scope, resume);
  widget.dictationProvider = (language) => doors.dictation(language);
</script>
```

Set them before the widget's own script runs (a plain `<script>` above it, with `import()` inside):
a conversation kept from before opens as the page loads, and asks for its ticket then.

### `token-url`

The widget sends:

```http
POST <token-url>
Content-Type: application/json

{ "agent": "<slug>", "scope": "talk" | "chat", "resume": "<resume_token>" }
```

`chat` when the panel opens, `talk` for a voice call; `resume` when the visitor carries a
conversation on. Your server posts to Pinecall:

```http
POST https://<gateway>/v1/tokens
Authorization: Bearer <key>
Content-Type: application/json

{ "agent": "<slug>", "scope": "talk" | "chat", "ttl_s": 120, "metadata": { … }, "resume": "<as sent>" }
```

Return Pinecall's response unchanged: `201` with
`{ "server_url", "participant_token", "call", "log_token", "resume_token" }` (`log_token` says the
call's hang-up at the gateway's door and opens no room; `resume_token` is what the widget keeps to
carry the conversation on). Pass `resume` on as it came: only your key can spend it. When the gateway
no longer takes a resume, the widget asks again without it and keeps the lines on screen.
`ttl_s` defaults to 60; a longer one is cut to a day (86400). `metadata` is sealed into the call: the
agent reads it as `this.call.metadata`, and the browser cannot alter it. Errors come as
`{ "detail": "…" }` (`404` unknown agent, `429` quota spent, `503` fleet full); pass them through and
the widget shows `detail`. `room_name`, `participant_name` and `participant_metadata` are rejected
with `400`.

Instead of `token-url`, set the element's `tokenProvider`:

```js
document.querySelector("pinecall-widget").tokenProvider = (scope, agent, resume) =>
  fetch("/my/mint", { method: "POST", body: JSON.stringify({ scope, agent, resume }) }).then((r) => r.json());
```

### `dictation-url`

Turns dictation on. When the visitor taps the microphone, the widget starts recording and sends:

```http
POST <dictation-url>?language=<lang>
```

Your server asks Pinecall for a one-stream token, with the words it writes its own way (`hear`, any
number; the vendor `stt` and `model` are optional):

```http
POST https://<gateway>/v1/transcriptions/token?language=en&hear=Brightside&hear=Pip&stt=<vendor>
Authorization: Bearer <key>
```

and answers `200` with `{ "url": "wss://<gateway><path>", "hear": [ … ] }`, `url` the gateway's
answer's `path` on the gateway's `wss` origin, and `hear` the same words, which the widget then writes
as the site spells them whatever the ears made of them. The browser opens that socket itself and
sends the microphone as raw 16 kHz 16-bit PCM, then `end`; the socket answers `{type: "interim" |
"final", text}` as it hears, then `{type: "done"}`. Errors as `{ "detail": "…" }`, shown to the visitor.

### `code-url`

Links a phone call to the page: **Call us** shows the agent's number and a 4-digit code; the caller
keys or says it when the agent asks, and the panel then follows that call only. The widget sends
`POST <code-url>` with `{ "agent": "<slug>" }`, and your server posts the same to
`https://<gateway>/v1/codes` with a key that has the `talk` scope.

Return the response unchanged: `201` with `{ "code", "number", "expires_at", "code_token" }`. The
agent needs a phone number (`pinecall numbers import`), otherwise `409`. A code lasts 10 minutes
(`ttl_s`, 60–1800). The browser then talks to the gateway directly: it polls
`GET /v1/codes/{code}?wait=1` with the code token and, once a call claims the code, reads that
call's log with the returned log token. Both are credential-less cross-origin `GET`s, so there is
nothing to relay. Or no endpoint: set `codeProvider`.

### `log-url`

For **Call us** with `phone` and no code: two `GET` queries, both with `agent` added to whatever
query string `log-url` already has.

**`<log-url>?agent=<slug>&list=1`** — the agent's latest telephone calls. The widget polls it once a
second while **Call us** is open, and expects `200` with:

```json
{ "calls": [ { "call": "call_…", "live": true, "from": "···169", "started_at": 1789000000.5 } ] }
```

Your server reads `GET https://<gateway>/v1/agents/<slug>/sessions?limit=30` (newest first), keeps
only the rows with `channel == "phone"`, and answers those four fields of each. `started_at` is Unix
seconds; the widget shows the call that is `live`, or a call that started after **Call us** was
opened. `from` is printed on the page as it comes, and the page is public: cut the caller's number to
its last three digits.

**`<log-url>?agent=<slug>&call=<id>`** — one call's log, live, as server-sent events. Your server relays

```http
GET https://<gateway>/v1/calls/<id>/events?types=call.started,user.transcript,agent.transcript,turn.user,turn.agent,tool.call,tool.result,call.ended&after=0
Authorization: Bearer <key>
Accept: text/event-stream
```

and streams the answer back byte for byte as `text/event-stream`, flushing every chunk, with
`Cache-Control: no-cache` and buffering off (`X-Accel-Buffering: no` behind nginx). Each frame is
`id: <seq>` · `event: <type>` · `data: <JSON>`, the entry's payload in the JSON's `data`. Check that
`<id>` is a call id before putting it in the URL.

The browser's own chats and voice calls never read `log-url`: their lines come over the room.

## Call us

With `phone`, `code-url` or `codeProvider`, the header's call button offers a call from the
visitor's phone. It opens over the conversation:

- **With a code**: step 1, the number and a **Call** button (a `tel:` link); step 2, the four digits
  to key, any time during the call; a pulsing "Waiting for your call…" and the code's time left.
  The moment the code is keyed, the call's lines show there live, the agent's words as its voice says
  them. An expired code offers a new one.
- **With `phone` alone**: the number and its **Call** button; with `log-url`, the live call follows
  under it, its tool calls behind **Show tools** (the choice kept in this browser).

The back arrow returns to the chat; the phone call goes on, it is the visitor's phone that hangs up.

## Your conversations

The conversation under way is kept in this browser with its resume token, its lines (at most 200)
and its cart, so a page change, a reload or a closed tab brought back carries it on. A visitor back
within five minutes is the same call, which waited for them; later, Pinecall opens a new call whose
agent reads what was said. Either way it stays one conversation.

The ones before it — after **New conversation**, or a dot's call that ended — are kept too, the last 20, and the
menu lists them under **Your conversations**: the first thing the visitor said, a chat or a
call, when. A tap reads one again as it was; **Carry on this conversation** (when the gateway gave it
a resume token) ends the one under way and takes this one up as a chat; the bin deletes it, and
**Clear** deletes them all. The lines are this browser's alone, so a shared computer is a reason to set
`history="off"`, which keeps nothing, not even the conversation under way across a reload.

## The words

Every word the widget says is a key of its texts table, in `texts.js`, in English (`en`) and Spanish
(`es`); `lang` picks the table. A site changes any of them two ways, the property winning:

```html
<pinecall-widget agent="pip" name="Pip" text-add-to-cart="Book it" text-tap-hint="Tap one to book it"></pinecall-widget>
```

```js
document.querySelector("pinecall-widget").texts = { addToCart: "Book it", soldOut: "Fully booked" };
```

`{name}` and `{company}` in a text are the tag's own; the other placeholders are filled where the
text is shown. The keys, with their English words:

| area | keys |
|---|---|
| the button and the header | `assistant` (the name when `name` is left out), `open` "Talk to {name}", `close`, `call` "Call {name}", `hangUpToChat`, `more` "More", `fresh` "New conversation", `maximize`, `restore`, `resize`, `toLight` "Light theme", `toDark` "Dark theme" |
| the conversation | `write` "Write to {name}…", `send`, `typing` "{name} is typing…", `connecting`, `reconnecting`, `live` "Online", `listening` "{name} is listening", `ended`, `tapToHear`, `micRefused`, `failed` |
| dictation | `dictate`, `stopDictating`, `hearing` "Listening…", `dictationFailed` |
| products | `addToCart` "Add to cart", `pickSize`, `sizes` "Sizes {sizes}", `added` "Added to cart", `notAdded`, `tapHint`, `soldOut` |
| the form | `formSent`, `formUpdate`, `required` |
| your conversations | `history` "Your conversations", `clear`, `backToChat`, `carryOn`, `forget`, `aCall`, `aChat`, `callWord`, `chatWord`, `endedWord`, `justNow`, `minAgo` "{n} min ago", `hAgo` "{n} h ago" |
| call us | `talkHere`, `talkHereSub`, `callUs` "Call us", `callUsSub`, `callUsByCode`, `callName` "Call {name}", `dial`, `keyCode`, `anyTime`, `theCode` "the code: {digits}", `showsHere`, `waiting`, `expiresIn` "expires in {left}", `codeExpired`, `newCode`, `gettingCode`, `onTheLine`, `callTheNumber`, `yourCall`, `callFrom` "☎ a call from {who}", `endedWhy` "— ended: {why}", `showTools` |
| the dot | `hangUp`, `captions`, `walks`, `stop`, `pause`, `back`, `next`, `more`, `ask`, `askAgent`, `looking`, `notHere`, `forAgent` |

## The look

Ink, cream and thin rules, corners barely rounded, the page's own font. Every colour is a custom
property on the tag, and one the page sets wins in either theme — set it under
`pinecall-widget[theme="dark"]` or a `prefers-color-scheme` query to give a theme its own:

```css
pinecall-widget {
  --pc-accent: #1a1917;       /* the button, her bubbles, the send, what is chosen */
  --pc-on-accent: #fff;       /* text and icons on the accent */
  --pc-accent-soft: #f6efe2;  /* the agent's bubbles, the field, the form's card */
  --pc-ink: #1a1917;          /* the text */
  --pc-muted: #6f6a63;        /* the second line of text */
  --pc-line: #e7e2da;         /* the rules and borders */
  --pc-surface: #fff;         /* the panel */
  --pc-header-bg: #faf8f5;    /* the header */
  --pc-radius: 4px;           /* the panel's corners, the photos, the cards */
  --pc-offset: 20px;          /* the distance from the page's edge */
  --pc-font: inherit;         /* the page's own */
  --pc-font-size: 15px;
  --pc-z: 2147483000;
  --pc-writing-opacity: .6;   /* a line still being written or heard; 1 shows it at full strength from its first word */
  --pc-panel-width: 400px;    /* the size a panel opens at */
  --pc-panel-height: 640px;
}
pinecall-widget::part(panel) { box-shadow: none; }   /* the panel, outright */
```

The values above are the defaults of the light theme. The dark one is the same look turned over:
a warm near-black panel, cream text and a cream accent with dark ink on it.

## The button

The button is yours to style, as far as you want to take it. Four ways, from a colour to a
launcher of your own:

```css
/* 1. Its own custom properties, in either theme */
pinecall-widget {
  --pc-button-bg: #111;            /* default: --pc-accent */
  --pc-button-ink: #fff;           /* default: --pc-on-accent */
  --pc-button-border: 1px solid #333;
  --pc-button-radius: 10px;        /* default 999px: round, or a pill with a label */
  --pc-button-padding: 0 22px;     /* default 0, and 0 22px 0 18px with a label */
  --pc-button-shadow: none;        /* default 0 4px 16px rgba(0,0,0,.2) */
  --pc-button-weight: 500;
  --pc-button-font-size: 16px;
}

/* 2. Anything CSS can say, through its parts */
pinecall-widget::part(button) { text-transform: uppercase; letter-spacing: .08em; }
pinecall-widget::part(button-icon) { color: #facc15; }
pinecall-widget::part(button-label) { font-style: italic; }
```

3. `label="Talk to Pip"` writes beside the icon, and `icon="none"` takes the icon away.

4. Your own element, in place of the button: give the tag a child with `slot="button"`. It is your
markup in your page, styled by your CSS like any other element, and a click on it opens the panel
(`autostart` included). With `button="none"` there is no button at all, and anything of yours opens
the panel with `toggle()`.

```html
<pinecall-widget agent="pip" name="Pip" token-url="/pinecall/token">
  <a slot="button" class="my-cta" href="#">Talk to us now</a>
</pinecall-widget>
```

## What the agent can show

The agent puts things on the visitor's screen with `this.call.send("pinecall.ui", data)`, drawn in
the conversation after the words it says with them. On a voice call they come a moment after it
starts speaking.

- `{ type: "choices", text?, options: [{ label, value? }] }` draws buttons; the one tapped is the
  visitor's next line (`value`, else `label`).
- `{ type: "html", html }` draws a card. Only text, lists, tables, `https` links, `https` images and
  code are kept; scripts and styles never run. A link to another site opens in a new tab; a link of
  the page's own site is handed to the page first ([Events](#events)). The agent's own lines are
  read as the little Markdown a model writes: `**bold**`, `*italics*`, lists and `https` links.
- `{ type: "products", items: [{ name, color?, price?, sizes?, image?, large?, url? }] }` deals a
  row of up to six product cards, one by one: the photo (`image`, https), the name and colour, the
  price as it is written, and the sizes left. A tap shows the photo large (`large`, else `image`)
  over the chat, its sizes to pick and **Add to cart**, which sends the agent the event `cart.add`
  `{ name, color, size }` and closes. `sizes: []` is sold out; an item with no `sizes` has none, and
  adds without one. A newer row in the same answer replaces the one waiting.
- `{ type: "form", event, id?, title?, note?, submit?, fields }` draws a form. `fields` are
  `{ name, label, type: "text" | "tel" | "email" | "choice", value?, required?, autocomplete?,
  half?, shownFor? }`; a `choice` has `options: [{ value, label, detail?, needs? }]`, and a field
  with `shownFor: "<choice>"` shows only when the option picked there `needs` it by name. Two
  `half` fields in a row sit side by side. Sent, it is the event named `event` with `{ name: value }`
  of every field shown; the visitor can correct it and send it again.
- `{ type: "form-fill", id, values: { name: value } }` writes what the visitor said into the form
  with that `id`, each field lit for a moment for them to check.
- `{ type: "cart", lines }` draws nothing: the conversation keeps `lines` as its cart, and a new
  call that follows one that ended gets it back as the event `cart.restored` `{ lines }`.

## Telling the agent what the visitor does

`event(name, data)` on the tag tells the agent what the visitor did on the page: the page they
opened, the plan they chose, their cart. The agent's `onEvent(name, data)` runs when its class
accepts that name from a participant, and the runtime drops any other. A state field the hook writes
is in the agent's view at its next turn, so the prompt follows the page, and the hook can `reply()`
at once.

```js
const widget = document.querySelector("pinecall-widget");
widget.addEventListener("pinecall:started", () => widget.event("page.viewed", { path: location.pathname }));
pricing.addEventListener("click", () => widget.event("plan.chosen", { plan: "pro" }).catch(() => undefined));
```

An event sent as the conversation opens waits until the agent listens (its first snapshot of the call, eight seconds at most), so a page may say what it is on `pinecall:started`. It rejects when no call or chat is open. The widget itself sends `call.spoken` `{ spoken: true }`
when a voice call starts, so the agent speaks for the ear, and `cart.add`, `cart.restored` and a
form's event as above. Anybody can send what a browser sends: keep `data` to values the agent's view
reads, never words the model is told to obey.

## Events

| event | `detail` | when |
|---|---|---|
| `pinecall:open` | | the panel opens |
| `pinecall:close` | | the panel closes (the conversation waits) |
| `pinecall:started` | `{ call, scope }` | a chat or a voice call has joined; a voice call from the chat, a **New conversation** or a carry-on is a new one |
| `pinecall:ended` | `{ call }` | it left |
| `pinecall:ui` | `{ action: "open", url }` | the visitor tapped a link of the page's own site in the conversation (`url` is its path and query). The event is cancelable: a page that routes it itself (a single-page app) calls `preventDefault()`, and the widget then leaves the link to it and, on a phone, steps aside. Not cancelled, the link opens in this tab and the conversation carries on on the next page |
| `pinecall:ui` | what the agent sent | with `look="dot"`: a card or choices the dot cannot draw |
| `pinecall:walk` | `{ walk, step, of, done }` | with `tutor`: a walk starts and ends |

```js
widget.addEventListener("pinecall:ui", (event) => {
  if (event.detail.action !== "open") return;
  event.preventDefault();
  router.navigate(event.detail.url);
});
```

## The talking dot

`look="dot"` turns the button into a small face (a dot with eyes and a mouth) that speaks with the
agent's voice. A click starts a voice call at once, with no panel. While the agent speaks, a bubble
above the dot lights each word as it is said, and the line stays a moment after the reply ends.
The face rests, listens and thinks with the agent's state. A click during the call offers
**Hang up**. A refused microphone, or a token your server refused, opens the panel with the reason.
The call is kept under **Your conversations** like any other.

```html
<pinecall-widget agent="pip" name="Pip" look="dot" token-url="/pinecall/token"></pinecall-widget>
```

The dot is `pinecall-dot.js`, loaded only for this look; it stands on
[`@pinecall/room`](../packages/room/README.md) and [`@pinecall/dot`](../packages/dot/README.md), both
from jsDelivr. It reads the call's log straight from `gateway` with the call's own token. Its size is
`--pc-dot-size` (64px by default), its colour `--pc-accent`, and its parts `button-face` and `bubble`.
What the agent shows with `pinecall.ui` has no room on a dot: the tag dispatches it as `pinecall:ui`.

## The dot as a tutor

> The dot and its tutor are an experiment of Pinecall: their attributes may change in any release.

`look="dot" tutor` makes the dot one more person on the page. The agent points at what it talks
about with a pointer of its own, highlights it, scrolls to it and shows where to click, and it
never sends a form or opens another page for the visitor; it fills a form's fields with what
the visitor tells it, and they press its button. The one button it presses is one a walk names: a
search, or a button outside any form. Its prompt reads the page as it is now, sent by the page each
time it changes. The agent extends `Tutor` from `@pinecall/dot/agent`, and its walks are macros in
its folder ([@pinecall/dot](../packages/dot/README.md#the-tutor-in-the-agent)).

```html
<pinecall-widget agent="pip" name="Pip" look="dot" tutor token-url="/pinecall/token"></pinecall-widget>
```

During a call, two buttons sit beside the dot's corner: **CC**, which turns the written words on
and off (off until the visitor turns them on, the choice kept in this browser), and **✕**, which
hangs up. The agent's words show beside the dot as its voice says them; the visitor's, what the
agent heard, show in the corner as they speak and a moment after, one side at a time. `captions`
says which may show.

With `walks`, a small button beside the dot fans out the agent's walks; a pick plays one in the
agent's voice, the pointer moving on its words, with no call and no microphone; captions, pause and
stop sit in the corner while it plays. A section with `data-pinecall-walk="<macro>"` names its walk:
the menu marks the one of the section the visitor is on when it opens; a button of the site's own
with `data-pinecall-play="<macro>"` and `hidden` is shown while that walk can play, and plays it. The
page's own `widget.views = { toolName: (host, result, tools) => … }` draws the results of the agent's
tools on a card above the dot; `tools.send(text)` says something to the agent as the visitor.

With `ask="/pinecall/ask"`, a path of the site's own server, the walks' menu has a field: "Ask me to
show you…". What the visitor types there is answered by that path with `@pinecall/dot/server`'s
`answer()` ([Typing to the dot](../packages/dot/README.md#typing-to-the-dot-one-thing-done-never-a-conversation)):
a walk played with the params it takes picked out of what they wrote, a thing shown, or **Ask the
agent**, which starts a call with it written in.

## In React, Vue, Svelte

A custom element is an element: render the tag and it works.

```jsx
// React — import the module once, then the tag. Attributes are strings.
import "https://cloud.pinecall.io/widget/pinecall-widget.js";

export function Support() {
  return <pinecall-widget agent="pip" name="Pip" company="Brightside Dental" token-url="/pinecall/token" />;
}
```

```vue
<script setup>
import "https://cloud.pinecall.io/widget/pinecall-widget.js";
</script>
<template>
  <pinecall-widget agent="pip" name="Pip" company="Brightside Dental" token-url="/pinecall/token" />
</template>
```

In TypeScript, declare the tag once: `declare global { namespace JSX { interface IntrinsicElements
{ "pinecall-widget": any } } }`. A site whose router keeps elements across pages (Astro's
`transition:persist`, for one) keeps the widget and its conversation as they are: it is built once.

## The files

| file | what it is |
|---|---|
| `pinecall-widget.js` | the element: its attributes, the panel's buttons, the room, the conversation |
| `styles.js` | the look, both themes, every position, the phone rules |
| `texts.js` | the words in each language, and how a site overrides them |
| `markup.js` | the agent's Markdown and HTML made safe, the icons, relative times |
| `lines.js` | the lines on screen: the dots, the typed-out reveal, what waits for the words |
| `cards.js` | choices, HTML, products and their viewer, the form, the toast |
| `panel.js` | the panel's size, drag, maximize, the phone fit, the theme switch |
| `menu.js` | the header's menu: a new conversation, the ones before, the theme, the size |
| `history.js` | the conversations kept, and the layer that lists them |
| `call-us.js` | **Call us**: the number, the code, the phone call's live log |
| `dictation.js` | dictation into the field |
| `pinecall-dot.js` | `look="dot"` |

## What is on the wire

The browser connects to the token's `server_url` with LiveKit's client SDK (`livekit-client@2.22.3`,
pinned, loaded from jsDelivr); a Content Security Policy must allow both, and, with dictation, the
gateway's `wss` origin. `look="dot"` also loads `@pinecall/room@0.11` and `@pinecall/dot@0.11` from
jsDelivr. A token opens one room for one agent and expires after `ttl_s` if unused. What the widget
keeps in this browser is under `pinecall-widget:*` keys, one set per agent: the conversations
(`localStorage`), the panel's size, the theme chosen, **Show tools**, and whether the panel was open
(`sessionStorage`).

## What is not there yet

- Wrappers with typed props and slots for React and Vue, so the chat's bubbles, header and
  composer can be replaced with your own components rather than only restyled.
- A headless core (`open`, `send`, `leave`, the transcript as events) for a page that draws its
  own UI entirely.
