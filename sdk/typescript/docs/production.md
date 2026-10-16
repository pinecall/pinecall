# Production

How a TypeScript agent runs where its callers reach it. There are three ways: Pinecall runs it for
you, it runs inside the Node app you already have, or it runs as a process of its own.

## The server's token

A server runs on a **server's token**, minted for production in the console (Settings ▸ Tokens) or
with `pinecall keys`. It was made for one world and opens that one alone: put it in the server's
secrets as `PINECALL_KEY`, never in the repository. A person's key works too while their
production switch is on, but a server should not run on a person.

## (a) Pinecall runs it: `pinecall deploy`

```bash
pinecall deploy --prod
```

`pinecall deploy` uploads the project; Pinecall installs it from its lockfile and starts it with
its own `pinecall start`, in a sandboxed container of its own, on a token it minted for the app.
The project lists `@pinecall/agents` under `dependencies` and nothing of the CLI: the version of
the framework the lockfile pins is the one that serves the agent. Secrets are `pinecall secrets`;
logs, releases and rollbacks are `pinecall deploy logs`, `releases` and `rollback`.
[Deploy to Pinecall](https://docs.pinecall.io/guides/deploy/) is the whole of it.

## (b) Inside your own Node app

When the app is already a Node process that stays up, the agent can live in it. `mount` registers
the class on a client of its own; `drain` hands the live calls to the next holder:

```tsx title="server.ts"
import { readFileSync } from "node:fs";

import { mount } from "@pinecall/agents";
import { Pinecall } from "@pinecall/agents/client";

import FrontDesk from "./agents/front-desk/agent.js";

const pc = new Pinecall({ url: "https://cloud.pinecall.io", apiKey: process.env.PINECALL_KEY });
mount(FrontDesk, { pc, source: readFileSync(new URL("./agents/front-desk/agent.tsx", import.meta.url), "utf8") });
await pc.connect();

process.on("SIGTERM", () => void pc.drain().finally(() => pc.close()));
```

`new Pinecall` reads nothing from the environment: the app hands it the gateway and the key it
keeps. A person's key would need `env: "production"`; a server's token needs nothing. `source` is
the agent file's own text: compiling removes the class docstring and the tools' parameter types,
and this is how they come back, so ship the `.tsx` beside your build.

## (c) `pinecall start --prod`, a process of its own

The `pinecall` command is the one CLI (`npm i -g pinecall`), installed once per machine and never a
dependency of the project. In the project's folder, `pinecall start --prod` starts your project's
`@pinecall/agents/serve` and watches it; beside it, it holds the socket that answers the console.
Run that line under whatever keeps the app's processes up:

```text title="Procfile"
web: node dist/server.js
agent: pinecall start --prod
```

**A deploy never cuts a call.** On SIGTERM the process drains: the gateway hands its live calls to
another process holding the agent, or keeps them for the next one, and the tools running are let
finish. Give the process 45 seconds between the signal and the kill — systemd's
`TimeoutStopSec=45`, pm2's `--kill-timeout 45000`. A second signal leaves at once.

What the agent searches is pushed before the deploy, not with it: `pinecall docs push --prod`.
