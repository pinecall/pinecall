# Changelog

**Experimental**: anything here may change or go in any release. All notable changes to `@pinecall/dot`. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers and tags are the
maintainer's call.

## Unreleased

- **A chat's answer is read aloud as it came**: after the press that drew it out (a question typed, a call opened), each
  turn marked `data-pinecall-said="agent"` is said pointing at it, before the notes on the chat.
- **A page read aloud starts from the part in view**: with the top scrolled away, the reading begins at the first part
  not above the screen (`fromHere`), so coming back to the middle of a chapter goes on from there.
- **A page read aloud talks to a chat until it has what it came for**: a send button marked `data-pinecall-goal` is a
  chat the dot talks to; it asks the door for its line (`{ next }`: Pinecall's caller through the gateway's
  `/v1/evals/caller`, with `voicing.next`), says it in its own voice, types and sends it, reads the agent's answer
  aloud (each turn marked `data-pinecall-said`), and goes on until it said goodbye, the chat ended or forty turns
  passed; the whole chat is then explained. The reading's text helpers moved to `tutor/text.ts`.
- **A page read aloud types its own example, and reaches into the site's frames**: a field marked `data-pinecall-type`
  is typed with its value and the `data-pinecall-press` after it sends it, in any form (the page's own example, not the
  visitor's); a frame of the site's own (a chat in an iframe) is read in its place, what its page marks
  `data-pinecall-read`, the pointer, the light, the scroll and the wait reaching into it.
- **Typing to the dot: one thing done, never a conversation.** With `tutor(call, { ask, onTalk })` the walks' menu
  has a field; what is typed goes to the site's server, which decides with `@pinecall/dot/server`'s `decide()`
  (Jev, through OpenRouter's Decisions API), and the dot plays a walk or lights and points at a thing, with no call.
  A question a person answers is offered to the agent (`onTalk`).
- **A macro is a function.** `params` it is called with fill the `{slots}` of its sentences; steps act on the page:
  `fill` a field with the visitor's words, `press` a button (outside any form, or in a search form), `wait` for what
  it changed, `read` a table's row (`{hit.Time}`); `if` and `unless` keep a step for a value. In a call the model
  passes the params to `runMacro`, and a table read is handed back to answer from; typed to the dot, the site's door
  (`@pinecall/dot/server`'s `answer()`) picks them out of what was typed, picks the row, and records a sentence
  with slots in the agent's voice when it is reached. A walk with params is asked for, not listed in the menu.
- **A page read aloud.** `tutor(call, { reading })` reads what the page marks `data-pinecall-read`, part by part as
  written, in the agent's voice with no call: the part read lit and pointed at, the rest dimmed, an example marked
  `data-pinecall-press` pressed and its output (`aria-controls`) waited on. Each part is recorded by the site's door
  (`{ read }`), which a site allows with `voicing.read`. `tutor.read()` starts it.
- **A lone walk plays from its button**: with one walk and no field to type in, the button beside the face plays it.
- **An output no note covers is explained by the agent's model**: a button marked `data-pinecall-explain` has its
  output (what it controls, `aria-controls`, even when the page says nothing after the press) sent to the site's door
  (`{ explain }`, the gateway's `/v1/agents/{slug}/explain`, with `voicing.explain`) once it answered, and the notes
  that come back are read as the page's would be, in the place of its `data-pinecall-then` (said when the model gives
  none: both would say what the output shows).
- **An output is read line by line**: `data-pinecall-notes` on an example's button names notes that each find a line of
  its output (`data-pinecall-find`) and say what it means; the line is lit and pointed at, the output marked
  `data-pinecall-reading` meanwhile. The pointer scrolls through nested boxes: a line into its output, the output into the page.
- **A page is read as written to be heard**: an element's `data-pinecall-say` is said instead of its text (nothing inside
  it read again), an example's `data-pinecall-then` is said pointing at its output once it answered, and the pointer
  stands at the left of the part read, the face in the margin, its arrow turned toward the text.
- **A walk goes back and on a sentence**: the corner has back and next beside pause and stop, all in one small pill
  (26 px buttons instead of 34). Going on does a step that acts; going back passes it over.
- **The page scrolls in its own box**: an app whose content scrolls in a pane, not the window, is scrolled there.
- **A table reads as rows**: the snapshot names each row by its cells (`row "Tue, Oct 28 · 9:00 · Dr. Patel"`),
  with a ref the pointer can light.
## 0.11.24 — walks for each page, the menu that marks your section, the header kept clear (2026-10-25)

- **What the tutor scrolls to sits below the site's own header**, not under it: the top a fixed or sticky bar covers
  (or the page's `scroll-padding-top`) is measured and left out, and a thing under the header is not on the screen.
  A thing that fits the screen is shown whole, never cut to stand at its spot, and a longer one starts just under
  the header, so as much of it as fits is seen.
- **A walk can be for some pages**: a macro's `pages` (`["/security"]`) is published with its walk, the menu lists only
  the walks for the page it is on, and a call is told the page's path (`page.seen`'s `path`) and offers and runs only
  the walks for it. A walk that names no page is for every page. Each page has a document of its own (`walks`,
  `walks-security`): a document is 64 KiB at most, and a visitor reads only their page's.
- **Two guides for whoever builds a tutor**: `docs/write-a-tutor.md` (the agent, the page, walks, views for an
  agent's own tools, shipping it) and `docs/macros.md` (the format of a macro, the moves, naming elements,
  writing sentences that play well). They ship in the package.

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
