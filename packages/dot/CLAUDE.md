# dot — `@pinecall/dot`

`@pinecall/dot`: the talking dot. The page's side is its face and the tutor that walks a page with
a pointer of its own. The agent's side is `@pinecall/dot/agent`, the `Tutor` class an agent
extends. It stands on `@pinecall/room` (the page) and `@pinecall/agents` (the agent). Reply to the
human in Spanish; code, comments, commit messages and this file in English. What it is and how a
page and an agent use it: [README.md](README.md), which is also its docs page.

## Workflow

```bash
pnpm install          # from the repository's root
pnpm test             # the suite, from the sources: node, and happy-dom for face, page, pointer and tutor
pnpm lint             # tsc over src and test
scripts/build         # what is published: src/ into dist/
scripts/check         # build → lint → test, in that order — what CI runs
```

## Structure

- `src/wire/` what the page and the agent say to each other: the events, the cursor and macro
  messages, a macro file checked
- `src/face/` the face: the mouth and the motion pure, the ear and the drawing on the DOM
- `src/page/` the page as the agent reads it: roles, names, refs
- `src/pointer/` the person with a pointer: its layer, the flight, the mirrored hovers
- `src/tutor/` the tutor on a page: every move, the snapshots sent, and the macro player
- `src/agent/` `@pinecall/dot/agent`: `Tutor` and `macros()`, the one part that runs in Node
- `test/` one file per sentence it proves, mirroring `src/`. `the-tree`, `the-imports` and `index`
  are the package's rules

## Rules the tests enforce

- No file over 400 lines, the pages at the root included. Every `.ts` opens with a line saying what
  it is.
- The import table in `test/the-imports.test.ts` is the architecture: `wire/` is plain data, the
  page's parts know only the DOM and the room, and `agent/` is the one place Node and
  `@pinecall/agents` are named.
- `test/index.test.ts` pins the two public surfaces by name.

## What a review comes back to

A change lands with the README section that describes it, and a line in `CHANGELOG.md`, in the same
commit. The pointer never clicks, sends a form or leaves the page for the visitor; it types into a
field only what the visitor said, and never a password, a card, a file or a hidden field. A field's
value reaches the agent in the snapshot; a password's or a card's never does.
The page's words reach the model fenced, as data.

- **`Tutor`'s tools are described from its JSDoc.** The module hands its own source to
  `describe()`, because tsx strips comments from `toString()`. A tool without a docstring is
  refused when the agent loads.
