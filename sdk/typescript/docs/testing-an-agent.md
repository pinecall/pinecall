# Testing an agent

Ring 0 is the ring your own suite lives in: no network, no key, no model, no gateway. It runs on
every commit, in a second, and it is where nearly every mistake is caught. `pinecall new` writes
one beside the agent, run with `npm test` (vitest):

```tsx title="agents/front-desk/test/agent.test.ts"
import { readFileSync } from "node:fs";

import { CallWorld, describe as describeClass, promptOf, runTool, seal, setCall, toolNamed, type ToolDeclaration } from "@pinecall/agents";
import { beforeEach, expect, it } from "vitest";

import FrontDesk from "../agent.js";

// The class's own source: its docstrings and parameter types survive the transpiler.
describeClass(FrontDesk, readFileSync(new URL("../agent.tsx", import.meta.url), "utf8"));

let agent: FrontDesk;

beforeEach(() => {
  agent = seal(new FrontDesk());
  setCall(agent, new CallWorld({ id: "CA_1", contact: "+15550100", channel: "phone" }, () => undefined));
});

function view(): string {
  return promptOf(agent).blocks.find((block) => block.name === "view")?.text ?? "";
}

it("asks for a message until there is one", () => {
  expect(view()).toContain("ask for their name and what the call is about");
});

it("ends the call with the message it took", async () => {
  await runTool(agent, toolNamed(agent, "takeMessage") as ToolDeclaration, { name: "Ana", about: "a refund" });

  expect(agent.stage).toBe("done");
  expect(view()).toContain("Ana, about a refund");
});
```

> [!WARNING]
> Skip `describe(...)` and the types are gone: the transpiler erased them, so `runTool` cannot tell a
> string from an object and says so, `takeMessage: its parameter types were erased when the file was
> compiled; hand the class its own source with describe(AgentClass, source)`. A transpiler that strips
> comments as well takes the docstring, and the tool refuses to build: `tool takeMessage: without a
> docstring no model can choose it`. Either way the class needs its own source handed back.

## The helpers

Every helper comes from `@pinecall/agents`:

| export | what it does |
|---|---|
| `describe(AgentClass, source)` | hands the class its own source, once per file, so docstrings and parameter types survive the transpiler |
| `seal(agent)` | starts recording state changes; field initializers before it are the baseline |
| `setCall(agent, call)` | gives the agent a call, as `this.call`; a `CallWorld` takes `{ id, contact, from, channel }` and a callback for what the agent does to it |
| `toolNamed(agent, name)` | a declared tool, by name |
| `runTool(agent, tool, args)` | one tool call as Pinecall runs it: arguments checked, writes authored by the tool, the result cut to its `preview` |
| `runHook(agent, name, ...args)` | a hook such as `onCall`, its writes authored by it |
| `recalled(agent, facts)` | facts as if memory had recalled them, for a `render()` that asks `remembers` |
| `promptOf(agent)` | the prompt as blocks, each with a `name` and its `text` |
| `showPrompt(agent)` | the prompt as one printed page, as `pinecall prompt` shows it |

`agent.visibleTools()` lists the tools the model would see in the current state.

## What is worth a test

The things a prompt makes true, not the things a method returns:

- **Each tool's effect on state.** Call it with good arguments and with bad ones. A tool that
  refuses should leave the state as it was, and its error is what the model reads — assert on it.
- **Each stage's tools.** After a tool moves the stage, `visibleTools()` should offer the next step
  and nothing that comes later.
- **The prompt blocks.** Render the class in three states and check that every block except the
  view is byte-for-byte the same in all three, and the view changed. The prompt cache depends on
  it, and nothing else notices when `render()` starts writing into a cached block.

## The whole app, in process

To test the agent the way the gateway drives it — `tool.call` in, `tool.result` out — mount it on a
gateway that is not there, from `@pinecall/agents/client/testing`. It answers the app's socket on
this machine:

```tsx
import { mount } from "@pinecall/agents";
import { Pinecall } from "@pinecall/agents/client";
import { FakeGateway } from "@pinecall/agents/client/testing";

const gateway = await FakeGateway.start({ apiKey: "pk_test" });
const pc = new Pinecall({ url: gateway.url, apiKey: "pk_test" });
mount(FrontDesk, { pc, source: SOURCE, slug: "front-desk" });
await pc.connect();

gateway.emit("front-desk", "CA_1", "call.started", {
  channel: "web", direction: "inbound", from: "web_ana", to: "front-desk", caller: null, started_at: Date.now() / 1000,
});
gateway.emit("front-desk", "CA_1", "tool.call", {
  call_id: "t-1", name: "takeMessage", arguments: { name: "Ana", about: "a refund" },
});
// gateway.commandsOf("tool.result") holds what a model would have been sent,
// gateway.commandsOf("tools.set") the tools it would see. Close with pc.close() and gateway.close().
```

`gateway.finds([...])` scripts what every search answers, and `gateway.cut()` drops the socket, so
a test can watch the agent dial back.

## The rings above

The verbs are the one `pinecall` CLI's, the same for a TypeScript project as for a Ruby or a Python
one, in the same layout: `agents/<slug>/agent.tsx`, `agents/<slug>/test/goldens/`, `agents/<slug>/test/memory/`,
`agents/<slug>/test/personas/`, `agents/<slug>/judges/`, `agents/<slug>/docs/`.

| ring | what it asks | how |
|---|---|---|
| 1 | does the agent hold its goldens? | `pinecall test` — the goldens under `agents/<slug>/test/goldens/`, played on whoever holds the agent: your `pinecall start`, or production's with `--prod`; `test` starts nothing |
| 2 | does it hold on a real line? | `pinecall test --voice` · `pinecall simulate --voice` |
| 3 | what does one real call score? | `pinecall eval <call-id>` |
| 4 | what did every call score? | `call.score`, written by the runtime at hang-up |

**The callers and the judges can be the class's.** `static personas = personas({ on: [...] })` names
which of Pinecall's callers `pinecall simulate` offers, and the agent's own callers are
`test/personas/<name>.json`, one each, what `PUT …/personas/{name}` takes; `static judges =
judges({ on: [...] })` names which of Pinecall's judges score every call at hang-up (ring 4), and
the agent's own judges are `judges/<name>.md`, one each, in the library's format. Both travel with
the code, are reviewed in a pull request and deploy with it; the console shows them locked. A class
that declares neither leaves them to the console and the CLI ([Writing an
agent](writing-an-agent.md), the environment).

The index and memory have goldens of their own — whether retrieval returns the chunk a question
needs (`pinecall docs eval`), whether recall brings back the fact a question needs
(`pinecall memory eval`), and what the hang-up's one model call writes, replaces and must never
keep (`pinecall remember`). They are files beside the project, run by the CLI and the same for every
language: [Testing knowledge & memory](https://docs.pinecall.io/guides/testing-knowledge-and-memory/).
