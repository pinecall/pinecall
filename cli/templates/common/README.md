# {{ProjectTitle}}

Pinecall agents in {{Language}}. Each agent is one folder under `agents/`, and everything it is
lives in it: the folder's name is the agent's name on the gateway.

```
agents/<name>/{{file}}            the class: its state, its tools, its prompt
agents/<name>/docs/                the documents its base is pushed from (pinecall docs push)
agents/<name>/test/                ring 0, the class as software ({{ring0}})
agents/<name>/test/goldens/        ring 1, conversations the model must hold (pinecall test)
lib/                               code two or more agents share
```

```bash
{{install}}
pinecall generate agent <name>   # one more agent, beside the others
pinecall link        # signs this machine in and writes this folder's key to .env
pinecall prompt      # the exact prompt the model reads, offline
pinecall chat        # talk to it in this terminal
pinecall test        # the goldens, against a real model
pinecall start       # answer calls; `pinecall console` opens the console beside it
```

The voice, the model, the greeting and what it knows by heart are its settings, not its code:
`pinecall agent set --help`, or Settings in the console. Every verb: https://docs.pinecall.io/cli/overview.
