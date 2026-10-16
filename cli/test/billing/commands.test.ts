/** `pinecall limits` as typed: a line per quota, monthly ones dated, and whose keys a call runs on. */

import { describe, expect, it } from "vitest";

import { answer } from "../support/gateway.js";
import { run, runJson } from "../support/run.js";
import { LIMITS } from "../support/fixtures.js";

describe("pinecall limits", () => {
  it("prints the env, each quota as used of limit, and the keys line", async () => {
    answer("get", "/v1/limits", LIMITS);
    answer("get", "/v1/provider-keys", { vendors: ["anthropic"] });
    const ran = await run(["limits"]);
    expect(ran.code).toBe(0);
    const lines = ran.out.split("\n");
    expect(lines[0]).toBe("sandbox");
    expect(ran.out).toMatch(/minutes\s+12 of 30 · starts again 1 \w{3}/);
    expect(ran.out).toMatch(/simulations\s+0, no limit\n/);
    expect(ran.out).toMatch(/LLM tokens\s+20500\.5 of 1000000/);
    expect(ran.out).toMatch(/bought numbers\s+0 of 0\n/);
    expect(ran.out).toContain("yours: anthropic · lent by the deployment: google, cartesia, deepgram");
    expect(ran.out).not.toContain("more:");
  });

  it("says where to buy more when the deployment sells plans, and that it lends nothing", async () => {
    answer("get", "/v1/limits", { ...LIMITS, lends: [], billing_url: "https://billing.pinecall.io/org" });
    answer("get", "/v1/provider-keys", { vendors: [] });
    const ran = await run(["limits"]);
    expect(ran.out).toContain("yours: none · lent by the deployment: none, bring a key for every vendor");
    expect(ran.out).toContain("more: https://billing.pinecall.io/org");
  });

  it("--json is the report whole", async () => {
    answer("get", "/v1/limits", { ...LIMITS, lends: null });
    answer("get", "/v1/provider-keys", { vendors: ["openai"] });
    const report = await runJson<{ env: string; brought: string[]; limits: { lends: null } }>(["limits"]);
    expect(report.env).toBe("sandbox");
    expect(report.brought).toEqual(["openai"]);
    expect(report.limits.lends).toBeNull();
  });
});
