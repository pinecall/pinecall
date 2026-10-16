/** The limits report: the env's limits, the org's own vendors sorted, and the day the monthly quotas start again. */

import { describe, expect, it } from "vitest";

import * as service from "../../src/billing/service.js";
import { answer } from "../support/gateway.js";
import { testContext } from "../support/context.js";
import { LIMITS } from "../support/fixtures.js";

describe("getLimits", () => {
  it("asks the limits and the org's keys in the env asked, and dates the restart the first of next month, UTC", async () => {
    const limits = answer("get", "/v1/limits", { ...LIMITS, world: "production" });
    const keys = answer("get", "/v1/provider-keys", { vendors: ["openai", "anthropic"] });
    const { ctx } = testContext({ env: "production" });
    const report = await service.getLimits(ctx, new Date("2026-10-31T23:30:00Z"));
    expect(report).toEqual({ env: "production", limits: { ...LIMITS, world: "production" }, brought: ["anthropic", "openai"], starts_again: "2026-11-01" });
    expect([limits[0]!.env, keys[0]!.env]).toEqual(["production", "production"]);
  });

  it("rolls December over into January", async () => {
    answer("get", "/v1/limits", LIMITS);
    answer("get", "/v1/provider-keys", { vendors: [] });
    const { ctx } = testContext();
    expect((await service.getLimits(ctx, new Date("2026-12-15T00:00:00Z"))).starts_again).toBe("2027-01-01");
  });
});
