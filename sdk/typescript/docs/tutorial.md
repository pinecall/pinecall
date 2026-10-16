# Tutorial — an agent that answers from your documents and remembers who called

Forty minutes, from an empty directory to an agent that picks up a call, answers out of a folder of
Markdown you wrote, and knows on the second call what it learned on the first.

You need the gateway — Pinecall's, at `https://cloud.pinecall.io`, whose sandbox is yours to break —
the one `pinecall` CLI, and this package. The CLI is a Node program for every language: it never
loads your class, it starts your project's `@pinecall/agents/serve` and talks to it through the
gateway. Your code never imports LiveKit.

## 1. The CLI, and a key

```bash
npm i -g pinecall                # the CLI, Node 24+, once per machine
pinecall new clinica --agent clinica-norte
cd clinica
npm install                      # @pinecall/agents, the project's one dependency
pinecall link                    # signs this machine in, picks the org, writes its key to ./.env
pinecall whoami                  # which gateway, which org, and where the key was read
```

`pinecall new` writes the project — the clinic — and its toolchain: `package.json`, `tsconfig.json`
(`extends: "@pinecall/agents/tsconfig.tenant.json"`, which brings the JSX runtime of `render()` and
the decorators) and `vitest.config.ts`. `--agent` writes its first agent, `agents/clinica-norte/`:
the class, a ring-0 test and one golden. Another agent of the clinic is `pinecall generate agent <name>`.

`pinecall link` writes `PINECALL_KEY` into this folder's `.env` (and `PINECALL_URL` when the gateway
is not Pinecall's), which nothing else reads: another org is another folder. Every verb works in the
sandbox unless `--prod` is said.

## 2. The class

The project's layout is the CLI's, the same for every language: one folder per agent,
`agents/<slug>/`, holding `agent.tsx`, its documents under `docs/` and its tests under `test/`.
**The folder's name is the agent's slug.** Replace
`agents/clinica-norte/agent.tsx` with this — the whole thing:

```tsx
import { Agent, state, tool, type Stages } from "@pinecall/agents";

interface Patient {
  name: string;
  phone: string;
}

/** You are the front desk of Clínica Norte. Formal, short sentences. */
export default class ClinicaNorte extends Agent {
  @state stage: Stages<"identify" | "resolve"> = "identify";
  @state({ pii: true }) patient?: Patient | undefined;

  /** Finds the patient by name and phone. Ask for both before calling it. */
  @tool({ stage: "identify", pii: ["name", "phone"] })
  async findPatient(name: string, phone: string): Promise<Patient> {
    this.patient = { name, phone };
    this.stage = "resolve";
    return this.patient;
  }

  override render() {
    return (
      <>
        {this.stage === "identify" && <p>Greet the caller and ask for their name and phone. Nothing else until you have both.</p>}
        {this.patient && <p>You are talking to {this.patient.name}, already on file. Do not ask for them again.</p>}
      </>
    );
  }
}
```

Four things are worth naming, because they are the whole design:

- **The class's docstring is the prompt's first paragraph.** Not documentation about the code: the
  words the model reads.
- **A tool's docstring is what the model reads about that tool, and its signature is the schema.**
  The parameters' types become the JSON Schema the model fills, and what it sends is checked
  against it before your method runs. `pii` names the arguments that carry personal data and are
  masked in the log; one naming a parameter the method has not is refused when the class loads, by
  name — as is a tool with no docstring.
- **Fields are the state, and tools are the only writers.** `this.patient = …` renders the prompt
  again and writes a `state.changed` line carrying the tool's own name; the same assignment
  anywhere else throws `UnauthoredWrite`.
- **The view is `render()`**: JSX that renders to text, with the state in `this`. It is the only
  part of the prompt that differs between two turns of a call.

Before running anything, look at what the model would read. No key, no gateway, no network:

```
$ pinecall prompt
── identity (static) ──
You are the front desk of Clínica Norte. Formal, short sentences.

<rules>
- Invent nothing: if it did not come from a tool or from the knowledge, do not say it.
- One question per turn, and wait for the answer.
…
</rules>

<protocols>
- To act, call a tool; saying you have done something does not do it.
…
</protocols>

<channel>
You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, …
</channel>

── knowledge (static) ──

── tools (static) ──
<tools>
- findPatient: Finds the patient by name and phone. Ask for both before calling it.
</tools>

── history ──

── view (dynamic) ──
Greet the caller and ask for their name and phone. Nothing else until you have both.
```

Four named blocks in two regions, in the one order they are ever sent. Everything above `history` is
what the provider caches; the view is rendered again on every state change, and a block goes up
again only when its own text changed. The rules and the channel's words are the framework's, the
same in every language the SDK is written in. `pinecall prompt --state <a golden's file>` prints the
page that golden's opening state produces.

## 3. Talk to it

```bash
pinecall chat                    # the agent served from this terminal, and a written caller against it
pinecall start                   # registered and answering: the process you deploy
```

`chat` starts your project's serve entry for the agent of this folder — a process that takes no
call it did not open — opens a written call naming that process, and stops it when you leave.
`start` is the same entry taking every call, with the console's screens answered beside it; under
it, the console's Talk tab is a real voice call to the same process. `--inspect` opens that process
to a debugger, so a breakpoint in a `@tool` is reachable.

Your tools run in that Node process: the gateway asks, your method answers, and no code of yours
ever crosses the socket.

## 4. Knowledge: a page the agent knows by heart

The voice, the model, the opening and everything else the agent runs on are not in the class: they
are the world's, set with `pinecall agent set` or the console's Settings, and a class that still
declares one is refused when it loads, with the verb to use instead
([writing-an-agent.md](writing-an-agent.md)).

What the agent knows by heart — hours, prices, what needs an authorisation — is one of those: a page
of Markdown in the agent's settings, written in the console, Settings ▸ Knowledge, or with
`pinecall agent knowledge edit`. The class sends nothing for it, so `pinecall prompt` prints the
second block empty; the gateway writes the page into it, whole, once per call, in the cached prefix:
the model has it in every turn and you pay for it once.

Use this for what is small, stable and always relevant. A folder of a hundred documents is not, and
that is the next step.

## 5. The knowledge base: what it looks up per turn

Put your Markdown under `agents/clinica-norte/docs/`, one file per subject, with headings, and push it.
With no arguments the verb reads that folder and pushes it under the agent's slug. Attaching the
base to the agent, with its `k` and `min_score`, is a setting — or the class's `static docs`.

```bash
pinecall docs push
pinecall docs attach clinica-norte --k 4
```

That is all: no vector-database client, no `search` call in your code, no `if` that decides when to
look. Each file was cut at its headings, each chunk prefixed with its heading path
(`prices.md › Prices › Check-up`) and embedded; on every turn the platform runs a `search` itself,
over an HNSW index and a BM25 index fused by rank. On a spoken call it starts while the caller is
still talking, so the answer is there when they stop.

A push replaces the base whole, so push again after every edit.

## 6. Memory: what it keeps between calls

```bash
pinecall memory policy --remember "how they like to be addressed" "allergies" "their usual doctor" --forget "payments"
```

The policy is a setting, or the class's `static memory`, which wins over it. `remember` is the vocabulary, **in your own words**, of
what is worth keeping about a person; `forget` is what is never written whatever the model heard.
A `recall` runs beside the `search` on every turn; at hang-up, one model call reads the call and
writes what it taught. On the phone and on WhatsApp the number is the identity; on the web nobody is
anybody until your page says so.

The view may ask memory a question and say a sentence of its own about the answer:

```tsx
{this.remembers("usual doctor") && <p>Offer their usual doctor's slots first.</p>}
```

## 7. What the model actually receives

```
system:   identity · knowledge · tools           ← cached, unchanged while the call runs
messages: …the turns…
          assistant tool_use  recall  {"contact":"+34600123456","query":"How much is…"}
          user      tool_result       {"facts":[{"text":"Prefers to be called Marta.", …}]}
          assistant tool_use  search  {"query":"How much is a general check-up?"}
          user      tool_result       {"chunks":[{"path":"prices.md", "heading":"Prices › Check-up", …}]}
          user      <instructions> what render() wrote </instructions>
```

A remembered fact was written by a model from an earlier caller's words, and a chunk was written by
whoever wrote the document. Neither is yours, so neither carries your authority: they arrive as
tool results, JSON-encoded, never as a paragraph of the prompt. That is why **every block of the
prompt is your own words and nothing else is ever put in one**.

## 8. The log, and the console

```bash
pinecall console                 # the sandbox's console, signed in as this folder's key
pinecall sessions                # the calls this agent has taken; `sessions <call>` reads one
```

The same log without a browser is `@pinecall/agents/client`:

```tsx
import { Pinecall } from "@pinecall/agents/client";

const pc = new Pinecall({ url: process.env.PINECALL_URL ?? "https://cloud.pinecall.io", apiKey: process.env.PINECALL_KEY });
const page = await pc.history({ call: process.argv[2]! });
for (const entry of page.entries) {
  if (entry.type === "docs.sources") console.log(entry.data);
}
```

Every call is an append-only log of typed entries, each with a `seq` written before control returns.

## 9. Test it

**Ring 0** is your own suite: vitest, no network, no key, no model, no gateway. Replace the test
`pinecall new` wrote, `agents/clinica-norte/test/agent.test.ts`, with one for this class:

```tsx
import { readFileSync } from "node:fs";

import { CallWorld, describe as describeClass, promptOf, runTool, seal, setCall, toolNamed, type ToolDeclaration } from "@pinecall/agents";
import { expect, it } from "vitest";

import ClinicaNorte from "../agent.js";

describeClass(ClinicaNorte, readFileSync(new URL("../agent.tsx", import.meta.url), "utf8"));

it("stops asking for the name once the patient is identified", async () => {
  const agent = seal(new ClinicaNorte());
  setCall(agent, new CallWorld({ id: "CA_1", contact: "+34600123456", channel: "phone" }, () => undefined));

  await runTool(agent, toolNamed(agent, "findPatient") as ToolDeclaration, { name: "Marta", phone: "600123456" });

  const view = promptOf(agent).blocks.find((block) => block.name === "view")?.text ?? "";
  expect(view).toContain("talking to Marta");
  expect(view).not.toContain("ask for their name");
});
```

```bash
npm test
```

`describe` hands the class its own source, so its docstrings survive the transpiler; `runTool` runs
a tool as a call does. [testing-an-agent.md](testing-an-agent.md) is every helper.

**Rings 1, 2 and 3** — the goldens, a real line, and one call re-scored — are `pinecall test`,
`pinecall simulate --voice` and `pinecall eval`. **Ring 4** happens without you: every finished call
is judged at hang-up and the verdict is an entry in your own log, `call.score`.

## 10. Ship it

```bash
pinecall deploy --prod
```

Pinecall installs the project from its lockfile and runs it, a deploy never cuts a call, and
[production.md](production.md) is the other two ways: inside your own Node app, or
`pinecall start --prod` on a server of yours.

## Where to go next

| you want | read |
|---|---|
| every declaration a class may carry | [writing-an-agent.md](writing-an-agent.md) |
| the four blocks, the two regions, and `render()` | [the-view.md](the-view.md) |
| the rings, and what is worth a test | [testing-an-agent.md](testing-an-agent.md) |
| running it on a server | [production.md](production.md) |
| a whole agent: stages, ids, a confirmed booking | [examples/typescript/clinica-norte](../../../examples/typescript/clinica-norte) |
