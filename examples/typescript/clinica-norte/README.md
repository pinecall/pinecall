# Clínica Norte

The whole tenant: a class that renders itself, the clinic's agenda, and the documents the agent
searches. Everything else — the state machine, the confirmation gate, memory, retrieval, the log
and the console — is the platform's. And what the agent knows by heart, the voice, the model, the
greeting and the words are not in this repository: they are the world's, in Settings.

The clinic is Spanish and so is everything its callers hear: the class's docstrings, its view and
the goldens are in Spanish on purpose. The framework's own rules are English, and tell the model to
answer in the caller's language.

```
agents/clinica-norte/       the agent, whole: its folder's name is its slug
  agent.tsx                 the class: the state is its fields, the tools are methods with a docstring,
                            and render() is the prompt as a function of the state — the last thing the model reads
  agenda.ts, crm.ts         the clinic's systems; here, deterministic doubles
  docs/                     sample data: the base the agent SEARCHES, to upload once
  test/
    agent.test.ts           the class as software
    goldens/                the conversations `pinecall test` runs; docs.json and memory.json, the
                            goldens of retrieval and of memory
    personas/               the seed of who calls: `pinecall personas push` uploads them to the gateway
    memory/                 the extraction cases of `pinecall remember`
```

## The tsconfig

```json
{ "extends": "@pinecall/agents/tsconfig.tenant.json" }
```

That is all a tenant writes. The preset brings the JSX runtime of `render()` and
`experimentalDecorators`, which `@tool` and `@state` still need because vite 8's transform (oxc)
implements only the legacy decorators. The day oxc ships TC39's, the flag leaves the preset and
nothing here changes.

## Test it

```bash
pnpm --filter @pinecall/example-clinica-norte test    # vitest, no network and no model
pnpm --filter @pinecall/example-clinica-norte lint    # tsc --noEmit
```

`agents/clinica-norte/test/agent.test.ts` walks the four stages with the class in hand;
`walkthrough.test.ts` walks them again against the SDK's `FakeGateway`, with the same
`tool.result`s a model would see, including the "no" for the 13:00 slot, which the agenda always
refuses.

## Run it

With the CLI, which is its own package (`npm i -g pinecall`, or `node ../../../cli/bin/pinecall.js`
from the repository's [`cli/`](../../../cli)):

```bash
pinecall login              # once per machine: signs it in
pinecall start              # the app: registers the agent and answers its tools
pinecall chat               # the app in THIS terminal, and a written call against it
pinecall test               # the goldens of agents/clinica-norte/test/goldens/, scored by the runtime
pinecall docs push          # once: agents/clinica-norte/docs/ to the gateway, as the base clinica-norte
pinecall docs attach clinica-norte --k 4      # the agent searches it every turn
pinecall simulate --persona apurado --judge   # a persona a model improvises, and its call.score
```

What the front desk knows by heart — hours, prices, what needs an authorisation — is written in the
console, Settings ▸ Knowledge (or `pinecall agent knowledge edit`), and the model reads it whole on
every call. The voice, the model and the greeting are on the same screen, or `pinecall agent set`.

What it remembers about a patient between calls is a policy on the gateway, Settings ▸ Memory in
the console or one line of the CLI, and the goldens of `agents/clinica-norte/test/memory/` and the view's
`remembers("médico habitual")` read these five categories:

```bash
pinecall memory policy --team --remember alergias --remember 'cómo prefiere que le llamen' \
  --remember 'cuándo prefiere que le llamen' --remember 'médico habitual' --forget pagos
```

The documents it searches are not the repository's either: they are a base on the gateway, written
in the console, Settings ▸ Docs, file by file. `agents/clinica-norte/docs/` is here only because this is an
example: the sample to create the base the first time. A `docs push` replaces the whole base, so
once it is edited in the console it is not pushed again.

The goldens live in `agents/clinica-norte/test/goldens/`: one per file, `{state, input, expect}`.

The personas are the agent's and the gateway keeps them, beside its settings: their goal, how they
talk and what they know about themselves — never a script: a model improvises them turn by turn.
`pinecall personas` lists them, `pinecall personas show apurado` opens one and `pinecall personas
add` writes another; the console's Personas screen writes the same. The files in
`agents/clinica-norte/test/personas/` are this example's seed: `pinecall personas push` uploads them once,
and from then on they are edited where the rest of the agent's world lives.

The patient `Ana García`, phone `+34 600 000 001`, has a file; the agenda refuses any 13:00 slot, so
the "that slot was just taken" path shows without faking anything.
