# Quickstart

From nothing to an agent that answers, in ten minutes. You install one command, create a project
in the language you like, read what the model will see, talk to the agent, and run its first test.
Everything runs in your org's **sandbox** on Pinecall Cloud: a space of your own to try things,
where nothing reaches a real caller.

## Before you start

- **Node 24 or later.** The `pinecall` command is a Node program, whatever language your agent is
  written in. `node --version` tells you which you have.
- **A Pinecall account.** Sign up at [cloud.pinecall.io](https://cloud.pinecall.io/sandbox/) if you
  do not have one; the quickstart signs you in from the terminal.
- **For a Python agent**, Python 3.11 or later and [uv](https://docs.astral.sh/uv/). **For a Ruby
  agent**, Ruby 3.2 or later and Bundler. A TypeScript agent needs nothing more than Node.

:::steps
### Install the CLI

```bash
npm i -g pinecall
pinecall --version
```

:::result
```console
0.11.2
```
One command, installed once per machine. It serves an agent in any of the three languages.
:::

> [!NOTE]
> No account, and nothing sent to a cloud? `pinecall-runtime setup` runs the whole runtime on your
> machine, open models included, and the CLI finds it by itself: skip `pinecall link` below.
> [On your machine](/self-hosting/laptop/) walks it.

### Create a project

Pick a language. The project is the same shape in all three: one folder per agent under
`agents/`, holding the agent's class and its tests.

:::tabs
### TypeScript
```bash
pinecall new acme --agent front-desk
cd acme
npm install
```
### Python
```bash
pinecall new acme --agent front-desk --python
cd acme
uv sync
```
### Ruby
```bash
pinecall new acme --agent front-desk --ruby
cd acme
bundle install
```
:::

:::result
```console
▸ acme · a TypeScript project · agents/front-desk/

  cd acme
  npm install
  pinecall link        sign in, pick the org: its key goes to .env
  pinecall chat        talk to it here
  pinecall test        its goldens, against a real model
  pinecall start       answer calls
```
`acme` is the project: the business, and the folder. `front-desk` is the agent: its folder under
`agents/` and its name on Pinecall. A project holds as many agents as the business needs, each
added with `pinecall generate agent <name>`. An agent's name is one org's on a gateway: if
`pinecall chat` later answers `agent front-desk belongs to another org`, somebody took it first —
write the agent again with a name of your own (`pinecall generate agent ana-front-desk`). The
lines under it are the steps that follow. `npm install` (or `uv sync`, `bundle install`) installs the SDK the agent is
written with; the project depends on nothing else.
:::

Inside the folder:

:::tabs
### TypeScript
```text
agents/front-desk/agent.tsx              the class: its state, its one tool, its prompt
agents/front-desk/test/agent.test.ts     a unit test: the class as software, no network
agents/front-desk/test/goldens/          a golden: a conversation the model must hold
package.json · tsconfig.json             the toolchain, with @pinecall/agents as the one dependency
```
### Python
```text
agents/front-desk/agent.py                the class: its state, its one tool
agents/front-desk/views/front-desk.jinja  its prompt's view, a template beside the class
agents/front-desk/test/test_agent.py      a unit test: the class as software, no network
agents/front-desk/test/goldens/           a golden: a conversation the model must hold
pyproject.toml                            the toolchain, with pinecall as the one dependency
```
### Ruby
```text
agents/front-desk/agent.rb                the class: its state, its one tool
agents/front-desk/views/front-desk.erb    its prompt's view, a template beside the class
agents/front-desk/test/agent_test.rb      a unit test: the class as software, no network
agents/front-desk/test/goldens/           a golden: a conversation the model must hold
Gemfile · Rakefile                        the toolchain, with the pinecall gem as the one dependency
```
:::

The agent `--agent` writes is a front desk: it answers from the documents it is given and,
for anything else, takes a message — the caller's name and what the call is about — with its one
tool, `takeMessage` (`take_message` in Python and Ruby).

### Sign in

```bash
pinecall link
```

:::result
```console
▸ front-desk · PINECALL_KEY written to .env
```
It opens the browser so you can sign in, asks which of your orgs this project belongs to, and
writes your key to `./.env`. The project's `.gitignore` already keeps `.env` out of git. Every
`pinecall` command run in this folder reads the key from there.
:::

To see which org and gateway the CLI is using at any time:

```bash
pinecall whoami
```

:::result
```console
gateway https://cloud.pinecall.io · key from .env · sandbox
  org front-desk · key k_4f2a1d9c66b30e17 · sandbox · ana-macbook · production: yes
```
The first line is where commands go and which key they use. `sandbox` means nothing you do here
reaches a real caller; `--prod` on a command acts in production instead.
:::

### Read what the model reads

```bash
pinecall prompt
```

:::result
```console
── identity (static) ──
You answer the phone for the business. Short sentences: everything you say is read aloud. …

<rules>
- Invent nothing: if it did not come from a tool or from the knowledge, do not say it.
- One question per turn, and wait for the answer.
…
</rules>

── knowledge (static) ──

── tools (static) ──
<tools>
- takeMessage: Writes down the caller's message. Call it as soon as the caller has said their name …
</tools>

── history ──

── view (dynamic) ──
A question the documents answer, answer. Otherwise take a message: ask only for what the caller has not said yet, their name or what the call is about, and call takeMessage the moment you have both. Greet nobody twice.

── tools ── stage: ask

  ● takeMessage  ask
```
This is the exact text the model reads when a call opens, with no key and no network. It has four
blocks: **identity** is your class's docstring plus rules Pinecall adds for every agent;
**knowledge** is what the agent knows by heart (empty until you write it, in step 7); **tools** is
every tool with its docstring; **view** is what your class says to do in this turn. Under the
blocks, the stage the agent is in and the tools the model may call now. Change the class and run
it again.
:::

### Talk to it

```bash
pinecall chat
```

:::result
```console
‹ Hi, I'm Ana Lopez. Please tell the manager my last order arrived broken.
→ takeMessage({"name":"***","about":"last order arrived broken"})
› Got it, Ana. Your message has reached the team. Goodbye!
```
`‹` is you, typing. `→` is a tool the model called, with its arguments: the name shows as `***`
because the class marked it as personal data, which is masked in the log. `›` is the agent's
answer. The agent runs on your machine, so a breakpoint in `takeMessage` stops there. Ctrl-D hangs
up.
:::

### Run its first test

```bash
pinecall test
```

:::result
```console
front-desk · 1 golden · the app's own model
  ✓ takes-the-message  llm_node_ttft 380ms
  1/1 · 0 judge calls · $0.0027 · 2s
```
A **golden** is a conversation written down, with what must be true at the end. This one says: a
caller leaves a message, and the agent must call `takeMessage`. `pinecall test` plays it against a
real model and checks the result. `✓` is a pass; `llm_node_ttft` is how long the model took to
start answering; the last line is the score, the model calls it cost, and the time. Add one
golden per behaviour you care about, in `agents/front-desk/test/goldens/`.
:::

The unit test runs with no network and no model: `npm test`, `uv run pytest` or `bundle exec rake`.

### Give it documents

```bash
mkdir -p docs/front-desk
printf '# Refunds\n\nA refund reaches the card it was paid with within ten working days.\n' > docs/front-desk/refunds.md
pinecall docs push
pinecall docs attach front-desk
```

:::result
```console
front-desk · 1 file · 1 chunk · 212 ms
front-desk · front-desk attached · your corner v2
```
`docs push` uploads the folder as a knowledge base named after the agent; `docs attach` tells the
agent to search it on every turn. Run `pinecall chat` again and ask how long a refund takes: the
answer comes from your file, and nothing in your code changed.
:::

### Its voice, and the rest of its settings

```bash
pinecall voices --language en      # the voices, with their ids
pinecall agent set --voice <id>
pinecall agent                     # every setting: voice, models, language, greeting…
```

The voice, the models, the language and what it knows by heart are **settings** of the agent, not
code: changing one needs no deploy. `pinecall console` opens the same settings in the browser,
with every call the agent has had.

### Answer calls

```bash
pinecall start
```

:::result
```console
front-desk · front-desk · sandbox · connected to https://cloud.pinecall.io · key from .env · tools 1
talk to it  https://cloud.pinecall.io/sandbox/a/front-desk/playground
doors    web
```
This is the process that answers: on your laptop now, on a server later. It holds the agent until
Ctrl-C and prints every call as it happens. The `console` line is where to see the agent in the
browser and talk to it by voice; `doors` is how callers reach it, the web for now, a phone number
once you point one at it.
:::

To ship it, `pinecall deploy` uploads a TypeScript project and Pinecall runs it for you; a Python or
Ruby agent runs on a server of yours with `pinecall start --prod`.
:::

## Next steps

:::cards
- [Build your first agent](your-first-agent.md) {rocket-launch} Forty minutes, in your language: knowledge, memory, a test suite, and going live.
- [Agent overview](agent-overview.md) {code} The class, explained part by part: state, tools, stages, the prompt.
- [Deploy to Pinecall](deploy-to-pinecall.md) {cloud-arrow-up} Pinecall runs your project for you.
- [The CLI](the-cli.md) {terminal} Every verb and flag.
:::
