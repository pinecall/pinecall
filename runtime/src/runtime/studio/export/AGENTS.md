# $name

A Pinecall agent exported from Studio (release $release). `agents/$name/agent.tsx` is the whole agent:
its docstring and `render()` are the prompt, each `@tool` method a request to the business's API.

## Tools

$tools

## Secrets

The process reads them from its environment: $secrets. On Pinecall
they are the org's secrets (`pinecall secrets set`), the same Studio used.

## Run it

- `npm install`, then `pinecall start` holds it from this machine; `pinecall chat` talks to it.
- `pinecall deploy` runs it on Pinecall. Once it answers, remove the Studio agent of the same name in the
  console: a slug is one agent.

Read https://docs.pinecall.io before changing the class: tools, state, the view and goldens are there.
