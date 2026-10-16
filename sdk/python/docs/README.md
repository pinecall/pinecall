# Docs

Five pages, in the order a person meets them: the first is the walk a newcomer takes, from an empty
directory to an agent that answers from your documents and remembers who called, and the other four
are the reference it points at.

| page | what it answers |
|---|---|
| [tutorial.md](tutorial.md) | forty minutes, from nothing: the class, a call, knowledge, the knowledge base, memory, the log, and a test |
| [writing-an-agent.md](writing-an-agent.md) | the class: config, state, the stage, tools, the events it accepts, and what is refused when it is created |
| [the-view.md](the-view.md) | the prompt as named blocks in two regions, and the Jinja template that renders the view |
| [testing-an-agent.md](testing-an-agent.md) | ring 0 with `pinecall.testing`, a suite with no network, no key and no model, and the rings above |
| [production.md](production.md) | how a server runs the agent: `pinecall start --prod`, or `pinecall.hold` in your own process |

The map of the package itself — every file, and what each piece corresponds to in the TypeScript
package and the Ruby gem — is [../ARCHITECTURE.md](../ARCHITECTURE.md).
