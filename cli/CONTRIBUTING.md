# Contributing to the CLI

This package is written to one convention, so that anybody who knows the convention knows where
every line lives before they open the tree. The convention is held by `test/conventions/`: a
file in the wrong place, a layer that imports upwards, a `fetch` outside `api/` or a word from the
banned list fails the suite, not a review. It is the CLI's half of the runtime's
`CONTRIBUTING.md`: the domains carry the same names, so an endpoint, the service that answers it
and the verb that asks for it share a word.

## The layout

```
src/
  main.ts          the entry: the program is run, and every error becomes one sentence and an exit code
  program.ts       the command tree on one screen: the global flags, one `register` call per domain
  context.ts       Context: what a verb runs with, resolved on first use
  errors.ts        PinecallError and its three kinds
  kit/             the toolkit: no business noun in it (io, table, format, dotenv, git, tarball…)
  api/             the gateway: client.ts and one module per domain; the only place `fetch` and `/v1/` appear
  project/         the tenant's folder: credentials, layout, language and serve entry
  <domain>/        a bounded context, always the same files (below)
  dev/             the engine: `start` and `console` — the serve child, the companion socket, the handlers
  mcp/             the MCP server: tools per domain over the domains' services
test/              mirrors src/; test/conventions/ holds this page, test/support/ the fake gateway (msw)
                   and the runner, test/help/ every --help as the CLI prints it
```

## A domain's files

Every domain folder holds these and nothing else. A file that would be empty is left out; the
names never change.

| file | holds | imports (of ours) |
|---|---|---|
| `service.ts` | the use cases, as functions `(ctx, input) → data`; each input a zod schema; the domain's own errors | `api`, `project`, `kit`, `errors`, `context`, other domains' `service` |
| `render.ts` | data → lines for a terminal; pure | `kit/format`, `kit/table`, a lower domain's `render` for a mark written the same way |
| `commands.ts` | `register(program, ctx)`: flags → input → one service call → `ctx.io.result(data, render)` | `service`, `render`, `context`, `kit/flags`, a lower domain's `render` |

A `service.ts`, `render.ts` or `commands.ts` that outgrows one module becomes a folder of the same
name, one module per noun (`evals/service/goldens.ts`, `evals/commands/dataset.ts`), with an
`index.ts` naming what the rest of the tree uses.

`dev/` and `mcp/` are engines and hold modules of their own. `dev/`: `child`, `serving`, `screen`,
`screens`, `console`, `start`, `companion`, `render`, `commands` and `handlers/` (the console's
screens). `mcp/`: `server`, `session`, `tool`, `instructions`, `scrub`, `site`, `commands`,
`tools/` (one module per domain, over its service), `install/` and `agent-host/` (an agent held in
a thread). An engine module may read `api/`; a tool never does.

The domains, bottom up; a domain imports a domain below it — its `service`, or its `render` for a
shared mark — never one above, and never another's `commands`:

```
billing · accounts · providers · agents · knowledge · telephony · judging · calls · evals · hosting · alerts · scaffold
· dev · mcp
```

## The twelve rules

1. **Canon.** A domain folder contains only `commands`, `service` and `render`, each a module or
   a folder of them.
2. **Layers.** `commands` and `mcp/tools` import `service` and `render`, never `api/`. `service`
   never imports `commands`, `render` or `mcp`. `api/` imports `kit`, `errors` and the SDK's
   `wire` and `client` only. No cycles.
3. **The gateway at home.** `fetch(` and the literal `/v1/` appear only in `api/`.
4. **Output at home.** `process.stdout`, `process.stderr` and `console.` appear only in
   `kit/io.ts`; `process.exit` nowhere (`main.ts` returns the code). A service never prints:
   it returns data, and the command renders it. Two files are other programs and exempt:
   `kit/ear.ts` (spawned to play a call) and the code `mcp/agent-host/thread.ts` runs in a thread.
5. **Shapes.** A shape the gateway answers is declared once, in `api/<domain>.ts` or imported
   from `@pinecall/agents/wire`; an input is a zod schema in `service.ts`, read by the command
   and by the MCP tool alike.
6. **Errors.** Everything thrown is a `PinecallError`: `UsageError` (exit 2: the arguments or
   the settings), `GatewayError` (exit 1: the gateway refused), `Cancelled` (exit 130), or a
   plain `PinecallError` (exit 1: a check failed). Only `main.ts` maps them.
7. **`--json`** on every verb that answers data: one object on stdout. Results go to stdout;
   everything a person reads while waiting goes to stderr.
8. **Boring names.** Modules are nouns, functions are `verbObject`, types are singular nouns.
   The vocabulary below names one word per concept; the banned words are a test.
9. **Size.** A module is at most 400 lines; `main.ts` and `program.ts` at most 150.
10. **Never the framework.** `src/` imports `@pinecall/agents/client` and `@pinecall/agents/wire`,
    never `@pinecall/agents` bare and never `/serve`: a class runs in its serve entry, started as
    a child whose door is in its environment and never in its argv. Nothing listens on a port.
11. **Tests mirror the tree**, fake the gateway at HTTP (msw, `test/support/gateway.ts`) and never
    a module of ours, and pin every `--help` as a snapshot (`test/help/`, `pnpm test -u` to rewrite
    one a change meant). A service is tested by what it sends and reads; a verb by `run([...])`.
12. **Comments say why.** A docstring is one line and says what. A comment is written only for a
    fact, a trap or a reason.

## The vocabulary

| say | never | means |
|---|---|---|
| gateway, `GatewayClient` | door, `theDoor`, `Door`, `Open`, `Held` | the URL and key a verb talks to |
| env (`sandbox`, `production`) | world | one of an org's two environments |
| `get`, `post`, `request` | `asked`, `knocked` | |
| `GatewayError` | `Refused`, `Refusal`, `refusal()`, `CannotRun` | |
| `Context` | `Numbering`, `Turning`, `Wording`, any `-ing` options bag | what a verb runs with |
| `listX` / `getX` / `createX` / `updateX` / `deleteX` / `formatX` | `linesOf`, `said`, `brought`, `bought`, `dropped`, `kept`, `shown`, the past participle | a function |
| `NumberRoute` | `Door_` | |
| `credentials` | `keyFrom` | |
| `entry` | — | one line of a call's log (kept) |
| `corner`, `world` | — | the wire's own words, read off its shapes (`answer.world`); a name of ours says `env` |
| `standing` | — | the version of a settings row or a lexicon that stands now |

A name that is a sentence (`a_blank_is_not_a_change`) is a comment, not a name.

## Commands

```
pnpm install            from the repository's root
pnpm lint               tsc over src and test
pnpm test               the suite (on the test machine, never on a laptop)
scripts/build           dist/
scripts/check           build → lint → test, what CI runs
```
