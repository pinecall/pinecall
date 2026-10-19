# An agent with no code

Part of [the MCP server](../the-mcp.md): every tool of this stage, what each parameter takes — read off the
tool's own schema, as the assistant sees it — and one real call, answered by Pinecall Cloud.

## `studio`

Build an agent with no code, as the console's Studio does: made, its definition saved as releases, each tool's request tried, deployed to production.

`studio` builds an agent with no class and no project: a definition the gateway holds and answers calls from. `new` makes it in the sandbox from a template; `show` answers its `release` and `definition`. `save` keeps a whole `definition` as the next release, `based_on` the release you read — refused when someone saved meanwhile: `show` again and save over that. A definition is the agent's `instructions`; its `greeting` (`say` the words, or `reply` for an opening of the model's own); its `tools`, each an HTTP request (`method`, `url`, `headers`, `params` the model fills: a path's `{name}`, else a GET's query or the JSON body) whose answer the model reads; and `collect`, the `fields` it gathers from the caller, the call ended once the required ones are in and the fields posted to `send_to`. `try` sends one tool's request once with `arguments` and answers its status, body and time: try every tool before a person calls. Then `chat` with `agent` set to its name talks to it, as to any sandbox agent, with nothing started. `deploy` is asked without `prod`: the sandbox's release lands in production, on a person's key that may act there. A secret is never written into a definition: a header names it as `{{secrets.NAME}}`, and the person sets it with `pinecall secrets set` or in the console. The `deploy` tool's `list` shows it beside the org's hosted apps; removing one is `pinecall deploy rm` in a terminal.

| parameter | takes | | what it is |
|---|---|---|---|
| `action` | `list` · `show` · `new` · `save` · `try` · `deploy` | required | list the org's Studio agents; show one's newest release and definition; new makes one; save keeps a whole definition as the next release; try sends one tool's request once; deploy puts the sandbox's release in production |
| `name` | text |  | the agent's name: lower-case letters and digits joined by dashes; every action but list takes it |
| `definition` | an object of `instructions` · `greeting` · `tools` · `collect` |  | `save`: the whole definition, every part of it, as `show` answers it — what is left out is gone; `new`: what it starts as, the gateway's template when left out; `try`: a definition not saved yet, to try its tool before saving |
| `based_on` | a whole number 1 or more |  | `save`: the release the definition was read at, from `show` or the last `save`; refused when someone saved meanwhile |
| `tool` | text |  | `try`: the tool's name |
| `arguments` | an object |  | `try`: the tool's arguments, as the model would fill its params |
| `release` | a whole number 1 or more |  | `deploy`: the sandbox's release to deploy; its newest when left out |
| `note` | text |  | `new`, `save` and `deploy`: a note kept with the release |
| `prod` | true or false |  | true acts in production; left out or false, in the sandbox |
