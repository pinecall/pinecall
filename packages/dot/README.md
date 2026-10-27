# @pinecall/dot

> **Experimental.** The dot and its tutor are an add-on of Pinecall, not part of its core, and they
> are still being found: any of their API, attributes and messages may change or go in any release, a
> patch one included. These pages are their only documentation, and they describe what is true today.

The talking dot. A small face, a dot with eyes and a mouth, speaks with your agent's voice, moving
its mouth with the sound frame by frame. As a tutor it becomes one more person on the page, with a
pointer of its own: it walks the visitor through the site, hovers and highlights what it talks
about, and the agent's prompt reads the page as it is now.

It stands on [`@pinecall/room`](../room/README.md), which joins the call. The pinecall widget
draws it with `<pinecall-widget look="dot">`, and with `look="dot" tutor` the tutor too.

**To build a tutor, start with [Write a tutor agent](docs/write-a-tutor.md)**, step by step, and
[Macros](docs/macros.md), the format of a guided walk. This page is the reference.

| import | where it runs | what it gives you |
|---|---|---|
| `@pinecall/dot` | the page | `face()`, `tutor()`, and `Page`, the page as the agent reads it |
| `@pinecall/dot/agent` | the agent's process | `Tutor`, the class an agent extends to be a tutor, and `macros()` |

```bash
pnpm add @pinecall/dot @pinecall/room livekit-client     # the page
pnpm add @pinecall/dot @pinecall/agents                  # the agent
```

## The face

```ts
import { room } from "@pinecall/room";
import { face } from "@pinecall/dot";

const call = room({ tokens });
const pip = face(document.querySelector("#pip"), call);   // the element sets the size

talkButton.onclick = () => {
  pip.wake();             // inside the click: a browser starts audio only here
  void call.start("talk");
};
// pip.close() takes it off the page.
```

The face fills its element with one SVG: 64 px is a launcher, 240 px a hero. Two faces on one page are fine.

**Its shape and colour.** `face(host, call, { shape, color })`: `shape` is `circle` (the default),
`squircle` or `blob`, and `color` any CSS colour (else the page's `--pc-face`). `reshape(shape)` changes it
later, the body easing from one into the other. The body moves whole with the mood, its outline never bent: it
bobs and leans in while it listens, more slowly while it thinks, and squashes with the voice while it speaks;
still under `prefers-reduced-motion`. Nothing is drawn outside the body, no halo and no shadow, so it sits on
any background. `tutor()` takes the same `shape` and `color`, which tints its pointer too.

**How the mouth is read.** Everything happens in the browser, from the element the agent's voice
plays in (`state.voice`):

| step | what |
|---|---|
| the ear | an analyser on that element's stream, never connected to the speakers: the element already plays it |
| how open | the frame's loudness, against the loudest recent frame, so a quiet voice opens fully too |
| what shape | where the energy is. Highs over 4 kHz are S or T (teeth, little opening). 1.5–3.5 kHz is EE or EH (wide). Energy under 500 Hz with no highs is OO or O (round) |
| motion | every number eases toward its target, quick to open and slower to close |

Because it measures the sound as it plays, the mouth is in time with the voice by construction,
whatever the voice vendor. Until `wake()` is called, or without Web Audio, the mouth opens with
`state.speaking.level`, in no particular shape.

| the room | the face |
|---|---|
| `idle`, `ended`, `failed` | rests: a smile, breathing, a blink every few seconds |
| `opening` | thinks: eyes up, looking from side to side, a small round mouth sliding with them |
| `live`, the agent `listening` | waits: head tilted, eyes a little wider, bobbing slowly |
| `live`, the caller speaking (`speaking.user`, or their words coming in) | hears: head cocked further, eyes wide on the caller, nodding |
| `live`, the agent `thinking` | thinks |
| `live`, the voice sounding | speaks: the mouth from the voice, the body with its loudness |

With `prefers-reduced-motion`, breathing, tilting and glances stop, and the mouth still speaks.
Colours are custom properties on any ancestor: `--pc-face` (the dot), `--pc-face-eye`,
`--pc-face-mouth`, `--pc-face-teeth`, `--pc-face-tongue`.

## The tutor, on the page

```ts
import { room } from "@pinecall/room";
import { tutor } from "@pinecall/dot";

let pip = null;
const call = room({ tokens, onUi: (data) => pip?.take(data) || drawCard(data) });
pip = tutor(call, { label: "Talk to Pip", onClick: () => { pip.wake(); void call.start("talk"); } });
```

`tutor()` puts the person on the page: resting, its face in the bottom-right corner (`dock: "left"`
for the other), 58 px across (`--pc-dot-size`) and 14 px from the edges; touring, a pointer in its colour with the face beside the tip and what it says
beside the face. It moves the way a hand moves a mouse:

- **It aims at an element the way a person does.** It lands on the middle of the element's first
words, not of its box, and flies there on a minimum-jerk path with a slight arc, timed by the distance.
- **The pointer looks like the one the element asks for**: a hand on a link, an I-beam in a field.
- **Hover looks real.** Every `:hover` rule of the site's own style sheets is mirrored onto
`[data-pc-hover]`, set on the element under the tip and its ancestors, and `pointerenter` and `mouseenter` are
sent for the site's code. A style sheet from another origin cannot be read and keeps no hover.
- **It scrolls the page eased**, until the element sits a little above the middle of the screen, below the
  site's own header: a fixed or sticky bar along the top (or the page's `scroll-padding-top`) is measured
  and left out, so nothing it shows ends up under it.
- **A highlight dims the rest of the page** and follows the element as the page scrolls. "Here" is a
  ring at the tip.

**It never sends a form or opens another page for the visitor.** It shows where, and they do it. A
form's fields it fills with what the visitor told it, typed letter by letter with the `input` and
`change` events the site's code listens for, a list by the option that says it; the visitor presses
its button. It never touches a password, a card number, a file or a hidden field. The one button it
presses is one a walk the site wrote names (`press`): outside any form, or in a search form
(`<search>`, `role="search"`); never a link, never a form that books, buys or signs up.

**The conversation in writing, and the call's buttons.** The agent's words show beside the face,
lit as its voice says them; the visitor's, what the agent heard, show in the corner as they speak and for
`linger` ms after (2600 by default), one side at a time. `captions` chooses whose may show: `both` (default),
`agent`, `caller` or `none`. During a call two buttons sit beside the corner: **CC**, which turns the words on
and off for this visitor: off until they turn them on (kept in their browser's `localStorage`, and absent with
`captions: "none"`), and **✕**, which hangs up (`call.leave()`). While a walk plays, CC sits there with **■**,
which stops it. The buttons slide into the face's corner while it tours, and aside as it comes home. No words
show while a window of code or a card is open: they would cover it. `words: { hangUp, captions, stop }` names
them for a screen reader.

`take(data)` returns `true` for a message that was the tutor's (a cursor move, a macro step) and
`false` for anything else, which stays the page's to draw.

### The page as the agent reads it

`Page` reads the page the way Playwright's aria snapshot does: roles and names, not markup.

```
- page "Brightside Dental" (scrolled 1180–2080 of 3460px)
- banner
  - link "Brightside Dental" [ref=e1]
  - navigation "Main"
    - link "Services" [ref=e2]
- main
  - region "Services" [ref=e6] (above)
  - region "Pricing" [ref=e9]
    - heading "Pricing" [level=2] [ref=e10]
    - article "Family Care plan" [ref=e14]
      - text "$39 / month"
      - button "Choose Family Care" [ref=e16]
  - region "Book your first visit" [ref=e18] (below)
```

- **What is on the screen is there in full. A section out of view is one line**, its name and
  `above` or `below`.
- **Words in a box that is only layout are a line of text**, as a price in a `<div>`, as Playwright
  says them.
- **A ref is stable for the page's life**, and still names its element after a scroll took it off
  the screen.
- **A field is its label and what it holds now**: `[value="Jordan Lee"]` or `[empty]`, a list's
choice and its `(options …)`, `[checked]` or `[unchecked]`, so the agent sees what the visitor typed. Passwords,
card numbers, and anything under `[data-pinecall-skip]` or `aria-hidden` are left out.
- **What the site wrote for the agent to say is marked `[has a line]`** ([below](#lines-on-the-page)).

The tutor sends it as `page.seen` when the call goes live, when a scroll stops, on a resize, when
the DOM changes (a question opened, a tab), on a click, and before each of the agent's moves. It
is sent only when it changed, but for one answer: when a move onto a thing ends, the page is sent
again with `why: "moved"` and the ref it moved to, and why a field could not be filled (`refused`).
What the visitor types in a field reaches the agent the same way, a moment after.

## The tutor, in the agent

```ts
import { macros, Tutor } from "@pinecall/dot/agent";
import tour from "./macros/tour.json" with { type: "json" };

/** You are Pip, Brightside Dental's front desk, on the visitor's screen. Short sentences. */
export default class Pip extends Tutor {
  static override macros = macros({ tour });
}
```

A class that extends `Tutor` gets these:

- **The page's events**, from the visitor's browser only: `page.seen`, `page.clicked`, `page.missing`.
- **`page` and `clicked` in its state.**
- **A view that prints the screen.** A class with a `render()` of its own ends it with `this.seeing()`.
  The site's words are fenced there as data, never as instructions to the model.
- **The pointer's tools**: `point`, `highlight`, `unhighlight`, `scrollTo`, `here`, `home`, `fill`,
  `explain` and `runMacro`.
  There is none to open a page: the tutor never leaves the page the visitor is on. They show once the page has been seen. The pointer's moves are `quiet`: they run as the
  model calls them, while the words that name them play, and the model answers one only when it made
  it without a word; `runMacro` too, which starts on its own first words and ends on its own last ones.
- **A move onto a thing waits for the page to say it ended** (`point`, `highlight`, `scrollTo`, three
seconds at most), and its result is that thing as the visitor now sees it, fenced as data: a section that was
one line below the fold comes back in full, its prices with it, for the model to talk about.
- **`fill(field, text)` writes what the visitor said into a field**, after the agent asked for it,
  one field at a time; its result is the field as it now shows, and a field the page refused (a
  password, a list with no such option) is a tool error naming why. It never sends the form.
- **The pointer only where a tutor's page is.** A call no tutor's page joined (the phone, a page with
  no dot, a chat) is the agent's alone: its view says nothing of a screen and the pointer's tools stay
  hidden. So an agent that answers the phone too can extend `Tutor` and lose nothing there.
- **The page asked for as the call opens**, on the web: `onCall` sends `{ type: "look" }`, and the page answers with
  `page.seen`. LiveKit keeps no data for a participant who joins after it was sent, so the agent asks
  once it is there. A page that joins a call already under way (a reload) tells it at once.

A class that overrides `onCall` or `onEvent` calls `super.onCall(call)` or
`super.onEvent(name, data, meta)` first.

### Macros

A macro is a guided walk, saved in the agent's folder as `macros/<name>.json`. Each step is a
sentence the agent says as written, and each beat is a move run as its word is said:

```json
{
  "name": "tour",
  "when": "the visitor asks to be shown around",
  "steps": [
    { "say": "Up here are our services. Whitening is the one most people ask about.",
      "beats": [
        { "word": "Up", "do": "point", "find": ["link", "Services"] },
        { "word": "Whitening", "do": "point", "find": ["article", "Whitening"] },
        { "word": "is", "do": "highlight", "find": ["article", "Whitening"] }
      ] }
  ]
}
```

- **`find` names the element as the snapshot does**, by role and a part of its name, so a macro
  survives a change of the markup.
- **A step can show code beside the page**: `"code": { "title": "agent.ts", "text": "…" }` opens a
  window with it, `"lines": [4, 5]` lights the lines the sentence is about and dims the rest, and a
  later step lights others in the same window; `"code": null` closes it, as does the walk's end.
- **`nth` picks which time a word is said**, from 1.
- **`macros()` checks every file when the class loads**, and refuses a beat on a word its sentence
  never says.
- **A model names a walk the way it heard it**: `runMacro("site tour")` runs `tour`, and an agent with one
  walk runs it whatever it is called (`walkNamed`).
- **A macro can be a function** ([docs/macros.md](docs/macros.md#a-macro-as-a-function)): `params` it is
  called with fill the `{slots}` of its sentences, and steps that act fill a field, press a search, wait
  for its answer and read the table it drew (`{hit.Time}`). In a call the model passes the params; typed
  to the dot, they are picked out of what the visitor wrote. A sentence with slots is recorded live.

How a macro runs. `runMacro("tour")` sends each step on `pinecall.ui`, then says it. The page binds
the step to the reply that follows and counts its words as the voice says them, the same word
timings room's karaoke lights words with. Each beat runs as its word starts. When the visitor
speaks, the walk stops and the agent answers them.

### Walks the visitor plays with no call

A macro is also a **walk the visitor plays on their own**, with no call and nothing spent. As the
agent starts (`static onServe`, run by `pinecall start` and by a deployed app), `Tutor` records each
sentence of each macro once in the agent's own voice, with when each word is said, and publishes
them as the agent's `walks` document; the terminal says `walk tour · 5 sentences · 0:38 · cartesia
sonic-3 …`. A sentence recorded before, in the same voice, costs nothing; a sentence edited, a voice
or a lexicon changed is recorded again at the next start. A macro's `"title"` is its button.

On the page, `tutor(call, { walks: "https://<gateway>/v1/agents/<slug>/public/walks" })` (the
widget's `walks` attribute) puts a small button beside the resting face. A click fans the walks out
round it, four at a time (a small ⌄ under them shows the next ones), each a pill with its title and length; a pick plays it: the voice, the mouth moving with
it, the words lit as said, each beat on its word, a ring round the face for how far it is. While it
plays, the corner holds captions, pause and stop; a click on the face stops it too. No microphone is
asked for. A section can name its walk: with `data-pinecall-walk="<macro>"` on it, the menu, when it
opens, marks the walk of the section the visitor is on (the one across the screen's middle) and opens on
the page it stands on. The site can also draw its own button, `hidden`, and mark it
`data-pinecall-play="<macro>"`: the tutor shows it while that walk can play, and a click plays it. A call opened afterwards tells the agent which walk
was played and how far (`page.walked`), so it goes on from there rather than give it again.
`onWalk` hears each start and end, for the page's own analytics.

### The views of a project's own tools

A project's agent has tools of its own: the free times, a booking, a piece of code. Their results are
already on the call's log, so the page says how to draw each, by the tool's name, and the tutor puts it
on a card above the face's corner when the tool finishes:

```ts
tutor(call, {
  views: {
    freeSlots: (host, result, tools) => {
      host.innerHTML = (result as { times: string[] }).times.map((time) => `<button>${time}</button>`).join("");
      host.addEventListener("click", (event) => tools.send((event.target as HTMLElement).textContent ?? ""));
    },
  },
});
```

A view draws into `host` and may answer a function that takes it down. `tools.send(text)` says
something to the agent in writing, as the visitor: a time picked, a name and an email typed instead of
spelled out; `tools.hide()` puts the card away; `tools.state()` reads the call, to mark what the agent
chose. The card holds the last tool that finished with a view, until it is replaced, closed with its
×, or the call ends; a page that joins a call under way shows none of what ran before. It is the
visitor's way to say something, never a way round the agent: nothing on it books or sends for them.
With the widget, set `widget.views = { … }` on the element. Colours: `--pc-card` and `--pc-card-ink`.

### Typing to the dot: one thing done, never a conversation

`tutor(call, { ask })` puts a field in the walks' menu ("Ask me to show you…"). `ask(request)` is the
site's door, on its own server. What the visitor types goes there with the page's path, its named
things by ref and the walks of the page (`{ decide }`); the answer is one thing to do, and the dot does
it with no call: it plays a walk, called with the params picked out of what was typed, or lights and
points at a thing with its name beside the face. A question a person answers, or something not on the
page, is never answered in the dot's words: the field says so, with a button that hands it to
`onTalk(message)` (the site starts a call with it written in). The same door picks the row of a table a
walk read (`{ row }`) and records a walk's sentence once its slots are filled (`{ say }`).

```ts
// the page
tutor(call, { ask: (request) => fetch("/api/ask", { method: "POST", body: JSON.stringify(request) }).then((r) => r.json()) });

// the site's server
import { answer } from "@pinecall/dot/server";
const answered = await answer(body, {
  key: process.env.OPENROUTER_API_KEY,
  voicing: { key: process.env.PINECALL_KEY, agent: "pip" }, // records sentences with slots in the agent's voice
});
```

`answer()` asks Jev, TypeSafe's System One model, through OpenRouter's Decisions API: one request, its
questions answered at once (what they want, which walk, which thing of the page, each param of each walk),
each a choice among the options given, with probabilities. A param in the visitor's words is one of the
parts of what they typed (one to five words in a row): what fills a field is what they wrote, never a word
of the model's. A sentence with slots is read from the walks the agent published, never from the page, and
recorded once per set of values (a line of 80 characters each). Jev cannot write a sentence or name a thing
not on the page, and under its threshold (0.5) decides nothing rather than guess. The page's words and what
the visitor typed go to OpenRouter and TypeSafe: a site says so in its privacy policy.

### A page read aloud

`tutor(call, { ask, reading: "Leer el capítulo" })` puts a first pill in the walks' menu that reads the page
aloud in the agent's voice, with no call: what the site marks `data-pinecall-read` (a `<main>`, a section), its
headings, paragraphs, items and captions in the page's order, as written, the part read lit and pointed at and
the rest dimmed; a long one is read a few sentences at a time. A button marked `data-pinecall-press` is an
example: reached, the pointer presses it (its value said first: `data-pinecall-press="Lo corro."`), the reading
waits for what it controls (`aria-controls`, its output) to answer and not be `aria-busy`, then says its
`data-pinecall-then` pointing at the output and reads the output line by line with notes: `data-pinecall-notes`
names a list whose items each find a line of it (`data-pinecall-find`, a text in any case or `/a regex/`) and
say what it means; the line is lit and pointed at, the output marked `data-pinecall-reading` meanwhile so the
site can widen a box that scrolls. A note whose line is not there is left out. A field marked
`data-pinecall-type` is typed with its value, the page's own example (a chat's question), and the
`data-pinecall-press` after it sends it, in any form; an element that is no field (an editor) marked so is told
each letter by `pinecall-typing` events the site takes with `preventDefault()`. A frame of the site's own (a
chat in an iframe) is read in its place. A send button marked `data-pinecall-goal` is a chat the dot talks to:
it asks the door for its line (`{ next }`: Pinecall's caller, with `voicing.next`), opens the chat by focusing
its field (its greeting waited on while busy), says each line as it types it, sends it, reads aloud what the
agent said and the tools it used (turns marked `data-pinecall-said`; a tool's said by its `data-pinecall-say`)
until it has what it came for, the chat ends (a turn marked `end`) or forty turns pass, and the page goes on.
Such a button in no form is a spoken call: the dot presses it, hears the greeting (`data-pinecall-heard` on the
output: the agent is heard, not read) and says its lines into the call, the output told each by a
`pinecall-saying` event with its recording, for the site to play in; `tutor.stop()` ends a reading when the
visitor takes over. A page whose top was scrolled away is read from the first part still in view. A button
marked `data-pinecall-explain` with no notes has its output explained by the door (`{ explain }`, with
`voicing.explain`), the notes read in the place of its `data-pinecall-then`. `data-pinecall-quiet` is not read.
An element with `data-pinecall-say` is said as that line instead, nothing inside it read again. `tutor.read()`
starts it from a button of the site's own; while it plays, the corner holds back, pause, next and stop.

Each part is recorded by the site's door when the reading reaches it, the next asked for while one plays (`{
read: { text } }`), and the gateway keeps it: a page read twice costs nothing the second time. A door lets its
pages be read only when it says so (`answer(body, { voicing: { …, read: true } })`): a page may then have any
text of 480 characters said in the agent's voice, so a site gives it to its own pages alone.

```html
<main data-pinecall-read>
  <h2>Cómo leer esto</h2>
  <p>Cada comando está en un bloque con ▶ Run.</p>
  <div class="block" data-pinecall-quiet>
    <pre>pinecall whoami</pre>
    <button aria-label="Run pinecall whoami" aria-controls="out-1" data-pinecall-press="Lo corro." data-pinecall-notes="notes-1">▶ Run</button>
    <output id="out-1"></output>
    <ol id="notes-1" hidden data-pinecall-skip>
      <li data-pinecall-find="org lesson">Ahí está tu org, lesson.</li>
      <li data-pinecall-find="/person's key/">Y es una key de persona.</li>
    </ol>
  </div>
</main>
```

### Lines on the page

A walk can also live in the site's own markup, beside what it is about:

```html
<section id="pricing" data-pinecall-say="Pricing is simple: three plans, and most families pick Family Care." data-pinecall-do="highlight">
<article data-pinecall-say="Family Care covers up to four people for thirty-nine dollars a month." data-pinecall-order="2">
```

- **`data-pinecall-say` is said as written**, with the move `data-pinecall-do` names (`point` unless
  `highlight` or `scroll_to`), in `data-pinecall-order` and then in the page's order; a line under
  `[data-pinecall-skip]` or `aria-hidden` is not read.
- **One at a time, or all**: `explain(what)` says the line of a thing marked `[has a line]`, the pointer
  on it; during a call a ▶ at the top right of a marked element under the mouse says it at once
  (`page.explain`); the walk `page`, listed with the agent's macros, says every line in order.
- **Said once.** The agent says a line through `say()`: it is the turn's answer, in the history, never asked again.

## What the page and the agent say to each other

| way | what |
|---|---|
| page → agent | `page.walked { walk, step, of, done }`, as a call opens after a walk played with no call |
| page → agent | `call.event("page.seen", { text, why, lines, at?, refused? })`, `lines` the site's `[{ at, say, do }]`, `at` the ref a move ended on when `why` is `moved`, `refused` why a field was not filled · `page.clicked { role, name }` · `page.missing { target }` · `page.explain { at }`, the ▶ pressed |
| agent → page | `pinecall.ui` `{ type: "cursor", action, target?, text? }`: a ref (`e22`) or a name as the screen shows it (`Questions`). The actions are `point`, `highlight`, `unhighlight`, `scroll_to`, `here`, `home`, and `type`, which writes `text` into the field |
| agent → page | `pinecall.ui` `{ type: "macro.step", macro, step, say, beats }` |
| agent → page | `pinecall.ui` `{ type: "look" }`: what the page shows now, answered with `page.seen` |

**Anybody can send what a browser sends.** The agent reads the page as the visitor's own words: a site
that shows other people's words (reviews, comments) puts them under `data-pinecall-skip`.
