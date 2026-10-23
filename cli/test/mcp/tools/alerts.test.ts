/** The `alerts` tool: what the org was told, newest first, as many as asked. */

import { describe, expect, it } from "vitest";

import { alerts } from "../../../src/mcp/tools/alerts.js";
import type { ToolContext } from "../../../src/mcp/tool.js";
import { testContext } from "../../support/context.js";
import { answer } from "../../support/gateway.js";

const AN_ALERT = { id: "alr_1", org: "acme", env: "sandbox", agent: "front-desk", kind: "monitor.fired", data: { name: "slow answers", value: 2.4 }, mailed: true, at: "2026-10-22T18:02:11Z" };

function context(): ToolContext {
  return Object.assign(testContext().ctx, { session: {} as ToolContext["session"] });
}

describe("the alerts tool", () => {
  it("answers the org's alerts, fifty unless asked", async () => {
    const sent = answer("get", "/v1/alerts", { alerts: [AN_ALERT] });
    expect(await alerts.call({}, context())).toEqual({ alerts: [AN_ALERT] });
    await alerts.call({ limit: 2 }, context());
    expect(sent.map((one) => one.query)).toEqual([{ limit: "50" }, { limit: "2" }]);
  });

  it("refuses a limit past two hundred before anything is sent", () => {
    expect(() => alerts.call({ limit: 201 }, context())).toThrow();
  });
});
