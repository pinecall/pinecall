// Ring 0: the class as software — no network, no key, no model.

import { readFileSync } from "node:fs";

import { CallWorld, describe as describeClass, promptOf, runTool, seal, setCall, toolNamed, type ToolDeclaration } from "@pinecall/agents";
import { beforeEach, expect, it } from "vitest";

import {{Class}} from "../agent.js";

// The class's own source, as the CLI hands it over: the parameters' types survive the transpiler.
describeClass({{Class}}, readFileSync(new URL("../agent.tsx", import.meta.url), "utf8"));

let agent: {{Class}};

beforeEach(() => {
  agent = seal(new {{Class}}());
  setCall(agent, new CallWorld({ id: "CA_1", contact: "+15550100", channel: "phone" }, () => undefined));
});

function view(): string {
  return promptOf(agent).blocks.find((block) => block.name === "view")?.text ?? "";
}

it("asks for a message until there is one", () => {
  expect(view()).toContain("ask only for what the caller has not said yet");
});

it("ends the call with the message it took", async () => {
  await runTool(agent, toolNamed(agent, "takeMessage") as ToolDeclaration, { name: "Ana", about: "a refund" });

  expect(agent.stage).toBe("done");
  expect(view()).toContain("Ana, about a refund");
});

it("writes nothing down on a blank or a guess", async () => {
  await expect(runTool(agent, toolNamed(agent, "takeMessage") as ToolDeclaration, { name: "Ana", about: "not specified" })).rejects.toThrow(
    "Nothing was written down",
  );
  expect(agent.stage).toBe("ask");
});
