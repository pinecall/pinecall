# Docs

Five pages, in the order a person meets them: the first is the walk a newcomer takes, from an empty
directory to an agent that answers from your documents and remembers who called, and the other four
are the reference it points at.

| page | what it answers |
|---|---|
| [tutorial.md](tutorial.md) | forty minutes, from nothing: the class, a call, knowledge, the knowledge base, memory, the log, a test, and shipping it |
| [writing-an-agent.md](writing-an-agent.md) | the class: config, state, stages, tools, hooks, the call, the panel, and what is refused when it loads |
| [the-view.md](the-view.md) | the prompt as named blocks in two regions, and `render()`, the JSX that writes the view |
| [testing-an-agent.md](testing-an-agent.md) | ring 0 with the package's helpers, a suite with no network, no key and no model, and the rings above |
| [production.md](production.md) | how the agent runs where its callers reach it: `pinecall deploy`, `mount` in your own Node app, or `pinecall start --prod` |

The product's own pages — what an agent is, the judges, the goldens, the console — are
[docs.pinecall.io](https://docs.pinecall.io), written TypeScript first. The map of the package
itself, file by file, is [../ARCHITECTURE.md](../ARCHITECTURE.md).
