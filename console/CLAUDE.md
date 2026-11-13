# console

The console: ONE browser page, built here and served by the runtime's gateway at its one name,
both worlds in it — production at the root, the sandbox under `/sandbox` — on one sign-in.
Reply to the human in Spanish; code, comments, commit messages and this file in English.

This folder builds a bundle and publishes nothing to npm; it has no version and no tag of its own.
What ships of the console is `dist/`, copied into the gateway by the runtime's
`scripts/console` and carried to the cluster by the runtime's `make deploy`.

This folder is the page; `../packages/core` (`@pinecall/core`) is what it stands on, taken as source. Pinecall's supervisor app and its notifier live in a private repository of their
own, beside this one's checkout, and take `packages/core` the same way: a change to core is a change
to them too, so its exports are a contract.

## Workflow

```bash
pnpm install                  # from the repository's root: every TypeScript package, one lockfile
pnpm lint                     # tsc against the DOM — the gate, as there are no UI suites
pnpm build                    # vite → dist/ (the core is source: nothing to build)
pnpm check                    # build → lint, in that order — what CI runs
pnpm --filter @pinecall/core check        # the core's own, from anywhere in the workspace
pnpm --filter @pinecall/core exec vitest run test/the-stream-reads-sse-by-hand.test.ts
```

To see it in a browser, `pnpm --filter @pinecall/console dev` serves this checkout at
`localhost:5190` with the gateway's paths forwarded to production (`PINECALL_BOX` names another
box): sign in there as on the box. A gateway serving the built bundle is the other way: from the
runtime's checkout, `scripts/console && pinecall-runtime gateway`, then open the gateway's own URL. **A change here
reaches a box only through that copy** — until `scripts/console` runs, the box serves the bundle it
was deployed with, whatever this checkout says.

## Structure

- `src/` — the page: `main.tsx` boots it and routes it, and beside it one directory per page of
  the menu (`dashboard/`, `apps/`, `calls/`, `numbers/`, `monitors/`, `team/`, `box/` for the
  operator's, …), each with its `door.ts` (the gateway's answers it reads, as zod schemas), its
  page and its one stylesheet · `shell/` (the frame: the menu, the org picker, the page's head) ·
  `login/` (sign-in, sign-up, an invitation) · `lib/` (the page's own reading of the gateway: the
  world, the key, the org) · `ui/` (the kit: the side panel, every control, and `row-menu.tsx`, the menu a right click opens on a row of any list: a row that is a link gets what a link can do, and a page adds its own with `useRowMenu`). Its `vite.config.ts`
  builds `dist/`.
- `../packages/core/src/` — what any supervisor app stands on, imported as `@pinecall/core/<module>`
  and taken as SOURCE by the app's bundler (nothing here is compiled): `api.ts` (the fetch, the one
  place a header is spelled), `credentials.tsx`, `the-floor.ts` (`/.well-known/pinecall`, read
  before any key), `theme.ts`, `login.ts`, `signup.ts` (the sign-up doors; the screen draws them
  only where the floor says `signup`), `session-key.ts`, `whoami.ts` (who a key is, and the
  org's word), `members.ts` (an org's people, the `team` door), `agents.ts` (the agents held now,
  `GET /v1/agents`), `initials.ts`, the SSE reader `stream.ts` (`openSse` for any stream, `openLog` for a log's entries) and the hooks over it (`use-call`,
  `use-floor`, `log-pages`), the org's feed opened once per page (`feed.ts`) and `use-fed` over it — the one way a screen
  reads a door that changes: on open, when the feed speaks, and by a clock only while it is down — and `use-room-open`, the seat and the two that spend one
  (`use-listen`, `use-supervise`), `verbs.ts` (one verb onto a call, the desk's and the phone's),
  `calls.ts` (a row said the same in every app: live, wants a person, elapsed, who, a web
  visitor's short id, the cut by day, and whether a call is spoken or typed), `calls-search.ts` (a list's search: the sessions door's
  `q`/`before` paging when it answers a `total`, else by hand over the rows held),
  `metrics.ts`/`wire.ts`/`score.ts`, `scopes.ts`, and the palette `tokens.css`. What core may not
  know: the router, the world, the shell, a page — a module that needs one of them
  is the console's. Its `package.json` `exports` is the list.
- **What an app tells the core at its boot**, and nothing else is configured: WHERE THE GATEWAY IS —
  `Credentials.base`, the value every hook reads from context, and the same string handed to the
  doors that take no key (`login.ts`, `the-floor.ts`); `api.ts:gatewayUrl` builds every URL from
  it. The console says `"/"` (`lib/key.ts:API_BASE`), resolved against the page's own origin: the
  doors are at the root whichever world the page is, while the ROUTER's base is the world's
  (`lib/world.ts:WORLD_BASE`, `/sandbox` on the sandbox's page) — two bases, never one string. WHERE THE KEY
  IS KEPT — `sessionKeyIn(storage)`, a `KeyStorage` of three async calls (the console's is
  `localStorage`, in `lib/key.ts`). WHAT IT CALLS ITSELF — the `device` every login takes,
  the label the key carries in the org's key list (`lib/key.ts`: `"console"`).

## The one menu

`src/shell/menu.ts` is the menu: the same rows whichever agent, world or page. An agent is a page
that is opened (`/agents/<name>/<tab>`, `/apps/<name>/<tab>`), never a mode of the menu, and the
box's own pages are rows only for those who run it. `main.tsx` routes every row; an address it
does not know lands on the dashboard, and the addresses the CLI and an alert's mail still send
(`/a/<agent>`, `/settings/alerts`) are sent on to the page that has them now.

**The world is the path's first segment, read once per page.** One gateway, one name, holds both
worlds and a person's key opens both (production only where their org lets them). `/…` is
production's console and `/sandbox/…` the sandbox's — the same pages under the prefix, which is
the router's base; `lib/world.ts` reads it off `window.location` and every request names it in
`pinecall-env`. One sign-in, one card, for both.

## Rules

- **No key outside `lib/key.ts`, and no header written by hand.** One key — the person's — in
  `localStorage`, through that file alone; core's `api.ts:headersFor` puts it on every request
  with the world. Both worlds are one origin and so one key.
- **The bundle carries no credential.**
- One stylesheet per directory, and one class prefix per stylesheet.
- Every file opens with a line saying what it is.
- **The wire is core's own** (`../packages/core/src/wire/`): the runtime's shapes this page reads,
  and the reducer the call pages fold a log with. No package of the runtime's is read.

## What a review comes back to

One definition per thing — `grep` before writing a constant, a helper, a formatter. No dead code:
a page removed from the menu is a page deleted in the same commit. One idea per file, named by
the idea. A stale comment is a bug. Names are sentences; 150 lines is the norm. There are no UI suites: `tsc` against the DOM and a clean build are the gates.

## Traps

- **This page may never import the framework.** It knows its core, react, react-router,
  livekit-client, zod and vite, and nothing of `pinecall/agents`: none of the class, the views or
  the bridge would run in a browser.
- **An import nobody uses is a branch nobody wrote.** A feature once shipped half-made: one half
  went out, the half that ANSWERED it was never inserted — an edit that matched nothing and said so
  to no one — and the imports it needed sat there unused while the typecheck and the suite both
  passed. `noUnusedLocals` is on in
  every package, so tsc refuses the next one.
- **The bundle is not reproducible across installs.** vite's minifier (rolldown) is a transitive
  dependency, and a fresh install resolved 1.2.9 where the agents repo had 1.2.7: same sources,
  same production build, output 7% larger and shaped differently. Measured 2026-09-21. The
  lockfile is what makes a build repeatable — commit it, and bump on purpose.

## Commits

A subject line and a body that says why. `pnpm check` exits 0 before a commit.
