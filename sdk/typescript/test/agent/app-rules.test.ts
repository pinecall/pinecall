// The rules a voice app gives its agents: in the identity block of each, and absent for an agent of no app.

import { expect, it } from "vitest";

import { Agent, seal } from "../../src/agent/agent.js";
import { appRulesOf, setAppRules } from "../../src/agent/app-rules.js";
import { promptOf } from "../../src/views/render.js";

class OfAnApp extends Agent {}
class OfNoApp extends Agent {}

function identityOf(agent: Agent): string {
  return promptOf(agent).blocks.find((block) => block.name === "identity")?.text ?? "";
}

it("are read into the identity block of every instance of the class, one per line", () => {
  setAppRules(OfAnApp, ["Never quote a price that is not in the price list.", "Read a time back before booking it."]);
  const identity = identityOf(seal(new OfAnApp()));
  expect(identity).toContain("<app_rules>\n- Never quote a price that is not in the price list.\n- Read a time back before booking it.\n</app_rules>");
});

it("leave the prompt of an agent of no app as it was", () => {
  expect(appRulesOf(new OfNoApp())).toBe("");
  expect(identityOf(seal(new OfNoApp()))).not.toContain("app_rules");
});

it("are taken away by an empty list", () => {
  setAppRules(OfAnApp, []);
  expect(identityOf(seal(new OfAnApp()))).not.toContain("app_rules");
});
