# Changelog

All notable changes to `@pinecall/dot`. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers and tags are the
maintainer's call.

## Unreleased

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
- **The tutor writes both sides of the conversation, and hangs up.** The visitor's words show in
  the corner as they speak, beside the agent's; `captions` (`both`, `agent`, `caller`, `none`)
  chooses whose may show, and a **CC** button lets the visitor turn them off, kept in their browser.
  A **✕** beside it hangs up.
- **The snapshot says the words of a box that is only layout**, as a price in a `<div>`: they were
  left out, and a model asked about a plan could not see its price.
