/** The agent's judges and callers as code: a judge appended to its harness file, a caller to its test folder's personas file, never over one declared. */

import { existsSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { appendJudge, appendPersona, DECLARED_ALREADY, literal, NAMED_IN_THE_CLASS, startPersonas } from "../../src/project/harness.js";
import { homeOf } from "../../src/project/layout.js";
import { AN_AGENT, project, write } from "../support/project.js";

const OFFERS = { name: "offers-next-slot", question: "Did the agent offer the next free slot?", answer: "verdict", choices: [], when: "always", trigger: "", reads: ["facts"] };
const REASON = { name: "reason", question: "Why did they call?", answer: "choice", choices: ["book", "cancel"], when: "trigger", trigger: "Did they say why?", reads: [] };
const RUSH = { name: "in-a-rush", about: "", goal: "book today", style: "short, interrupts", facts: { "their name": "Luis" }, state: {}, expects: ["The agent should offer today."], tags: [], behavior: { interrupts: 0.3, pause_s: 1 }, llm: null, tts: null, voice: null };

describe("a TypeScript agent", () => {
  it("gets harness.ts as pinecall new writes it, the constructor imported under its opening line, and each judge appended as an export the class imports", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    expect(appendJudge(home, OFFERS)).toEqual({ path: "agents/front-desk/harness.ts", symbol: "offersNextSlot" });
    const code = readFileSync(home.harness, "utf8");
    expect(code.startsWith('// The judges of Front Desk\'s own, as code: imported by agent.tsx into the `judges` of its @agent({ … }).\n\nimport { ownJudge } from "@pinecall/agents";\n\n// A judge of the agent\'s own')).toBe(true);
    expect(code).not.toContain("ownPersona");
    expect(code.endsWith(`
export const offersNextSlot = ownJudge({
  name: "offers-next-slot",
  asks: "Did the agent offer the next free slot?",
  reads: ["facts"],
});
`)).toBe(true);
  });

  it("gets its callers in test/personas.ts, started with Pinecall's it plays and each of its own appended as an export", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    expect(startPersonas(home, ["in-a-hurry", "wrong-number"])).toBe(true);
    expect(startPersonas(home, [])).toBe(false);
    expect(appendPersona(home, RUSH)).toEqual({ path: "agents/front-desk/test/personas.ts", symbol: "inARush" });
    expect(existsSync(home.harness)).toBe(false);
    expect(readFileSync(home.personas, "utf8")).toBe(`// The callers Front Desk is tested with: every ownPersona this file exports is one of the agent's own, and \`on\` names
// the ones of Pinecall's it plays. \`pinecall simulate\` phones the agent as each one.

import { ownPersona } from "@pinecall/agents";

export const on = ["in-a-hurry", "wrong-number"];

export const inARush = ownPersona({
  name: "in-a-rush",
  goal: "book today",
  style: "short, interrupts",
  facts: {
    "their name": "Luis",
  },
  expects: ["The agent should offer today."],
  behavior: {
    interrupts: 0.3,
    pauseS: 1,
  },
});
`);
  });

  it("refuses a caller for an agent with no personas file: its class still names them, and pull moves them", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    expect(() => appendPersona(home, RUSH)).toThrow(NAMED_IN_THE_CLASS("front-desk", "agents/front-desk/test/personas.ts"));
    expect(existsSync(home.personas)).toBe(false);
  });

  it("writes of a caller's behavior only what differs from the runtime's defaults, and none when nothing does", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    const defaults = { interrupts: 0, pause_s: 0, interferer_db: null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "television", ambience_turns: 1 };
    startPersonas(home, []);
    appendPersona(home, { ...RUSH, name: "calm", behavior: defaults });
    appendPersona(home, { ...RUSH, name: "noisy", behavior: { ...defaults, interferer_db: -12, ambience: "cafe" } });
    const code = readFileSync(home.personas, "utf8");
    expect(code).toContain('export const calm = ownPersona({\n  name: "calm",\n  goal: "book today",\n  style: "short, interrupts",\n  facts: {\n    "their name": "Luis",\n  },\n  expects: ["The agent should offer today."],\n});');
    expect(code).toContain('  behavior: {\n    interfererDb: -12,\n    ambience: "cafe",\n  },\n');
    expect(code).not.toContain("speed");
  });

  it("writes how and when a judge answers only when it is not the default", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    appendJudge(home, REASON);
    expect(readFileSync(home.harness, "utf8")).toContain(`export const reason = ownJudge({
  name: "reason",
  asks: "Why did they call?",
  answer: "choice",
  choices: ["book", "cancel"],
  when: "trigger",
  trigger: "Did they say why?",
});`);
  });

  it("appends to the file as it stands, and refuses a name the file declares already", () => {
    const root = project(["front-desk"]);
    write(root, "agents/front-desk/harness.ts", 'import { ownJudge } from "@pinecall/agents";\n\nexport const reason = ownJudge({ name: "reason", asks: "Why?" });\n');
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    expect(() => appendJudge(home, REASON)).toThrow(DECLARED_ALREADY("agents/front-desk/harness.ts", "reason"));
    appendJudge(home, OFFERS);
    const text = readFileSync(home.harness, "utf8");
    expect(text.startsWith('import { ownJudge } from "@pinecall/agents";\n\nexport const reason')).toBe(true);
    expect(text).toContain("\n\nexport const offersNextSlot = ownJudge({");
    startPersonas(home, []);
    appendPersona(home, RUSH);
    expect(() => appendPersona(home, RUSH)).toThrow(DECLARED_ALREADY("agents/front-desk/test/personas.ts", "inARush"));
    expect(() => appendPersona(home, { ...RUSH, name: "In A Rush" })).toThrow(/no name for one of the agent's own/);
  });

  it("adds the constructor to the file's import when it imports the package without it, and the import when there is none", () => {
    const root = project(["front-desk"]);
    write(root, "agents/front-desk/harness.ts", 'import { ownPersona } from "@pinecall/agents";\n\nexport const rush = ownPersona({ name: "rush", goal: "g", style: "s" });\n');
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    appendJudge(home, OFFERS);
    expect(readFileSync(home.harness, "utf8").startsWith('import { ownJudge, ownPersona } from "@pinecall/agents";\n\nexport const rush')).toBe(true);
    write(root, "agents/sales/agent.py", AN_AGENT);
    write(root, "agents/sales/harness.py", 'from pinecall import own_persona\n\nRUSH = own_persona(name="rush", goal="g", style="s")\n');
    appendJudge(homeOf(`${root}/agents/sales/agent.py`), OFFERS);
    expect(readFileSync(`${root}/agents/sales/harness.py`, "utf8").startsWith("from pinecall import own_judge, own_persona\n\nRUSH")).toBe(true);
    write(root, "agents/notes/agent.py", AN_AGENT);
    write(root, "agents/notes/test/personas.py", "# nothing yet\n");
    appendPersona(homeOf(`${root}/agents/notes/agent.py`), RUSH);
    expect(readFileSync(`${root}/agents/notes/test/personas.py`, "utf8").startsWith("from pinecall import own_persona\n\n# nothing yet\n")).toBe(true);
  });
});

describe("a Python and a Ruby agent", () => {
  it("get harness.py and harness.rb as pinecall new writes them, and their callers in test/personas, each one a constant built keyword by keyword", () => {
    const root = project([]);
    write(root, "agents/sales/agent.py", AN_AGENT);
    write(root, "agents/notes/agent.rb", AN_AGENT);
    const python = homeOf(`${root}/agents/sales/agent.py`);
    const ruby = homeOf(`${root}/agents/notes/agent.rb`);
    startPersonas(python, ["in-a-hurry"]);
    startPersonas(ruby, ["in-a-hurry", "wrong-number"]);
    expect(appendPersona(python, RUSH)).toEqual({ path: "agents/sales/test/personas.py", symbol: "IN_A_RUSH" });
    expect(appendJudge(python, OFFERS)).toEqual({ path: "agents/sales/harness.py", symbol: "OFFERS_NEXT_SLOT" });
    expect(appendJudge(ruby, REASON)).toEqual({ path: "agents/notes/harness.rb", symbol: "REASON" });
    expect(readFileSync(python.personas, "utf8")).toBe(`"""The callers Sales is tested with: every own_persona this file defines is one of the agent's own, and ON names Pinecall's."""

from pinecall import own_persona

ON = ["in-a-hurry"]

IN_A_RUSH = own_persona(
    name="in-a-rush",
    goal="book today",
    style="short, interrupts",
    facts={
      "their name": "Luis",
    },
    expects=["The agent should offer today."],
    behavior={
      "interrupts": 0.3,
      "pause_s": 1,
    },
)
`);
    const py = readFileSync(python.harness, "utf8");
    expect(py.startsWith('"""The judges of Sales\'s own, as code: imported by agent.py into judges(own=…)."""\n\nfrom pinecall import own_judge\n\n# A judge of the agent\'s own')).toBe(true);
    expect(py).toContain("\nOFFERS_NEXT_SLOT = own_judge(\n");
    expect(readFileSync(ruby.personas, "utf8")).toBe(`# frozen_string_literal: true

# The callers Notes is tested with: every Pinecall.own_persona this file defines is one of the agent's own, and ON
# names the ones of Pinecall's it plays.

require "pinecall"

ON = ["in-a-hurry", "wrong-number"].freeze
`);
    const rb = readFileSync(ruby.harness, "utf8");
    expect(rb.startsWith("# frozen_string_literal: true\n\n# The judges of Notes's own, as code")).toBe(true);
    expect(rb).not.toContain("own_persona");
    expect(rb).toContain(`
REASON = Pinecall.own_judge(
  name: "reason",
  asks: "Why did they call?",
  answer: "choice",
  choices: ["book", "cancel"],
  when: "trigger",
  trigger: "Did they say why?"
)
`);
  });

  it("writes each language's nothing, booleans and keys its way", () => {
    expect([literal("typescript", null, ""), literal("python", null, ""), literal("ruby", null, "")]).toEqual(["null", "None", "nil"]);
    expect([literal("typescript", true, ""), literal("python", true, ""), literal("ruby", false, "")]).toEqual(["true", "True", "false"]);
    expect(literal("ruby", { "their-name": "x", ok: 1 }, "")).toBe('{\n  "their-name" => "x",\n  ok: 1,\n}');
  });
});
