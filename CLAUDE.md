# pinecall — the map

Every package of Pinecall, one folder each, released together at one version. **Each folder has its
own `CLAUDE.md`, and that file is the authority for it**; this page only says which one to open
and what holds across all of them. Code, comments, commit messages and pages are in English.

Three groups, named in one sentence: the parts of the product, the SDKs, the libraries.

| folder | what it is | its page |
|---|---|---|
| `runtime/` | the gateway and the worker (PyPI `pinecall-runtime`), the wire's source (`pinecall/wire/`) | `runtime/CLAUDE.md` |
| `cli/` | the `pinecall` CLI (npm `pinecall`), never imports the framework but through `client` and `wire` | `cli/CLAUDE.md` |
| `console/` | the page the gateway serves, both envs in it; built into the runtime's wheel | `console/CLAUDE.md` |
| `widget/` | one agent as one button on any page; served by the gateway | `widget/README.md` |
| `sdk/typescript/` | the TypeScript framework (npm `@pinecall/agents`) | `sdk/typescript/CLAUDE.md` |
| `sdk/python/` | the Python SDK (PyPI `pinecall`, import `pinecall`) | `sdk/python/CLAUDE.md` |
| `sdk/ruby/` | the Ruby SDK (gem `pinecall`) | `sdk/ruby/CLAUDE.md` |
| `packages/room/` | the caller's side of a call, for a page's own UI (npm `@pinecall/room`) | `packages/room/CLAUDE.md` |
| `packages/dot/` | **experimental**: the talking dot, its face, and the tutor that walks a page with a pointer, both sides (npm `@pinecall/dot`) | `packages/dot/CLAUDE.md` |
| `packages/core/` | what the console and the supervisor app stand on (`@pinecall/core`, never published) | `console/CLAUDE.md` |
| `examples/` | Clínica Norte, the one example agent, in each language (`typescript/`, `python/`, `ruby/`); and Brightside, the dot tutor's, in TypeScript | each example's `README.md` |
| `infra/` | the charts, the images and the Terraform a runtime is deployed with; the runtime's `Makefile` drives them | `infra/README.md` |

## What holds across the folders

- **One version.** `scripts/version` prints the version all seven published packages carry, or says
  which disagrees; `scripts/version X.Y.Z` writes it into all seven (and relocks the runtime). A `v*`
  tag publishes everything (`.github/workflows/release.yml`). Each package keeps its own
  `CHANGELOG.md`; its Unreleased section becomes the version's in the release commit.
- **A change that crosses folders lands in one commit**: the runtime's wire, the SDKs that read it,
  their tests and the pages that describe them.
- **The toolchains stay apart.** The TypeScript packages are one pnpm workspace (the root's
  `pnpm-workspace.yaml`, one lockfile); install from the root. `runtime/` and `sdk/python/` both
  ship the module `pinecall`, so each is its own uv project with its own `uv.lock`. `sdk/ruby/`
  has its Gemfile. A `pnpm -r` run from a folder reaches every package of the workspace: filter it
  (`--filter @pinecall/example-clinica-norte`).
- **CI** is `.github/workflows/check.yml`: each package's own check, run when its folder or a root
  it stands on changed.
- **Documents not written for the people who use Pinecall** — plans, briefs, notes — never enter
  this repository: everything tracked here is published with it.
