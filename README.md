# Pinecall

[![check](https://img.shields.io/github/actions/workflow/status/pinecall/pinecall/check.yml?branch=main&label=check&logo=github&style=flat-square)](https://github.com/pinecall/pinecall/actions/workflows/check.yml)
[![release](https://img.shields.io/github/v/tag/pinecall/pinecall?label=release&color=9184d9&style=flat-square)](https://github.com/pinecall/pinecall/tags)
[![docs](https://img.shields.io/badge/docs-docs.pinecall.io-9184d9?style=flat-square)](https://docs.pinecall.io)

Voice and chat agents written as a class, on the phone, in the browser, in chat and on WhatsApp.
This repository holds the runtime that runs the calls, the console it serves, the SDKs an agent is
written with, and the CLI that drives them. Every package is released together, at one version, by
one tag.

| folder | what it is | published as |
|---|---|---|
| [`runtime/`](runtime) | the gateway that answers every door of the API and the worker that runs the calls, on LiveKit | [`pinecall-runtime`](https://pypi.org/project/pinecall-runtime/) on PyPI |
| [`cli/`](cli) | the `pinecall` CLI, the same for every language | [`pinecall`](https://www.npmjs.com/package/pinecall) on npm |
| [`console/`](console) | the page the gateway serves, both environments in it | inside `pinecall-runtime` |
| [`widget/`](widget) | one agent as one button on any page | inside `pinecall-runtime` |
| [`sdk/typescript/`](sdk/typescript) | the TypeScript framework an agent is written in | [`@pinecall/agents`](https://www.npmjs.com/package/@pinecall/agents) on npm |
| [`sdk/python/`](sdk/python) | the Python SDK | [`pinecall`](https://pypi.org/project/pinecall/) on PyPI |
| [`sdk/ruby/`](sdk/ruby) | the Ruby SDK | [`pinecall`](https://rubygems.org/gems/pinecall) on RubyGems |
| [`packages/room/`](packages/room) | the caller's side of a call, for a page's own UI | [`@pinecall/room`](https://www.npmjs.com/package/@pinecall/room) on npm |
| [`packages/core/`](packages/core) | what the console and Pinecall's supervisor app stand on | nothing: taken as source |
| [`examples/`](examples) | the one example agent, Clínica Norte, in each language | nothing: what the nightly drives |
| [`infra/`](infra) | the charts, the images and the Terraform a runtime is deployed with | nothing: `make deploy` from `runtime/` releases them |

Each folder's `README.md` says what it is and how to use it; the docs are at
[docs.pinecall.io](https://docs.pinecall.io).

## Working on it

```console
$ git clone https://github.com/pinecall/pinecall && cd pinecall
$ pnpm install          # every TypeScript package, one workspace and one lockfile (Node 24, pnpm 11)
$ cd runtime && uv sync # each Python package is a project of its own, with its own uv.lock
```

The TypeScript packages share the root's workspace (`pnpm-workspace.yaml`). `runtime/` and
`sdk/python/` both ship the module `pinecall`, so they are never one environment: each keeps its
own `uv.lock`. `sdk/ruby/` has its Gemfile. Each package's own check is what CI runs for it
(`.github/workflows/check.yml`), only when its folder changed.

## Releasing

Every published package carries the same version. `scripts/version` prints it, or says which
package disagrees; `scripts/version X.Y.Z` writes it into all six. A `v*` tag publishes them all
(`.github/workflows/release.yml`), each registry by Trusted Publishing, and a GitHub Release whose
notes are each package's `CHANGELOG.md` section for that version.

## Security

[SECURITY.md](SECURITY.md).
