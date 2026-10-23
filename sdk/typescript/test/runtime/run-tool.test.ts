// runTool: a tool's arguments are checked against the types the class's source says, and only then.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, it } from "vitest";

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
