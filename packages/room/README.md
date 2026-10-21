# @pinecall/room

The caller's side of a Pinecall call, in a browser. A visitor talks to your agent, writes to it, or
asks it to ring their phone; the page draws what is happening from the call's own log. No
framework, no key in the page.

## One store, three imports

Everything is one store: a value you read, a function you subscribe with, and a handful of verbs
that change it. The package has three entry points, and each one is for a different place.

| import | where it runs | what it gives you |
|---|---|---|
| `@pinecall/room` | the page | `room()`, the store of one conversation, `rowsOf`, `knownBy`, `brief` to draw it, and the karaoke of what is being said |
| `@pinecall/room/react` | the page, in React | `useRoom()`, `useStore()` and `useKaraoke()` |
| `@pinecall/room/server` | your server | `mint()`, `dial()`, `expect()` and `GatewayRefused`: the only code that touches the key |

A conversation has two parts, and they are not the same thing. **The participant** is the page's
place in a LiveKit room: it carries the audio and the typed lines. **The log** is the call's record on the gateway, read
straight from it with a token minted for that one call: every turn, every tool the agent called and what came back, the agent's own state, and
at the end the cost and the score. The store joins the two. What the page draws is the log folded
by the runtime's own reducer, the same fold the Pinecall console draws from.

## Install

```bash
pnpm add @pinecall/room livekit-client
```

`livekit-client` is only loaded when the page joins a room, so a page that only offers "call me" never
downloads it. React is optional: `@pinecall/room/react` needs React 18 or 19, the rest needs
nothing. The server entry needs Node 24 or anything else with `fetch`.

## From a page

```ts
import { room, rowsOf } from "@pinecall/room";

const call = room({
  tokens: async (scope) => {
    const answer = await fetch("/api/token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scope }),
    });
    const body = await answer.json();
    if (!answer.ok) throw new Error(body.detail ?? `the server answered ${answer.status}`);
    return body;
  },
});

call.subscribe((state) => {
  status.textContent = state.phase === "failed" ? state.error : state.phase;
  lines.replaceChildren(
    ...rowsOf(state.log).map((row) => {
      const line = document.createElement("p");
      line.textContent = row.kind === "turn" ? `${row.role}: ${row.text}` : `${row.name}(${row.args})`;
      return line;
    }),
  );
});

talkButton.onclick = () => call.start("talk");
chatButton.onclick = () => call.start("chat");
form.onsubmit = (event) => {
  event.preventDefault();
  void call.send(input.value);
  input.value = "";
};
hangUp.onclick = () => call.leave();
```

`start` is safe to call from a button that gets clicked twice: while a conversation is opening or
live, it does nothing. Once one has ended or failed, it opens a new one. When the page goes away,
`call.close()` takes everything down at once.

## With React

```tsx
import { useRoom } from "@pinecall/room/react";
import { rowsOf } from "@pinecall/room";

// `tokens` is the function from the page above.
export function Visitor() {
  const call = useRoom({ tokens });

  if (call.phase === "idle") return <button onClick={() => call.start("talk")}>Talk</button>;
  if (call.phase === "failed") return <p>{call.error}</p>;
  return (
    <>
      {call.wantsSound && <button onClick={call.playSound}>Turn the sound on</button>}
      {rowsOf(call.log).map((row) => (
        <p key={row.key}>{row.kind === "turn" ? row.text : row.name}</p>
      ))}
      {call.phase === "live" && <button onClick={() => call.leave()}>Hang up</button>}
    </>
  );
}
```

`useRoom` makes one room per mounted component and closes it when the component unmounts. The
options are read when they are used, not when the room is made, so a `tokens` written inline — a
new function every render — is fine: the one from the last render is the one that runs. It hands
back the state with the six verbs beside it.

`useStore(store)` is the plain version: any store of this package, read with React's
`useSyncExternalStore`. `useRoom` is `useStore` over a room it owns.

## Your server: two routes

The page never holds a key. It asks your server for a participant's token and, if you offer it, for
a call to its phone; your server asks the gateway with the org's key. The key needs the `talk` scope and never
reaches the page.

| route | the page sends | your server does | it answers |
|---|---|---|---|
| `POST /api/token` | `{scope, resume?}`, `talk` or `chat` | `mint(key, {url, agent, scope, log, resume})` | the gateway's answer whole: `{server_url, participant_token, call, log_token, resume_token}` |
| `POST /api/call-me` | `{to}`, a number in E.164 | `dial(key, {url, agent, to, log})` | `{call, log_token}` |

The names of the routes are yours; the page only knows the functions you give `room()`. With
Hono:

```ts
import { Hono } from "hono";
import { dial, GatewayRefused, mint } from "@pinecall/room/server";

const KEY = process.env.PINECALL_KEY!;
const url = "https://cloud.pinecall.io";
const agent = "clinica-norte";
const app = new Hono();

// A refusal keeps the gateway's own sentence and status: it names the fix.
const refused = (error: unknown) => {
  if (error instanceof GatewayRefused) return Response.json({ detail: error.message }, { status: error.status });
  throw error;
};

app.post("/api/token", async (c) => {
  const { scope, resume } = await c.req.json();
  return mint(KEY, { url, agent, scope, log: "tenant", resume }).then((minted) => c.json(minted), refused);
});

app.post("/api/call-me", async (c) => {
  const { to } = await c.req.json();
  return dial(KEY, { url, agent, to, log: "tenant" }).then(({ call, log_token }) => c.json({ call, log_token }), refused);
});
```

**The log is read from the gateway, not relayed.** Beside the participant's token, the gateway mints a
`log_token`: it reads that one call's log, its state and its recording, for four hours, before
the call ends and after, and opens nothing else — no room, no other call, no verb. The page
follows `GET /v1/calls/{call}/events` with it, and those routes answer a page on any origin. Your
server keeps no list of the calls it opened, so restarting it touches no call a page is showing.

`log` is what the token reads the call through: `public` (the default) is the turns and the
state the agent declared public; `tenant` is everything — the tools, the latency, the cost — with a
`pii` field masked. Ask for `tenant` when the page draws those, as a demo does. `gateway` in
`room()` names your own gateway; `https://cloud.pinecall.io` otherwise.

## Resume a conversation

A conversation outlives the page. Every mint answers a `resume_token`, which `state.resume` holds
once the call is open: keep it beside the conversation (`localStorage` is enough), and hand it back
to resume it.

```ts
// tokens(scope, resume) sends both on to your server: `body: JSON.stringify({ scope, resume })`.
call.subscribe((state) => state.resume && localStorage.setItem("conversation", state.resume));

// The page came back: a reload, or the tab opened again tomorrow.
continueButton.onclick = () => call.start("chat", localStorage.getItem("conversation") ?? undefined);
```

What comes back depends on when:

- **While the call waits.** A visitor's call does not end when the page goes: it waits five minutes
  for them, the agent still in the room. Resumed in that time, it is the same call (`state.call` is
  unchanged) and its log is read again from the first entry, so the page draws the whole
  conversation.
- **Later.** The gateway opens a new call that carries the old one on: the agent opens on what was
  said in it, and does not greet again. The new call's log holds only what is said from now on, so
  the page draws the earlier lines from what it kept itself.

`leave()` is a hang-up: it is said at the gateway's door first (`POST /v1/calls/{call}/hangup`
with the call's own token, `keepalive`, so a closing tab still completes it), then in the room
as the seat goes, and the call ends at once. A page that is
closed or reloaded says nothing, and its call waits. A resume token lives thirty days, and only
your server's key can spend it.

## Have the agent call me

Give `room()` a `callMe`, and the page can ask for a phone call instead of joining the room:

```ts
const call = room({
  tokens,
  callMe: async (to) => {
    const answer = await fetch("/api/call-me", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ to }),
    });
    const body = await answer.json();
    if (!answer.ok) throw new Error(body.detail ?? `the server answered ${answer.status}`);
    return body;
  },
});

await call.callMe("+34600000001");
```

The page is no participant on a phone call: the conversation happens on the phone, and the page only
watches. Everything it says comes from the log. The phase is `ringing` while the call is being
placed, `live` once the log says it was answered, and `ended` when the log says it is over — or
straight from `ringing` when nobody picked up. `speaking` comes from the log too.

Every dial passes the org's dialling rules first ([Calling out](calling-out.md) lists them and the
order they run in), and a refusal reaches the page as a failed call with the gateway's sentence.

## Let the visitor call you

Give `room()` an `expect`, and the page can show the agent's phone number and a four-digit code
instead: the visitor calls the number, keys the code on the phone (or says it, and the agent
claims it), and from that moment the page follows that call. Your server asks for the code:

```ts
import { expect } from "@pinecall/room/server";

app.post("/api/expect", async (c) => expect(KEY, { url, agent, log: "tenant" }).then((code) => c.json(code), refused));
```

The page hands the answer to the room as it came, and calls `byPhone()`:

```ts
const call = room({ tokens, expect: async () => (await fetch("/api/expect", { method: "POST" })).json() });

await call.byPhone();
```

The phase is `expecting` while the page waits, and `state.code` is `{code, number, expiresAt}`:
show "call `number` and key `code`", and `expiresAt` (seconds since the epoch) as a countdown if
you like. The page asks the gateway about the code with the code's own token, which reads that
code and nothing else; the gateway holds each ask up to 25 seconds, and a network that fails or a
`5xx` is asked again the way the log is. When a call claims the code the phase goes straight to
`live` — the caller is on the phone already — and the call is followed like any other: `call`,
the log, `speaking`, `ended`. A code lives ten minutes unless `ttl_s` says otherwise (60 to 1800
seconds); an expired one fails with "the code expired: ask for another". `leave()` while
`expecting` stops the asking at once.

The agent must answer at a phone number in the sandbox or production the key opens, or `expect()`
throws the gateway's 409 naming the fix.

## Relaying the log yourself

A page that must not reach the gateway — a network that only lets it talk to your own domain —
gives `room()` a `log` — `(call) => "/api/log?call=" + call` — and the log token is not used.
Your relay streams `GET /v1/calls/{call}/events` with the key, forwards `last-event-id`, and passes
the gateway's status and body through as they came. It must relay only the calls that visitor's
session opened: a relay that streams any call id it is handed is a window onto every call of the
org. `recording` is then `""`, and the recording is yours to relay too.

## What `state` says

Every field is the truth at the moment it was published. A new state is a new object; one you were
handed is never changed afterwards, so it can be compared by reference and kept.

| field | what it is |
|---|---|
| `phase` | `idle` · `opening` (minting, joining) · `expecting` (a code shown, no call has claimed it yet) · `ringing` (a phone call not yet answered) · `live` · `ended` · `failed` |
| `mode` | `talk`, `chat`, `phone`, or `null` before anything started |
| `call` | the call id, once the tokens or the dial answered it; `""` before |
| `error` | the sentence to show when `phase` is `failed`; `""` otherwise |
| `recording` | where the call's recording plays from, with its token: an `<audio src>` once the call has ended; `""` when the log is relayed |
| `log` | the call as the runtime's reducer folds it: `turns`, `tools`, `app_state`, `status`, `live` (the words being said right now), `cost` |
| `entries` | every entry of the log read so far, in order |
| `connection` | the log's stream: `connecting` · `live` · `reconnecting` · `ended` (also before anything opened) |
| `wantsSound` | `true` when the browser has not let the page play sound yet: show a button that calls `playSound()` |
| `speaking` | `{agent, user, level}`: who is making a sound right now, and how loud the agent is, 0 to 1 |
| `code` | `{code, number, expiresAt}` once `byPhone()` has a code to show; `null` otherwise |

The phase and everything around it — `error`, `connection`, `wantsSound`, `speaking` — are
published the moment they change. The log is painted at most ten times a second: a burst of
entries inside one turn is one repaint, not forty.

The log is read for a while after the page leaves the room. The agent's last words, the call's cost and its
score are entries that arrive after the visitor has gone, so `cost` is `null` until `call.summary`,
which comes after `call.ended`. The stream is followed until `call.score`, the last thing a log ever
says, or for `linger` milliseconds after the call ended (60 000 by default: the worker notices a caller has gone some twenty seconds after the fact, and the score comes after that), whichever is first.

A stream that drops, a network that fails, or a gateway answering `5xx` — a proxy while the gateway
behind it restarts, a deploy — is asked again from the last entry read, after half a second,
doubling to eight seconds, for as long as it takes. A `4xx` is the gateway saying no, and ends it.

## Drawing the conversation

```ts
import { brief, knownBy, rowsOf } from "@pinecall/room";
```

`rowsOf(state.log)` is the conversation as one column, in the order things happened: every turn,
and every tool run above the reply it was called for. A turn row has `role`, `text`, and for the
agent `ms` (how long the reply took, end to end), `ttft` (the model's time to its first token —
what a written call has, since nobody spoke) and `interrupted`. A tool row has `name`, `args` and `output`
as one short line each, `status` (`running`, `done`, `failed`) and `error` — and `raw`, the
`arguments` and `output` as they are, for a page that draws more than one line.

`knownBy(state.log)` is the agent's own declared fields, in the order its class writes them, as
`[name, value]` pairs with the empty ones left out. `brief(value, max)` is a value as one line of
JSON, cut at `max` characters. A field that is an object is opened one level — `person.name`, `person.email` — so a page shows a name rather than a JSON blob.

## What is being said right now

Both sides of a spoken call can be drawn as they happen, karaoke-style.

**The visitor** — `state.log.live.user` is what the recogniser has heard so far of the turn in
progress, rewritten as they speak ("Hi", "Hi ther", "Hi there. I would…"), and `null` once the
turn closes.

**The agent** — a voice call's log carries its reply one word at a time, each with the second it
is spoken at. The words usually reach the page before the voice says them, so a page can draw the
whole sentence and light each word as it sounds:

```tsx
import { useKaraoke } from "@pinecall/room/react";

const saying = useKaraoke(room.entries);   // null when nobody is mid-reply
{saying && <p><b>{saying.lit}</b><span className="dim">{saying.coming}</span></p>}
```

Without React, the same with a clock of your own: note the time the reply's first word arrived,
and on each frame split it with `litAt`.

```ts
import { litAt, sayingOf } from "@pinecall/room";

let began: { speech: string; at: number } | null = null;
function frame() {
  const saying = sayingOf(call.state.entries);
  if (saying && began?.speech !== saying.speech) began = { speech: saying.speech, at: performance.now() };
  if (saying && began) draw(litAt(saying, performance.now() - began.at));   // { lit, coming }
  requestAnimationFrame(frame);
}
```

A written call's reply comes as model tokens with no timing: every token is lit as it arrives,
which reads as the agent typing. Once the turn closes, the reply is a turn in `rowsOf` like any
other, and `useKaraoke` returns `null`.

## Sound and the browser's permission

In `talk`, the microphone is turned on once the room is joined, and the agent's voice plays through
a hidden audio element at the end of the page. `chat` joins the same room — the typed lines ride it
on LiveKit's `lk.chat` topic — and never asks for the microphone and never plays a sound.

A browser plays sound only after the visitor has done something on the page. When it has not let
the page yet, `wantsSound` is `true`: show a button, and call `playSound()` from its click. It is
asked for once, not on every event the browser fires about it, and after the click it is `false`
until the browser changes its mind.

The microphone is the browser's to give. When the visitor says no, or the device is missing, the
call fails with a sentence meant for them (below), and the page can offer to write instead.

## When something is refused

Nothing fails silently. Every refusal is a phase and a sentence, or a rejected promise.

| what happened | the state |
|---|---|
| `tokens` threw (your server, or the gateway behind it, said no) | `failed`, `error` is its message; nothing was opened |
| the microphone was refused in `talk` | `failed`, `error` is "I could not get to your microphone. Check the browser's permission, or write instead." |
| the room could not be joined in `chat` | `failed`, `error` is LiveKit's message |
| `livekit-client` could not be loaded | `failed`, `error` is the loader's message |
| `callMe` threw | `failed`, `error` is its message |
| `callMe()` on a room given no `callMe` | `failed`, `error` says so |
| `expect` threw | `failed`, `error` is its message |
| `byPhone()` on a room given no `expect` | `failed`, `error` says so |
| the code expired before a call claimed it | `failed`, "the code expired: ask for another" |
| the gateway answered a `4xx` about the code | `failed`, "the code answered 403" |
| the log answered a `4xx` | on the phone: `failed`, "the log answered 401". In a room: `connection` is `ended` and the phase is left to the room, which is the call |
| the log answered a `5xx`, or its stream dropped | `connection` is `reconnecting`, and it resumes where it was; nothing ends |
| `tokens` or `callMe` answered no `log_token`, and there is no `log` to relay it | `failed`, `error` says so |
| the room closed from the other side | `ended`; the log is read on until the score |
| an entry of the log this version cannot read | skipped; `onSkipped(why)` is called, and the rest of the call still draws |
| `send()` outside a live room | the promise rejects with "not in a call"; an empty line is nothing |

On the server, `mint`, `dial` and `expect` throw `GatewayRefused` for a refusal: `status` is the gateway's,
and `detail` its sentence when it sent one (`null` when the body was not the gateway's JSON). The
sentence names the fix — a quota, a scope the key does not hold, a number the org cannot call —
so pass it on rather than rewording it.
