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
