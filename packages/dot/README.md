# @pinecall/dot

The talking dot. A small face, a dot with eyes and a mouth, speaks with your agent's voice, moving
its mouth with the sound frame by frame. As a tutor it becomes one more person on the page, with a
pointer of its own: it walks the visitor through the site, hovers and highlights what it talks
about, and the agent's prompt reads the page as it is now.

It stands on [`@pinecall/room`](../room/README.md), which joins the call. The pinecall widget
draws it with `<pinecall-widget look="dot">`, and with `look="dot" tutor` the tutor too.

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

The face fills its element with one SVG: 64 px is a launcher, 240 px a hero. Two faces on one page
are fine.

**Its shape and colour.** `face(host, call, { shape, color })`: `shape` is `circle` (the default),
`squircle` or `blob`, and `color` any CSS colour (else the page's `--pc-face`). `reshape(shape)`
changes it later, the body easing from one into the other. The body moves with the mood: a slow
wobble round its rim while it listens, a lighter one while it thinks, and one that follows the voice
while it speaks; still under `prefers-reduced-motion`. Nothing is drawn outside the body, no halo
and no shadow, so it sits on any background. `tutor()` takes the same `shape` and `color`, which
tints its pointer too.

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
| `opening` | thinks: eyes up and away, a small round mouth to one side |
| `live`, the agent `listening` | listens: head tilted, eyes a little wider, the halo beating slowly |
| `live`, the agent `thinking` | thinks |
| `live`, the voice sounding | speaks: the mouth from the voice, the halo with its loudness |

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
for the other); touring, a pointer in its colour with the face beside the tip and what it says
beside the face. It moves the way a hand moves a mouse:

- **It aims at an element the way a person does.** It lands on the middle of the element's first
  words, not of its box, and flies there on a minimum-jerk path with a slight arc, timed by the
  distance.
- **The pointer looks like the one the element asks for**: a hand on a link, an I-beam in a field.
- **Hover looks real.** Every `:hover` rule of the site's own style sheets is mirrored onto
  `[data-pc-hover]`, set on the element under the tip and its ancestors, and `pointerenter` and
  `mouseenter` are sent for the site's code. A style sheet from another origin cannot be read and
  keeps no hover.
- **It scrolls the page eased**, until the element sits a little above the middle of the screen.
- **A highlight dims the rest of the page** and follows the element as the page scrolls. "Here" is a
  ring at the tip.

**It never clicks, sends a form or opens another page for the visitor.** It shows where, and they do
it. A form's fields it fills with what the visitor told it, typed letter by letter with the `input`
and `change` events the site's code listens for, a list by the option that says it; the visitor
presses its button. It never touches a password, a card number, a file or a hidden field.

**The conversation in writing, and the call's buttons.** The agent's words show beside the face,
lit as its voice says them; the visitor's, what the agent heard, show in the corner as they speak
and for `linger` ms after (2600 by default), one side at a time. `captions` chooses whose may show:
`both` (default), `agent`, `caller` or `none`. During a call two buttons sit beside the corner:
**CC**, which turns the words off and on for this visitor (kept in their browser's `localStorage`,
and absent with `captions: "none"`), and **✕**, which hangs up (`call.leave()`). `words: { hangUp,
captions }` names them for a screen reader.

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
  choice and its `(options …)`, `[checked]` or `[unchecked]`, so the agent sees what the visitor
  typed. Passwords, card numbers, and anything under `[data-pinecall-skip]` or `aria-hidden` are
  left out.
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
  seconds at most), and its result is that thing as the visitor now sees it, fenced as data: a
  section that was one line below the fold comes back in full, its prices with it, for the model to
  talk about.
- **`fill(field, text)` writes what the visitor said into a field**, after the agent asked for it,
  one field at a time; its result is the field as it now shows, and a field the page refused (a
  password, a list with no such option) is a tool error naming why. It never sends the form.
- **The page asked for as the call opens**: `onCall` sends `{ type: "look" }`, and the page answers with
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
- **`nth` picks which time a word is said**, from 1.
- **`macros()` checks every file when the class loads**, and refuses a beat on a word its sentence
  never says.
- **A model names a walk the way it heard it**: `runMacro("site tour")` runs `tour`, and an agent with one
  walk runs it whatever it is called (`walkNamed`).

How a macro runs. `runMacro("tour")` sends each step on `pinecall.ui`, then says it. The page binds
the step to the reply that follows and counts its words as the voice says them, the same word
timings room's karaoke lights words with. Each beat runs as its word starts. When the visitor
speaks, the walk stops and the agent answers them.

### Lines on the page

A walk can also live in the site's own markup, beside what it is about, so the HTML and what is
said never drift apart:

```html
<section id="pricing" data-pinecall-say="Pricing is simple: three plans, and most families pick Family Care." data-pinecall-do="highlight">
<article data-pinecall-say="Family Care covers up to four people for thirty-nine dollars a month." data-pinecall-order="2">
```

- **`data-pinecall-say` is said as written**, with the move `data-pinecall-do` names (`point`
  unless `highlight` or `scroll_to`), in `data-pinecall-order` and then in the page's order.
- **One at a time**: `explain(what)` says the line of a thing marked `[has a line]`, the pointer on
  it, when the visitor asks what it is; and during a call a ▶ shows at the top right of a marked
  element under the visitor's mouse, which says it at once (`page.explain`).
- **All of them**: the walk `page`, listed with the agent's macros, says every line in order.
- **Said once.** The agent says a line through `say()`, so it is the turn's answer, in the history:
  the model is not asked to answer it again, and the tool's result tells it the line is said.

Only the site's markup is read: a line under `[data-pinecall-skip]` or `aria-hidden` is not.

## What the page and the agent say to each other

| way | what |
|---|---|
| page → agent | `call.event("page.seen", { text, why, lines, at?, refused? })`, `lines` the site's `[{ at, say, do }]`, `at` the ref a move ended on when `why` is `moved`, `refused` why a field was not filled · `page.clicked { role, name }` · `page.missing { target }` · `page.explain { at }`, the ▶ pressed |
| agent → page | `pinecall.ui` `{ type: "cursor", action, target?, text? }`: a ref (`e22`) or a name as the screen shows it (`Questions`). The actions are `point`, `highlight`, `unhighlight`, `scroll_to`, `here`, `home`, and `type`, which writes `text` into the field |
| agent → page | `pinecall.ui` `{ type: "macro.step", macro, step, say, beats }` |
| agent → page | `pinecall.ui` `{ type: "look" }`: what the page shows now, answered with `page.seen` |

**Anybody can send what a browser sends.** The agent reads the page as the visitor's own words, and
a site that shows other people's words (reviews, comments) puts them under `data-pinecall-skip`
when the agent should not read them.
