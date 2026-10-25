# Changelog

All notable changes to `@pinecall/dot`. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers and tags are the
maintainer's call.

## Unreleased

## 0.11.24 — the walks' menu marks the walk of the section the visitor is on (2026-10-25)

## 0.11.23 — the resting face a little smaller and nearer its corner (2026-10-25)

- **The resting face is a little smaller and nearer its corner**: 58 px across (it was 64), its edge 14 px from the
  window's (it was 20), and its words, buttons, menu and card keep their distance from it.
## 0.11.22 — the face stays on a phone's screen as the page scrolls (2026-10-25)

- **On a phone the face stays on the screen as the page scrolls.** It let go of what it pointed at only after the
  scroll, so it rode off the top with it; and a section taller than the screen is shown from its start, not
  from its middle.
## 0.11.21 — the tutor's walks, its cards, and a face that hears and thinks (2026-10-25)

- **The walks' pills are smaller, and come four at a time**: a small ⌄ under them shows the next four, and back
  to the first from the last (`words: { more }`).
- **The card is larger, and the captions stay out of its way**, as they do for a window of code.
- **A project's own tools are drawn on a card.** `tutor(call, { views })` (the widget's `views` property) says,
  by tool name, how to draw a result: the free times, a booking form, a piece of code. The card stands above
  the face's corner when the tool finishes, and the visitor answers on it in writing (`tools.send`).
- **The walks' menu marks the walk of the section the visitor is on**, and opens on its page: a section names it with
  `data-pinecall-walk="<macro>"`, and the one across the screen's middle is the visitor's. Nothing is offered as
  the page scrolls. `data-pinecall-play="<macro>"` on a button the site draws (`hidden`) shows it while that walk
  can play, and plays it on a click. While the menu is open the mark follows the page as it scrolls.
- **The pointer stands under the words it points at**, not on them, and still hovers what it points at: a
  link keeps its hand.
- **The face hears and thinks.** While the caller speaks it nods with its head cocked and its eyes wide;
  while the agent thinks it looks up from side to side, its mouth pursed and sliding, "hmm". Waiting is as it was.
- **The captions start off.** The visitor turns them on with CC, in a call or a walk, and the choice is kept.
- **A walk can be paused.** While a walk plays the corner holds pause beside captions and stop
  (`words: { pause }`).
- **The captions stay out of the code's way.** None show while a window of code is open. During a walk CC sits in the
  corner with a stop button, the same choice as in a call; CC is an icon now, and the buttons slide into
  the face's corner while it tours, aside as it comes home. The
  walks' pills stand beside the face, the highest a gap from it. The walks' button stands in front of the face,
  where a click on it no longer began a call, and on the face's resting size, where the face back from a
  walk no longer covered it.
- **The face stands where it hides nothing.** Beside the tip it takes the side that fits the screen
  (right or left, below or above), and on a window of code the side clear of the lines being explained.
  The side is chosen for where the flight lands, before it leaves: the face no longer covers a section
  and then jumps above it.
- **A tab is read by its words and pointed at**, as a button is: a walk's beat on a tab found nothing.
  The pointer stays above a window of code, and lets go of a line whose window closed.
- **A walk explains code.** A step's `code` opens a window of it beside the page, coloured and written in a
  line at a time, and `lines` lights the lines its sentence is about while the pointer goes to them; a step
  that names no code keeps the window; `null` or the walk's end closes it, in a call too (`macro.done`).
  The walks' first pill is the highest.
- **A call no tutor's page joined is the agent's alone**: no screen in its view (it said "the page has
  not been seen yet" on every phone call), no pointer, and no page asked for off the web.
- **Walks the visitor plays with no call.** `Tutor` records each macro once in the agent's voice as
  the agent starts (`static onServe`) and publishes them as `walks`; `tutor({ walks })` puts a button
  beside the face whose pills play one, the mouth, the words and the pointer on its audio. A macro
  takes a `title`. A call afterwards hears what was played (`page.walked`).
- **Marked an experiment**: an add-on of Pinecall, whose API may change in any release.
- **First release.** `face(element, room)`: a dot that speaks with the agent's voice. Its mouth is
  read from that voice frame by frame, and its mood follows the agent's state.
- **`tutor(room, options)`**: one more person on the page, with a pointer of its own.
  - It points, highlights, scrolls, shows where to click and goes home, and never clicks or types
    for the visitor.
  - It sends the page as the agent reads it (`page.seen`) when it changed.
  - It runs a macro's moves on the words the agent says.
- **`Page`**: the page as Playwright's aria snapshot reads it, with stable refs, and no field values.
- **`@pinecall/dot/agent`**: `Tutor`, the class an agent extends. It gives the page in the view,
  the pointer's tools and `runMacro`. `macros()` checks the macro files of the agent's folder.
- The pointer's tools are `quiet`, and the agent asks for the page as its call opens (`look`).
- **A move onto a thing is answered with what the visitor sees there.** `point`, `highlight` and
  `scrollTo` wait for the page to say the move ended (`page.seen` with `why: "moved"` and `at`), and
  return the thing as it now shows, so a model that moved in silence has something to say.
- **The face takes a shape and a colour, and moves as it listens.** `shape` (`circle`, `squircle`,
  `blob`) and `color` on `face()`, `tutor()` and the widget; `reshape()` eases from one shape into
  another. The whole body bobs while it listens and squashes with the voice, its outline never bent. The halo and the drop shadow that
  reached past the dot are gone.
- **The site's own lines, said as written.** `data-pinecall-say` on an element (with
  `data-pinecall-do` and `data-pinecall-order`) is a line the agent says about it: one at a time
  with `explain`, or with the ▶ shown on it under the visitor's mouse, all of them as the walk
  `page`. A line said is the turn's answer, never said again.
- **The tutor fills a form with the visitor.** `fill(field, text)` types what they said into a
  field, a list by its option; it never sends the form, and never touches a password or a card.
  The snapshot now says what each field holds, and a list's options.
- **The tutor writes both sides of the conversation, and hangs up.** The visitor's words show in
  the corner as they speak, beside the agent's; `captions` (`both`, `agent`, `caller`, `none`)
  chooses whose may show, and a **CC** button lets the visitor turn them off, kept in their browser.
  A **✕** beside it hangs up.
- **The snapshot says the words of a box that is only layout**, as a price in a `<div>`: they were
  left out, and a model asked about a plan could not see its price.
