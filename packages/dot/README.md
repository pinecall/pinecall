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

**It never clicks or types for the visitor.** It shows where, and they do it.

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
      - button "Choose Family Care" [ref=e16]
  - region "Book your first visit" [ref=e18] (below)
```

- **What is on the screen is there in full. A section out of view is one line**, its name and
  `above` or `below`.
- **A ref is stable for the page's life**, and still names its element after a scroll took it off
  the screen.
- **A field is its label, never its value.** Passwords, card numbers, and anything under
  `[data-pinecall-skip]` or `aria-hidden` are left out.

The tutor sends it as `page.seen` when the call goes live, when a scroll stops, on a resize, when
the DOM changes (a question opened, a tab), on a click, and before each of the agent's moves. It
is sent only when it changed.

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
- **The pointer's tools**: `point`, `highlight`, `unhighlight`, `scrollTo`, `here`, `home`, `goTo` (same site only)
  and `runMacro`. They show once the page has been seen.

A class that overrides `onEvent` calls `super.onEvent(name, data, meta)` first.

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

How a macro runs. `runMacro("tour")` sends each step on `pinecall.ui`, then says it. The page binds
the step to the reply that follows and counts its words as the voice says them, the same word
timings room's karaoke lights words with. Each beat runs as its word starts. When the visitor
speaks, the walk stops and the agent answers them.

## What the page and the agent say to each other

| way | what |
|---|---|
| page → agent | `call.event("page.seen", { text, why })` · `page.clicked { role, name }` · `page.missing { ref }` |
| agent → page | `pinecall.ui` `{ type: "cursor", action, ref?, url? }`. The actions are `point`, `highlight`, `unhighlight`, `scroll_to`, `here`, `home` and `go` |
| agent → page | `pinecall.ui` `{ type: "macro.step", macro, step, say, beats }` |

**Anybody can send what a browser sends.** The agent reads the page as the visitor's own words, and
a site that shows other people's words (reviews, comments) puts them under `data-pinecall-skip`
when the agent should not read them.
