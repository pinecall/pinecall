# Changelog

All notable changes to `@pinecall/dot`. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers and tags are the
maintainer's call.

## Unreleased

- **The captions stay out of the code's way.** None show while a window of code is open, and CC sits in the
  corner during a walk too, the same choice as in a call. The walks' button stands in front of the face,
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
