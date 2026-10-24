// runTool: a tool's arguments are checked against the types the class's source says, and only then.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, it } from "vitest";
import { z } from "zod";

import { Agent, CallWorld, describe as describeClass, runTool, seal, setCall, tool, toolNamed, type ToolDeclaration } from "../../src/index.js";

class Desk extends Agent {
  note = "";

  /** Writes down who called and what about. */
  @tool()
  takeMessage(name: string, about: string): string {
    this.note = `${name}: ${about}`;
    return this.note;
  }
}

function desk(): { agent: Desk; message: ToolDeclaration } {
  const agent = seal(new Desk());
  setCall(agent, new CallWorld({ id: "CA_1", contact: "+15550102", channel: "phone" }, () => undefined));
  return { agent, message: toolNamed(agent, "takeMessage") as ToolDeclaration };
}

// The first test runs before the class is described: describe() is once per class, for good.
it("says the parameter types were erased when the class was not handed its own source", async () => {
  const { agent, message } = desk();

  await expect(runTool(agent, message, { name: "Ana", about: "a refund" })).rejects.toThrow(
    "takeMessage: its parameter types were erased when the file was compiled; hand the class its own source with describe(AgentClass, source)",
  );
  expect(agent.note).toBe("");
});

it("runs the tool once the class knows its types, and refuses a value of the wrong one", async () => {
  describeClass(Desk, readFileSync(fileURLToPath(import.meta.url), "utf8"), "run-tool.test.ts");
  const { agent, message } = desk();

  await expect(runTool(agent, message, { name: 5, about: "a refund" })).rejects.toThrow("takeMessage: name must be a string, not a number");
  expect(await runTool(agent, message, { name: "Ana", about: "a refund" })).toBe("Ana: a refund");
});

class Shop extends Agent {
  /** Quotes the items, so many of each. */
  @tool({ params: z.object({ items: z.array(z.string()).min(1), quantity: z.number().int().min(1) }) })
  quote(items: string[], quantity: number): string {
    return `${quantity} × ${items.join(", ")}`;
  }
}

// T F1 (2026-10-24): `z.number().int()` is JSON Schema's `integer`, which no `typeof` says: every call was refused.
it("takes a whole number for an integer parameter, and refuses a fraction naming it", async () => {
  // describe() reads the first class of the source it is handed: Shop's own, from its line on.
  const source = readFileSync(fileURLToPath(import.meta.url), "utf8");
  describeClass(Shop, source.slice(source.indexOf("class Shop")), "run-tool.test.ts");
  const agent = seal(new Shop());
  setCall(agent, new CallWorld({ id: "CA_2", contact: "+15550103", channel: "phone" }, () => undefined));
  const quote = toolNamed(agent, "quote") as ToolDeclaration;
  expect(await runTool(agent, quote, { items: ["latte"], quantity: 2 })).toBe("2 × latte");
  await expect(runTool(agent, quote, { items: ["latte"], quantity: 2.5 })).rejects.toThrow("quote: quantity must be an integer, not 2.5");
});
