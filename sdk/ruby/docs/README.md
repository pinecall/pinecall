# Docs

Five pages, in the order a person meets them: the first is the walk a newcomer takes, from an empty
directory to an agent that answers from your documents and remembers who called, and the other four
are the reference it points at.

| page | what it answers |
|---|---|
| [tutorial.md](tutorial.md) | forty minutes, from nothing: the class, a call, knowledge, the knowledge base, memory, the log, and a test |
| [writing-an-agent.md](writing-an-agent.md) | the class: config, state, tools, hooks, and what is refused at load |
| [the-view.md](the-view.md) | the prompt as named blocks in two regions, and the template that renders the view |
| [testing-an-agent.md](testing-an-agent.md) | the index's own golden, why a call has no retrieval score, and a suite with no network, no key and no model |
| [production.md](production.md) | how a server runs the agent: the one CLI's `pinecall start --prod`, or `Pinecall.serve` in your own process |

The map of the package itself — every file, every entity, and what each piece corresponds to in
the TypeScript package — is [../ARCHITECTURE.md](../ARCHITECTURE.md).
