/** `pinecall new | generate` as typed: files written with no key and no gateway, the next steps printed. */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { folder, project } from "../support/project.js";
import { run } from "../support/run.js";

describe("pinecall new", () => {
  it("writes ./<name> with no key at all, and prints the next steps: the first agent among them", async () => {
    const here = folder();
    const ran = await run(["new", "clinica-dental"], { cwd: here, key: null });
    expect(ran.code).toBe(0);
    expect(existsSync(join(here, "clinica-dental/agents"))).toBe(true);
    expect(ran.out).toContain("▸ clinica-dental · a TypeScript project, no agent yet");
    expect(ran.out).toContain("  pinecall generate agent <name>");
    expect(ran.out).toContain("  npm install");
  });

  it("--agent writes the first agent in its own folder", async () => {
    const here = folder();
    const ran = await run(["new", "clinica-dental", "--agent", "sofia"], { cwd: here, key: null });
    expect(ran.code).toBe(0);
    expect(existsSync(join(here, "clinica-dental/agents/sofia/agent.tsx"))).toBe(true);
    expect(ran.out).toContain("▸ clinica-dental · a TypeScript project · agents/sofia/");
    expect(ran.out).not.toContain("generate agent");
  });

  it("--ruby writes a Ruby project, and two languages are refused", async () => {
    const here = folder();
    expect((await run(["new", "sales", "--ruby"], { cwd: here })).out).toContain("bundle install");
    expect((await run(["new", "other", "--ruby", "--python"], { cwd: here })).code).toBe(2);
  });

  it("refuses a name the gateway would not take", async () => {
    expect((await run(["new", "FrontDesk"], { cwd: folder() })).code).toBe(2);
  });
});

describe("pinecall generate", () => {
  it("agent writes a second agent and says each file", async () => {
    const root = project(["front-desk"]);
    const ran = await run(["generate", "agent", "sales"], { cwd: root });
    expect(ran.code).toBe(0);
    expect(ran.out).toContain(`  wrote ${join("agents", "sales", "agent.tsx")}`);
  });

  it("g golden takes the lines in order and the tools", async () => {
    const root = project(["front-desk"]);
    const ran = await run(["g", "golden", "asks-for-a-refund", "--say", "Hi, I want a refund.", "--say", "It's Ana Ruiz.", "--tool", "takeMessage"], { cwd: root, key: null });
    expect(ran.code).toBe(0);
    expect(ran.out).toBe(`  wrote ${join("agents", "front-desk", "test", "goldens", "asks-for-a-refund.json")}\n`);
    expect(JSON.parse(readFileSync(join(root, "agents/front-desk/test/goldens/asks-for-a-refund.json"), "utf8")).turns).toEqual([{ say: "Hi, I want a refund." }, { say: "It's Ana Ruiz." }]);
  });

  it("golden needs --say", async () => {
    expect((await run(["generate", "golden", "x"])).code).toBe(2);
  });
});
