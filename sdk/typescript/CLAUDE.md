# @pinecall/agents

The framework a tenant writes an agent in — a class whose fields are the state and whose `@tool`
methods are the model's verbs — and the serve entry the CLI starts it with. The CLI is
`../../cli` (npm `pinecall`), a package of its own in this repository that never imports this one
but through `@pinecall/agents/client` and `@pinecall/agents/wire`. Reply to the human in Spanish;
code, comments, commit messages and this file in English. What it is:
[ARCHITECTURE.md](ARCHITECTURE.md). How to build an agent with it: [docs/](docs/).

## Workflow

```bash
pnpm install                     # from the repository's root: every TypeScript package, one lockfile
pnpm test                        # the framework — from the sources
pnpm lint                        # tsc over src and test
pnpm --filter "@pinecall/example-clinica-norte" test   # the example, ../../examples/typescript
scripts/build                    # what is published: the wire's build, then dist/ (tsc) — no console in it
scripts/check                    # build → lint → test, in that order — what CI runs
pnpm vitest run test/agent       # one directory; `-t "a sentence"` for one test
cd ../../examples/typescript/clinica-norte && node ../../../cli/bin/pinecall.js chat   # the example, through the CLI's checkout
```

Nothing has to be built to lint or test: every package in the workspace exports its sources, and
`scripts/build` is only what gets published. The console is not here: it is `../../console`, a
folder of its own that the runtime builds into the gateway.

## Structure

- `src/` — seven directories, kept apart by the import table in `test/the-imports.test.ts`
  - `agent/` the class · `views/` JSX→text · `call/` the live call as a value
  - `client/` `@pinecall/agents/client`: the socket, and nothing above it · `runtime/` the bridge
  - `serve/` `@pinecall/agents/serve`: the entry the CLI starts an agent with — `start`, `prompt`
  - `wire/` `@pinecall/agents/wire`: the runtime's shapes, which the CLI reads too
- `test/` mirrors `src/`; `the-tree`, `the-imports`, `index` and `client/index` are the tree's rules
- `../../examples/typescript/` one tenant written the way a customer writes one — and what the nightly drives
- `docs/` how to build an agent · `docs/decisions/` the maintainer's notebook, **git-ignored**:
  a clone has no such directory, and a comment naming a page there points at a note. A page of
  the runtime's notebook is named as **the runtime's** `docs/decisions/<page>.md`, never bare

## Docs are part of the change

**A change lands with the page that describes it, in the same commit.** Not "later", not a TODO:
a page that describes what the tree no longer does is worse than no page, because somebody trusts
it. What to edit, by what you touched:

| you changed | edit |
|---|---|
| a module, a directory, an entity or its fields, a line of the import table, the path something takes between two parts | `ARCHITECTURE.md` — the section, and any table that lists the file |
| an install step, an export | `README.md` |
| what a tenant writes, renders or tests | `docs/` here (the package's own reference: the tutorial, the class, the view, testing, production — synced to the site's SDKs tab) and the site's pages in `../docs/pages/concepts/` and `../docs/pages/guides/`, which are written TypeScript first — `../docs/pages/STYLE.md` says how |
| anything a tenant would notice | `CHANGELOG.md`, one line under `Unreleased` |

Before committing a rename or a removal:
`grep -rn '<the old name>' ARCHITECTURE.md README.md CLAUDE.md docs` — a symbol
that moved is a stale sentence somewhere. When a doc and the code disagree, the code is what
happened and the doc is the bug.

## Rules the tests enforce

- No `.ts` at the repo root. No file over 400 lines. Every file opens with a line saying what it
  is. No two names in one directory one letter apart.
- The import table is the architecture: `client/` knows only the wire and `ws`; a line nobody uses
  is a line the test deletes.
- `test/index.test.ts` and `test/client/index.test.ts` pin the two public surfaces by name —
  never a CLI module, never a bridge internal, never a test helper.
- `package.json` exports point at `src/` and `publishConfig` swaps in `dist/`. The example
  resolves `@pinecall/agents` through `node_modules` like a customer; nothing is aliased or path-mapped.
- The wire is `src/wire/`, the runtime's shapes this package uses and no more; its golden call
  log is `test/wire/golden/`, copied from the runtime's `tests/wire/golden/`, so a log folded here
  is the one the runtime folds. A change of the runtime's wire moves both by hand.

## Comments and doc comments

The bar is an open-source library: plain technical English, and less prose than code.
- A comment says WHY, only when the code cannot: a constraint, a trap, an external fact. Never
  what the next line does. One line by default, three at most; more belongs in `docs/`.
- No history in code (dates, incidents, "until X this did Y"): that is the commit message.
- Public API keeps a concise doc comment a user reads in their editor; internals need none unless
  the name is not enough. No figures of speech.

## What a review comes back to

One definition per thing — `grep` before writing a constant, a parser, a helper. No dead code and
no code "for later": a symbol with no user outside its file and its test goes in the commit that
notices it. No module-level mutable state — per call, per mount, per request, or on the async
context (`AsyncLocalStorage`). One idea per file, named by the idea. A stale comment is a bug, and
so is a count inside one (`snapshot` drops "the config fields", not "the nine"). Names are
sentences; small methods; 150 lines is the norm. Tests read as sentences.

## Traps — each one cost an afternoon

- **The serve entry reads its door from `PINECALL_URL`, `PINECALL_KEY` and `PINECALL_ENV`**, and
  from nothing else: no `.env`, no flag. The CLI resolved them and set them on the child; a serve
  entry that read a file would serve another org than the one the CLI showed.
- **A tool with no docstring is refused,** because without one no model can choose it; and
  `@tool({ stage })` on a class with no `stage` field is refused too.
- **The class docstring lives above the class,** where `toString()` cannot see it, and parameter
  types are gone after compilation. `describe(ctor, source)` in `serve/load.ts` and `mount({source})`
  are the only reason the `identity` block has a first line and the tools have typed arguments.
- **Only a `dynamic` block may differ between two turns.** Re-sending identical text is a cache
  miss for nothing, and reordering the blocks breaks the prefix cache. A tenant's static block is
  called against props that throw on the first read, so "static reads no state" is an exception.
- **A view says what to do in THIS turn.** Two facts the examples paid for: a rule that lives only
  in the static prefix is read once and generically, and the rule for "the caller just named a
  slot" is the opposite of the one for "the caller just said yes".
- A release is a `v*` tag of the repository: the root's `release.yml` publishes every package at
  the one version the root's `scripts/version` writes. The last number goes up; each package's
  Unreleased section becomes that version's in the same commit.

## Commits

A subject line and a body that says why. `pnpm lint` and `pnpm test` exit 0 before a commit;
`scripts/check` before anything that touches the build or the console. `CHANGELOG.md` gains a line
under `Unreleased` for anything a tenant would notice.
