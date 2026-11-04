/** The agent's harness file: one more judge or caller appended as code in the agent's language, never over one it declares. */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { appendJudge, appendPersona, DECLARED_ALREADY, literal } from "../../src/project/harness.js";
import { homeOf } from "../../src/project/layout.js";
import { AN_AGENT, project, write } from "../support/project.js";

const OFFERS = { name: "offers-next-slot", question: "Did the agent offer the next free slot?", answer: "verdict", choices: [], when: "always", trigger: "", reads: ["facts"] };
const REASON = { name: "reason", question: "Why did they call?", answer: "choice", choices: ["book", "cancel"], when: "trigger", trigger: "Did they say why?", reads: [] };
const RUSH = { name: "in-a-rush", about: "", goal: "book today", style: "short, interrupts", facts: { "their name": "Luis" }, state: {}, expects: ["The agent should offer today."], tags: [], behavior: { interrupts: 0.3, pause_s: 1 }, llm: null, tts: null, voice: null };

describe("a TypeScript agent", () => {
  it("gets harness.ts as pinecall new writes it, the constructor imported, and each one appended as an export the class imports", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    expect(appendJudge(home, OFFERS)).toEqual({ path: "agents/front-desk/harness.ts", symbol: "offersNextSlot" });
    expect(appendPersona(home, RUSH)).toEqual({ path: "agents/front-desk/harness.ts", symbol: "inARush" });
    const code = readFileSync(home.harness, "utf8");
    expect(code.startsWith("// The judges and the callers of Front Desk's own, as code")).toBe(true);
    expect(code).toContain('import { ownJudge, ownPersona } from "@pinecall/agents";');
    expect(code).toContain("export const hurried = ownPersona({");
    // The template's judge example sits above its caller, so what is appended ends the file.
    expect(code.indexOf("// A judge of the agent's own")).toBeLessThan(code.indexOf("export const hurried"));
    expect(code.trimEnd().endsWith("});")).toBe(true);
    expect(code).toContain(`
export const offersNextSlot = ownJudge({
  name: "offers-next-slot",
  asks: "Did the agent offer the next free slot?",
  reads: ["facts"],
});

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

  it("writes of a caller's behavior only what differs from the runtime's defaults, and none when nothing does", () => {
    const root = project(["front-desk"]);
    const home = homeOf(`${root}/agents/front-desk/agent.ts`);
    const defaults = { interrupts: 0, pause_s: 0, interferer_db: null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "television" };
    appendPersona(home, { ...RUSH, name: "calm", behavior: defaults });
    appendPersona(home, { ...RUSH, name: "noisy", behavior: { ...defaults, interferer_db: -12, ambience: "cafe" } });
    const code = readFileSync(home.harness, "utf8");
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
    write(root, "agents/notes/harness.py", "# nothing yet\n");
    appendPersona(homeOf(`${root}/agents/notes/agent.py`), RUSH);
    expect(readFileSync(`${root}/agents/notes/harness.py`, "utf8").startsWith("from pinecall import own_persona\n\n# nothing yet\n")).toBe(true);
  });
});

describe("a Python and a Ruby agent", () => {
  it("get harness.py and harness.rb as pinecall new writes them, each one a constant built keyword by keyword", () => {
    const root = project([]);
    write(root, "agents/sales/agent.py", AN_AGENT);
    write(root, "agents/notes/agent.rb", AN_AGENT);
    const python = homeOf(`${root}/agents/sales/agent.py`);
    const ruby = homeOf(`${root}/agents/notes/agent.rb`);
    expect(appendPersona(python, RUSH)).toEqual({ path: "agents/sales/harness.py", symbol: "IN_A_RUSH" });
    expect(appendJudge(ruby, REASON)).toEqual({ path: "agents/notes/harness.rb", symbol: "REASON" });
    const py = readFileSync(python.harness, "utf8");
    expect(py.startsWith('"""The judges and the callers of Sales\'s own, as code')).toBe(true);
    expect(py).toContain("from pinecall import own_persona\n");
    expect(py).toContain("HURRIED = own_persona(");
    expect(py).toContain(`
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
    const rb = readFileSync(ruby.harness, "utf8");
    expect(rb.startsWith("# frozen_string_literal: true\n\n# The judges and the callers of Notes's own, as code")).toBe(true);
    expect(rb).toContain("HURRIED = Pinecall.own_persona(");
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
