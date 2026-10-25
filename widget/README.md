# Pinecall widget

A web component that puts a Pinecall agent on any page: a button that opens a voice call from
the browser, a chat, or the agent's phone number with the call's live transcript. One JavaScript
file, no build step, no framework dependency.

It is served by your gateway at `https://<gateway>/widget/pinecall-widget.js`, and by jsDelivr from
the public repository at `https://cdn.jsdelivr.net/gh/pinecall/pinecall@main/widget/pinecall-widget.js`.

```html
<script type="module" src="https://cloud.pinecall.io/widget/pinecall-widget.js"></script>
<pinecall-widget agent="bidfire-sales" name="Sam" company="BidFire"
                 token-url="/pinecall/token" log-url="/pinecall/log"></pinecall-widget>
```

## The tag

| attribute | | |
|---|---|---|
| `agent` | required | the agent's slug, as `pinecall start` prints it |
| `token-url` | required, unless `tokenProvider` is set | your token endpoint (below) |
| `log-url` | optional | your log endpoint (below): transcripts from the call log, live phone calls, a "Show tools" toggle |
| `code-url` | optional | your code endpoint (below): "Call us" shows the number and a 4-digit code that ties the phone call to this page |
| `gateway` | optional | gateway origin for codes and their logs; defaults to the script's origin (`cloud.pinecall.io` for the jsDelivr copy) |
| `phone` | optional | number shown by "Call us" when there is no `code-url`; with neither, "Call us" is hidden |
| `name` | optional | what the agent is called on screen, `Assistant` when left out |
| `company` | optional | whose agent it is, shown under the name |
| `tagline` | optional | the line under the name, after the company |
| `label` | optional | the button's text, `Talk to <name>` when left out |
| `icon` | optional | `none` leaves the button without its icon |
| `button` | optional | `none` draws no button at all: open the panel with `toggle()` from anything of yours |
| `lang` | optional | the language of the widget's own words — its menu, buttons and statuses: `en` (default) or `es`. The agent answers in whatever language the visitor speaks either way |
| `position` | optional | `bottom-right` (default), `bottom-left`, `top-right`, `top-left`, or `inline`: the button right where the tag is, in the page's own flow |
| `greeting` | optional | the agent's first bubble, shown before a call starts; plain text (markup is escaped) |
| `theme` | optional | `auto` (default, follows `prefers-color-scheme`, and the visitor may switch it from the panel's header, their choice kept in this browser), `light` or `dark` (forced, no switch) |
| `autostart` | optional | the opening click starts a voice call directly; if the microphone is refused, the menu opens with the reason |
| `history` | optional | `off` keeps no conversations in this browser. By default the visitor's last 20 chats and calls with this agent are kept in `localStorage` — the lines as they settled, at most 200 each — listed under **Your conversations** in the menu, any one readable again, and cleared by the visitor with **Clear** |
| `look` | optional | `dot`: the button is a face that speaks with the agent's voice, and a click is a voice call with no panel ([below](#the-talking-dot)) |
| `tutor` | optional | with `look="dot"`: the dot walks the visitor through the page with a pointer of its own, for an agent that extends `Tutor` ([below](#the-dot-as-a-tutor)) |
| `shape` · `color` | optional | with `look="dot"`: the face's shape, `circle` (default), `squircle` or `blob`, and its colour, any CSS colour (else the widget's accent) |
| `captions` | optional | with `tutor`: whose words show in writing, `both` (default), `agent`, `caller` or `none`. Unless `none`, the visitor turns them off and on with the **CC** button, their choice kept in this browser |

Attributes are read once when the element connects, except `token-url`, which is read for every
token. Use one tag per agent; several can share a page. The console stores these settings per
agent (`GET`/`PUT /v1/agents/{slug}/widget`) to generate a snippet; the widget itself only reads
its attributes.

Without `log-url`, transcripts come from LiveKit text streams only, "Call us" shows just the
number, and there is no tools toggle.

## Your two endpoints

The org's API key stays on your server, which exposes these endpoints; the widget sends the
agent's slug with each request, so one set of endpoints serves every agent (reject slugs your site
doesn't serve). Use a production key with the `talk` scope (tokens, codes) and `calls` (logs), sent
as `Authorization: Bearer <key>`.

### `token-url`

The widget sends:

```http
POST <token-url>
Content-Type: application/json

{ "agent": "<slug>", "scope": "talk" | "chat", "resume": "<resume_token>" }
```

`talk` for a voice call, `chat` for a written one; `resume` only when the visitor carries on a
conversation of theirs ([below](#your-conversations)). Your server posts to Pinecall:

```http
POST https://<gateway>/v1/tokens
Authorization: Bearer <key>
Content-Type: application/json

{ "agent": "<slug>", "scope": "talk" | "chat", "ttl_s": 60, "metadata": { … }, "resume": "<as sent>" }
```

Return Pinecall's response unchanged: `201` with
`{ "server_url", "participant_token", "call", "log_token", "resume_token" }` (`log_token` reads
that call's log and opens no room; `resume_token` is what the widget keeps to carry the
conversation on). Pass `resume` on as it came: only your key can spend it.
`ttl_s` defaults to 60; a longer one is cut to a day (86400). `metadata` is sealed into the call: the agent reads it as `this.call.metadata`
(`call.started` carries it), and the browser cannot alter it. Errors come as `{ "detail": "…" }` (`404` unknown agent, `429` quota
spent, `503` fleet full); pass them through and the widget shows `detail`. `room_name`,
`participant_name` and `participant_metadata` are rejected with `400`.

Instead of `token-url`, you can set the element's `tokenProvider` property to
`(scope, agent, resume) => Promise<token JSON>`:

```js
document.querySelector("pinecall-widget").tokenProvider = (scope, agent, resume) =>
  fetch("/my/mint", { method: "POST", body: JSON.stringify({ scope, agent, resume }) }).then((r) => r.json());
```

### `code-url` — optional, and the way to put a phone call on the page

Links a phone call to the page: the widget shows the agent's number and a 4-digit code; the
caller enters or says it when the agent asks, and the panel then follows that call only.

The widget sends:

```http
POST <code-url>
Content-Type: application/json

{ "agent": "<slug>" }
```

Your server posts to Pinecall with a key that has the `talk` scope:

```http
POST https://<gateway>/v1/codes
Authorization: Bearer <key>
Content-Type: application/json

{ "agent": "<slug>" }
```

Return the response unchanged: `201` with `{ "code", "number", "expires_at", "code_token" }`. The
agent needs a phone number (`pinecall numbers import`), otherwise `409`. A code lasts 10 minutes
(`ttl_s`, 60–1800). The browser then talks to the gateway directly: it polls
`GET /v1/codes/{code}?wait=1` with the code token and, once a call claims the code, reads that
call's log with the returned log token. Both are credential-less cross-origin `GET`s, so there is
nothing to relay.

Or no endpoint: set the element's `codeProvider` property to `(agent) => Promise<code JSON>`.

### `log-url` — optional

Two `GET` queries, both with `agent` added to whatever query string `log-url` already has:

**`<log-url>?agent=<slug>&list=1`** — the agent's latest telephone calls. The widget polls it once a
second while "Call us" is open, and expects `200` with:

```json
{ "calls": [ { "call": "call_…", "live": true, "from": "···169", "started_at": 1789000000.5 } ] }
```

Your server reads `GET https://<gateway>/v1/agents/<slug>/sessions?limit=30` (newest first,
`{ "calls": [ … ] }`), keeps only the rows with `channel == "phone"`, and answers those four fields
of each. `started_at` is Unix seconds; the widget shows the call that is `live`, or a call that
started after "Call us" was opened. `from` is printed on the page as it comes, and the page is
public: cut the caller's number to its last three digits.

**`<log-url>?agent=<slug>&call=<id>`** — one call's log, live, as server-sent events. Your server
relays

```http
GET https://<gateway>/v1/calls/<id>/events?types=call.started,user.transcript,agent.transcript,turn.user,turn.agent,tool.call,tool.result,call.ended&after=0
Authorization: Bearer <key>
Accept: text/event-stream
```

and streams the answer back byte for byte as `text/event-stream`, flushing every chunk, with
`Cache-Control: no-cache` and buffering off (`X-Accel-Buffering: no` behind nginx). Without that
`Accept` header Pinecall answers a JSON page instead of the stream. Each frame is
`id: <seq>` · `event: <type>` · `data: <JSON>`, and the widget reads the entry's payload from the
JSON's `data` field. Check that `<id>` is a call id before putting it in the URL.

## Your conversations

A visitor who comes back finds their last chats and calls in the menu: the first thing they said,
when, how many lines. Opening one shows it as it was, and it goes on from there: a chat takes a new
line under the old ones, a call has **Continue the call**. **New chat** and **New call** start
afresh. The lines are this browser's alone, so a shared computer is a reason to set
`history="off"`, and the visitor can always press **Clear**.

Carrying one on asks your `token-url` with the conversation's `resume` token, kept beside it. A
visitor back within five minutes (a reload, a tab closed and opened again) is the same call, which
waited for them; later, Pinecall opens a new call whose agent reads what was said and does not
greet again. Either way it stays one conversation in the menu. Closing the panel or reloading is
not hanging up; **Hang up** and **End chat** are, said at the gateway's door with the call's own
token before the widget leaves the room, and the call ends at once.

## The look

The font is inherited from the page, and `theme` picks the light colours or the dark ones.
Everything else is a custom property on the tag, and one the page sets wins in either theme — set
it under `pinecall-widget[theme="dark"]` or a `prefers-color-scheme` query to give a theme its own:

```css
pinecall-widget {
  --pc-accent: #0f766e;       /* the button, the links, the agent's bubbles — default #6d28d9 */
  --pc-accent-soft: #f0fdfa;  /* the soft background behind them — default #f5f3ff */
  --pc-ink: #111;             /* the text — default #1f2937 */
  --pc-muted: #6b7280;        /* the second line of text */
  --pc-line: #e5e7eb;         /* borders */
  --pc-radius: 14px;          /* the panel's corners */
  --pc-offset: 20px;          /* the distance from the page's edge */
  --pc-font: Inter, sans-serif; /* default: the page's own */
  --pc-font-size: 15px;
  --pc-z: 2147483000;
  --pc-panel-width: 480px;    /* the size a panel opens at — default 480px */
  --pc-panel-height: 760px;   /* default 760px */
}
pinecall-widget::part(button) { border-radius: 8px; }   /* the button, outright */
pinecall-widget::part(panel) { box-shadow: none; }      /* the panel, outright */
```

The panel is the visitor's to size: they drag its corner, or maximize it from the header, and the
size they leave is kept in this browser.

## The button

The button is yours to style, as far as you want to take it. Four ways, from a colour to a
launcher of your own:

```css
/* 1. Its own custom properties, in either theme */
pinecall-widget {
  --pc-button-bg: #111;            /* default: --pc-accent */
  --pc-button-ink: #fff;
  --pc-button-border: 1px solid #333;
  --pc-button-radius: 10px;        /* default 999px */
  --pc-button-padding: 14px 22px;
  --pc-button-shadow: none;
  --pc-button-weight: 500;
  --pc-button-font-size: 16px;
}

/* 2. Anything CSS can say, through its parts */
pinecall-widget::part(button) { text-transform: uppercase; letter-spacing: .08em; }
pinecall-widget::part(button-icon) { color: #facc15; }
pinecall-widget::part(button-label) { font-style: italic; }
```

3. `icon="none"` takes the icon away.

4. Your own element, in place of the button: give the tag a child with `slot="button"`. It is your
markup in your page, styled by your CSS like any other element, and a click on it opens the panel
(`autostart` included). With `button="none"` there is no button at all, and anything of yours opens
the panel with `toggle()`.

```html
<pinecall-widget agent="front-desk" token-url="/pinecall/token">
  <a slot="button" class="my-cta" href="#">Talk to us now</a>
</pinecall-widget>
```

## The talking dot

`look="dot"` turns the button into a small face (a dot with eyes and a mouth) that speaks with the
agent's voice. A click starts a voice call at once, with no panel. While the agent speaks, a bubble
above the dot lights each word as it is said, and the line stays a moment after the reply ends.
The face rests, listens and thinks with the agent's state. A click during the call offers
**Hang up**. A refused microphone, or a token your server refused, opens the usual menu with the
reason. The call is kept under **Your conversations** like any other.

```html
<pinecall-widget agent="front-desk" name="Pip" look="dot" token-url="/pinecall/token"></pinecall-widget>
```

The dot stands on [`@pinecall/room`](../packages/room/README.md) and
[`@pinecall/dot`](../packages/dot/README.md), both loaded from jsDelivr only for this look. It reads the call's
log straight from `gateway` with the call's own token, so `log-url` is not used. Its size is
`--pc-dot-size` (64px by default), its colour `--pc-accent`, and its bubble the part `bubble`. What
the agent shows with `pinecall.ui` has no room on a dot: the tag dispatches it as `pinecall:ui`
instead (below).

## The dot as a tutor

`look="dot" tutor` makes the dot one more person on the page. The agent points at what it talks
about with a pointer of its own, highlights it, scrolls to it and shows where to click, and it
never clicks, sends a form or opens another page for the visitor; it fills a form's fields with what
the visitor tells it, and they press its button. Its prompt reads the page as it is now, sent by the page each
time it changes. The agent extends `Tutor` from `@pinecall/dot/agent`, and its walks are macros in
its folder ([@pinecall/dot](../packages/dot/README.md#the-tutor-in-the-agent)).

```html
<pinecall-widget agent="front-desk" name="Pip" look="dot" tutor token-url="/pinecall/token"></pinecall-widget>
```

During a call, two buttons sit beside the dot's corner: **CC**, which turns the written words off
and on, and **✕**, which hangs up. The agent's words show beside the dot as its voice says them;
the visitor's, what the agent heard, show in the corner as they speak and a moment after, one side
at a time. `captions` says which may show.

## Telling the agent what the visitor does

`event(name, data)` on the tag tells the agent what the visitor did on the page: the section they
opened, the plan they chose. The agent's `onEvent(name, data)` runs when its class accepts that
name from a participant, and the runtime drops any other. A state field the hook writes is in the
agent's view at its next turn, so the prompt follows the page, and the hook can `reply()` at once.

```js
const widget = document.querySelector("pinecall-widget");
pricing.addEventListener("click", () => widget.event("plan.chosen", { plan: "pro" }));
```

It rejects when no call or chat is open. Anybody can send what a browser sends: keep `data` to
values the agent's view reads, never words the model is told to obey.

## What the agent can show

The agent can put things on the visitor's screen with `this.call.send("pinecall.ui", data)`, drawn
in the conversation:

- `{ type: "choices", text?, options: [{ label, value? }] }` draws buttons; the one tapped is the
  visitor's next line (`value`, else `label`).
- `{ type: "html", html }` draws a card. Only text, lists, tables, `https` links (opened in a new tab),
  `https` images and code are kept; scripts and styles never run.

## Events

The tag dispatches `pinecall:open` when the panel opens, `pinecall:started` (`detail: {call,
scope}`) when a voice call or chat has joined, and `pinecall:ended` (`detail: {call}`) when it
leaves, so a page can track conversions. With `look="dot"`, `pinecall:ui` (`detail`: what the agent
sent on `pinecall.ui`) is a card or choices the dot cannot draw. **New call** / **New chat** ends the current
conversation (`pinecall:ended`) and starts another with a fresh token (`pinecall:started`). `toggle()` opens the panel, or closes it when open:
`document.querySelector("pinecall-widget").toggle()`.

## In React, Vue, Svelte

A custom element is an element: render the tag and it works.

```jsx
// React — import the module once, then the tag. Attributes are strings.
import "https://cloud.pinecall.io/widget/pinecall-widget.js";

export function Support() {
  return <pinecall-widget agent="bidfire-sales" name="Sam" token-url="/pinecall/token" log-url="/pinecall/log" />;
}
```

```vue
<script setup>
import "https://cloud.pinecall.io/widget/pinecall-widget.js";
</script>
<template>
  <pinecall-widget agent="bidfire-sales" name="Sam" token-url="/pinecall/token" log-url="/pinecall/log" />
</template>
```

In TypeScript, declare the tag once: `declare global { namespace JSX { interface IntrinsicElements
{ "pinecall-widget": any } } }`.

## What is on the wire

The browser connects to the token's `server_url` with LiveKit's client SDK (`livekit-client@2`,
loaded from jsDelivr); a Content Security Policy must allow both. `look="dot"` also loads
`@pinecall/room@0.11` from jsDelivr, and reads the log from `gateway`. A token opens one room for one
agent and expires after `ttl_s` if unused.

## What is not there yet

- Wrappers with typed props and slots for React and Vue, so the chat's bubbles, header and
  composer can be replaced with your own components rather than only restyled.
- A headless core (`open`, `send`, `leave`, the transcript as events) for a page that draws its
  own UI entirely.
