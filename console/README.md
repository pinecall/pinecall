# pinecall/console

The web console for the Pinecall runtime.

The runtime's gateway serves the console at its name, with both worlds in it: production and the
sandbox, a switch at the top, one sign-in.

- **Production** manages the org: deployed agents, calls, phone numbers, API tokens, vendor keys,
  team and usage.
- **Sandbox** is for development: your copies of the agents, live calls, Dev chat, test suites,
  phone testing.

`pinecall console` (the CLI, [pinecall/cli](https://github.com/pinecall/pinecall/tree/main/cli))
opens it signed in.

## Development

```bash
pnpm install    # from the repository's root: every TypeScript package, one lockfile
pnpm check      # build, lint and test
```

What the page stands on — the gateway client, the key, the call's state, the palette — is
[`packages/core`](../packages/core) (`@pinecall/core`), taken as source; Pinecall's supervisor app
takes it the same way. Nothing is published to npm. The runtime's `scripts/console` copies `dist/`
into the gateway, and the runtime's `make deploy` ships it. To see the page, run a gateway (see the
runtime's README) or `pnpm dev`, which proxies to production.

It is a folder of [pinecall/pinecall](https://github.com/pinecall/pinecall), beside the packages it
works with:

```
pinecall/
├── runtime/         the gateway that serves the console and the API it reads
├── cli/             the pinecall CLI
├── console/         this folder
├── widget/          one agent as one button on any page
├── sdk/             the agent frameworks: typescript/, python/, ruby/
└── packages/
    ├── core/        what this page and the supervisor app stand on
    └── room/        the caller's side of a call, for a page's own UI
```

Every screen, and whether the sandbox, production or both have it: `src/lib/mode.ts`; the
screens explained for a team: [The console](https://docs.pinecall.io/guides/console/).
