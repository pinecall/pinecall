# pinecall

The CLI for [Pinecall](https://pinecall.io) agents: link a project to your org, print the prompt a
state produces, chat with the agent in a terminal, run its goldens, and start the process that
answers its calls — for an agent written in TypeScript
([`@pinecall/agents`](https://github.com/pinecall/pinecall/tree/main/sdk/typescript)) or Ruby
([`pinecall` gem](https://github.com/pinecall/pinecall/tree/main/sdk/ruby)).

## Install

```bash
npm i -g pinecall                 # once per machine, whatever the agent is written in
```

The CLI never loads your class. It starts your project's own serve entry — `@pinecall/agents/serve`
for TypeScript, `Pinecall::Serve` for Ruby, `python -m pinecall.serve` for Python — and drives it
through the gateway, so the SDK that runs is the version your project pinned. A project depends on
its SDK, never on this CLI.

## Quick start

```bash
pinecall new front-desk          # or --ruby, --python: a project of one agent, ready for every verb below
cd front-desk && npm install     # bundle install for Ruby, uv sync for Python
pinecall link        # sign in through the browser; writes your key to ./.env
pinecall prompt      # the prompt the model reads, offline; --state <golden> for another state
pinecall chat        # talk to the agent in this terminal
pinecall test        # run the goldens
pinecall start       # run the agent: the process you deploy
pinecall deploy      # or let Pinecall run it
pinecall mcp install # or do all of it from Claude Code, Codex, Cursor…
```

Every verb acts in the sandbox unless `--prod` is given. The CLI reads `PINECALL_KEY` and
`PINECALL_URL` from the environment or the project's `.env`.

| | |
|---|---|
| [docs/quickstart.md](docs/quickstart.md) | nothing to an agent that answers, in ten minutes |
| [docs/the-cli.md](docs/the-cli.md) | every verb |
| [docs/the-mcp.md](docs/the-mcp.md) | `pinecall mcp`: the same CLI as an assistant's MCP server, and `mcp install` |
| [Deploy to Pinecall](https://docs.pinecall.io/guides/deploy/) | `pinecall deploy`: Pinecall installs and runs your project |
| [ARCHITECTURE.md](ARCHITECTURE.md) | the CLI file by file |

## Development

```bash
pnpm install         # from the repository's root: links ../sdk/typescript, the framework of the same commit
pnpm test
pnpm lint
scripts/check        # build, lint, test — what CI runs
```

## License

[Apache-2.0](LICENSE), including its patent grant. No CLA.
