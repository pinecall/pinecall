# @pinecall/agents

Build voice and chat agents as TypeScript classes. Fields are the agent's state, `@tool`
methods are what the model can call, docstrings are the prompt, and `render()` describes the
current turn.

```tsx
/** You are the front desk of Clínica Norte. Formal, short sentences. */
export default class ClinicaNorte extends Agent {
  stage: Stages<"identify" | "choose" | "book"> = "identify";
  patient?: Patient | undefined;
  slot?: Slot | undefined;

  /** Finds the patient by name and phone. Ask for both before calling it. */
  @tool({ stage: "identify", pii: ["name", "phone"] })
  async findPatient(name: string, phone: string): Promise<Patient | null> {
    this.patient = await this.agenda().find(name, phone);
    if (this.patient) this.stage = "choose";
    return this.patient ?? null;
  }

  /** The prompt as a function of state: the only part that changes between turns. */
  override render() {
    return (
      <>
        {this.stage === "identify" && <p>Greet the caller and ask for their name and phone.</p>}
        {this.patient && <p>You are talking to {this.patient.name}, already on file.</p>}
      </>
    );
  }
}
```

The same agent answers the web, WhatsApp and the phone, and remembers a customer across them.
Audio, rooms, the call log and tenants are handled by the
[Pinecall runtime](https://github.com/pinecall/pinecall/tree/main/runtime), which this package talks to over a
WebSocket.

## Install

```bash
npm i @pinecall/agents   # in the project: the framework your agents are written in
npm i -g pinecall        # once per machine: the CLI, the same for TypeScript, Ruby and Python
```

The CLI is its own package, [`pinecall`](https://github.com/pinecall/pinecall/tree/main/cli), and never a dependency
of the project: it never loads this one, it starts the agents of your project through the
`@pinecall/agents/serve` your project pinned. It needs a gateway: use Pinecall's hosted one, or run your own with
[`pip install pinecall-runtime`](https://github.com/pinecall/pinecall/tree/main/runtime) (see
[Self-hosting](https://docs.pinecall.io/self-hosting/overview/)).

## Quick start

```bash
npm i -g pinecall
pinecall login               # sign this machine in through the browser, once
pinecall new acme --agent front-desk   # the project, and its first agent in agents/front-desk/
cd acme && npm install
pinecall chat                # talk to the agent in this terminal
pinecall test                # run its golden against a real model
pinecall start               # run the agent (this is the process you deploy)
```

The whole example, a clinic's receptionist with stages, a calendar and documents, from this
checkout:

```bash
pnpm install
npm i -g pinecall            # the CLI; the example takes the framework from this checkout
cd ../../examples/typescript/clinica-norte
pinecall login               # sign this machine in through the browser, once
pinecall chat                # talk to the agent in this terminal
pinecall start               # run the agent (this is the process you deploy)
pinecall console             # open the sandbox console
pinecall test                # run the goldens
```

Other useful verbs: `pinecall prompt --state <file>` prints the exact prompt a state produces
(`--channel web --medium text` for the one a written chat gets);
`pinecall docs push` uploads a knowledge base and `pinecall docs attach <base>` gives it to the
agent; `pinecall deploy` runs the project on Pinecall instead of your own server, with
`pinecall secrets` for what it is started with ([Deploy to Pinecall](https://docs.pinecall.io/guides/deploy/)). Every verb runs against the sandbox unless `--prod` is given. The CLI reads `PINECALL_KEY`
and `PINECALL_URL` from the environment or the project's `.env`. Full reference:
[docs/the-cli.md](https://github.com/pinecall/pinecall/blob/main/cli/docs/the-cli.md).

A project holds one or more agents: `agents/<name>/agent.tsx` and their tests in
`agents/<name>/test/`. Voice, model, language, greeting, knowledge and the documents an agent searches
are per-world settings (`pinecall agent set --language es`), unless the class declares them
itself — `@voice`, `@llm`, `@stt`, `@judge` and `static` fields — and then the class wins. Running in production on your own server:
[Run it on your own server](https://docs.pinecall.io/guides/own-server/).

## Development

```bash
pnpm test          # the framework, from sources
pnpm lint          # tsc over src and test
scripts/build      # the published build (dist/)
scripts/check      # build, lint, test — what CI runs
```

`package.json` exports point at `src/` and `publishConfig` switches them to `dist/` on publish,
so tests and the example run from sources with no build step.

| `src/` | |
|---|---|
| `agent/` | the `Agent` class, `@tool`, `@render`, `@state`, `@voice` · `@llm` · `@stt` · `@judge`, stages, hooks |
| `views/` | JSX-to-text rendering and the prompt's named blocks |
| `call/` | the live call as a value, reduced from log entries |
| `client/` | `@pinecall/agents/client`: the WebSocket client and the wire, nothing else |
| `runtime/` | the bridge between the class and the wire |
| `serve/` | `@pinecall/agents/serve`: the entry the CLI starts an agent with, `start` and `prompt` |

`test/the-imports.test.ts` enforces which directory may import which. The public exports are
`@pinecall/agents`, `@pinecall/agents/client`, `@pinecall/agents/serve`, `@pinecall/agents/wire` and
`@pinecall/agents/tsconfig.tenant.json`, pinned by
`test/index.test.ts` and `test/client/index.test.ts`.

The wire is the runtime's, kept in `src/wire/`; the runtime's golden call log, in
`test/wire/golden/`, is how this package and the runtime are checked to fold a log identically.

## Documentation

| | |
|---|---|
| [Tutorial](docs/tutorial.md) | forty minutes, from an empty directory to an agent with knowledge and memory, tested and shipped |
| [Writing an agent](docs/writing-an-agent.md) | the class: config, state, stages, tools, hooks, the call, the panel |
| [The view](docs/the-view.md) | the four blocks of the prompt, and `render()` |
| [Testing an agent](docs/testing-an-agent.md) | ring 0 with no network, no key and no model, and the rings above |
| [Production](docs/production.md) | `pinecall deploy`, `mount` in your own app, or `pinecall start --prod` |
| [ARCHITECTURE.md](ARCHITECTURE.md) | the package file by file |
| [docs.pinecall.io](https://docs.pinecall.io) | the product: agents, judges, goldens, the console, the CLI |

## License

[Apache-2.0](LICENSE), including its patent grant. No CLA.
