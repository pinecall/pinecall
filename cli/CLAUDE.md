# cli — the `pinecall` CLI

The `pinecall` CLI: every verb a tenant types, for an agent written in any language. It never
loads a class — it starts the agent's language's serve entry in a child process and drives it
through the gateway. Reply to the human in Spanish; code, comments, commit messages and this file
in English. The convention: [CONTRIBUTING.md](CONTRIBUTING.md). File by file:
[ARCHITECTURE.md](ARCHITECTURE.md). Every verb: [docs/the-cli.md](docs/the-cli.md).

## Workflow

```bash
pnpm install                     # from the repository's root: every TypeScript package, one lockfile
pnpm lint                        # tsc over src and test
pnpm test                        # the suite — on the test machine, never on a laptop
scripts/build                    # what is published: dist/ (tsc)
scripts/check                    # build → lint → test — what CI runs
node bin/pinecall.js --help      # the CLI from its sources, through tsx
cd ../examples/typescript/clinica-norte && node ../../../cli/bin/pinecall.js prompt --state <golden>
```

The framework is `@pinecall/agents`, `workspace:^` in `dependencies`: the root's workspace links
`../sdk/typescript`, so nothing is built to test, and `pnpm pack` writes the range npm resolves.

## Structure

One convention, held by `test/conventions/`: `main.ts` (the one error handler), `program.ts` (the
command tree), `context.ts`, `errors.ts`, `kit/` (no business noun), `api/` (the only `fetch` and
`/v1/`), `project/` (the tenant's folder), one folder per domain with `commands` · `service` ·
`render`, `dev/` (the engine behind `start`) and `mcp/` (the server, its tools over the domains'
services). CONTRIBUTING.md has the twelve rules and the vocabulary; read it before adding a file.

## Docs are part of the change

**A change lands with the page that describes it, in the same commit.**

| you changed | edit |
|---|---|
| a module, a folder, what the child is started with | `ARCHITECTURE.md` (its table is one row per file, the file's first line) |
| the convention itself | `CONTRIBUTING.md`, and the test in `test/conventions/` that holds it |
| a verb, a flag, an exit code, a refusal | `docs/the-cli.md` — and `../docs/pages/guides/deploy-to-pinecall.md` for `deploy` and `secrets`; its `test/help/<group>.txt` (`pnpm test -u`, the diff read) |
| an MCP tool: its schema, its manual, a stage | `scripts/mcp-pages` rewrites `docs/mcp/` (the suite fails a stale page); `docs/the-mcp.md` by hand |
| an install step | `README.md` |
| anything a tenant would notice | `CHANGELOG.md`, one line under `Unreleased` |

## Rules the tests enforce

The twelve of CONTRIBUTING.md. The ones that cost the most: `fetch(` and `/v1/` only in `api/`;
`process.stdout`, `process.stderr` and `console.` only in `kit/io.ts`; a service never prints; a
`commands` or `mcp/tools` module never imports `api/`; nothing imports `@pinecall/agents` bare or
`/serve`; nothing listens on a port; no file over 400 lines; every file opens with one line saying
what it is.

## Traps — each one cost an afternoon

- **A test's home is `PINECALL_HOME`, not `HOME`** (`accounts/service/home.ts` reads that variable,
  else `os.homedir()`): `test/support/` sets it to a folder of the test's own, or a test signs the
  real machine in. `mcp install` takes its home as an argument for the same reason — never run it
  through `run([...])`.
- **`reportOf` writes reproductions under the process's cwd**, as a person's terminal is: a suite
  test whose run broke would write into the checkout. Test `writeReproductions` with a folder of
  its own.

- **The CLI reads `PINECALL_KEY` and `PINECALL_URL`, and the local runtime's file** (`project/credentials.ts`):
  from the process's environment, else from the nearest `.env` up from the cwd, else
  `~/.pinecall/local.json`, which `pinecall-runtime setup` writes (a key of the org `default` on
  `http://127.0.0.1:8080`). v1's `PINECALL_API_KEY` is never read, and there are no profiles:
  another org is another folder.
  `--prod` on any verb acts in production for that one command; the `pinecall-env` header says which.
- **The child gets its door in its environment, never its argv** (`dev/child.ts`): an argv is read
  by every process on the machine.
- **A TypeScript agent is served by the project's own `@pinecall/agents`**, resolved from the
  project's root (`project/language.ts`); `pinecall mcp` alone lends its own to the agent's thread
  (`mcp/agent-host/framework.ts`), never as a link in the project's `node_modules`.
- **The child is detached, and its stdin ending means drain.** The first SIGINT/SIGTERM is passed on
  once, as SIGTERM; a second, or 40 s, kills it. `main.ts` raises a signal again after 1.5 s only
  when nothing else handles it, so a verb stuck in a fetch still stops on Ctrl-C.
- **`--prod` and `--json` are the root's options and may come anywhere** on the line: do not
  enable commander's positional options, which would require them before the verb.
- **zsh `noclobber`**: `cat > file` refuses to overwrite. `>|`.

## Commits and releases

A subject line and a body that says why. `pnpm lint` and the suite exit 0 before a commit.
A release is a `v*` tag of the repository: the root's `release.yml` publishes every package at
the one version the root's `scripts/version` writes. The last number goes up; each package's
Unreleased section becomes that version's in the same commit. The framework is published before
the CLI.
