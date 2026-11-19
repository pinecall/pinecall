// The serve entry's loader: a tenant's class with its own source, and an instance with a line to answer on.

import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { harnessOf } from "../../src/agent/harness.js";
import { docOf } from "../../src/agent/tools.js";
import { instanceFor, loadAgent } from "../../src/serve/load.js";
import { showPrompt } from "../../src/views/render.js";

const AGENT = fileURLToPath(new URL("./clinic/agents/clinica-norte/agent.tsx", import.meta.url));
const TESTED = fileURLToPath(new URL("./tested/agents/front-desk/agent.ts", import.meta.url));
const TWICE = fileURLToPath(new URL("./twice/agents/front-desk/agent.ts", import.meta.url));

describe("loading an agent from disk", () => {
  it("hands the class its own source, so the docstring above it survives the import", async () => {
    const loaded = await loadAgent(AGENT);

    // Ctor.toString() cannot see a comment above the class; only describe(Ctor, source) can.
    expect(docOf(new loaded.ctor())).toContain("recepción de Clínica Norte");
  });

  it("hands back an instance with a line to answer on, so a render may read this.call", async () => {
    const agent = instanceFor(await loadAgent(AGENT));

    expect(agent.call.channel).toBe("web");
    expect(agent.render()).toContain("Saluda y pide nombre");
  });

  it("says where it looked when there is no agent there", async () => {
    await expect(loadAgent("does/not/exist.ts")).rejects.toThrow(/no agent at/);
  });

  it("puts a goldens case into the instance and renders its view at the end", async () => {
    const agent = instanceFor(await loadAgent(AGENT));
    agent.startIn({ patient: { name: "Ana García" }, slots: [{ when: "martes 16:00" }] });

    const page = showPrompt(agent);

    expect(page.indexOf("── identity (static) ──")).toBeLessThan(page.indexOf("── view (dynamic) ──"));
    expect(page).toContain("Ofrece 1 horas");
  });
});

describe("the callers an agent is tested with", () => {
  it("are the ones test/personas.ts holds beside its goldens: each ownPersona it exports, and Pinecall's it names in on", async () => {
    const loaded = await loadAgent(TESTED);

    expect(harnessOf(loaded.ctor).personas).toEqual({ on: ["in-a-hurry"], own: [{ name: "in-a-rush", goal: "I want the first time you have", style: "short, interrupts" }] });
  });

  it("are nobody's to declare for an agent with no such file: the org writes them", async () => {
    expect(harnessOf((await loadAgent(AGENT)).ctor).personas).toBeUndefined();
  });

  it("are refused when the class names them too, by the sentence that says which to keep", async () => {
    await expect(loadAgent(TWICE)).rejects.toThrow(/FrontDesk declares personas in @agent\(\{ … \}\) and .*test\/personas\.ts holds them too: the file is their place — take personas out of the class/);
  });
});
