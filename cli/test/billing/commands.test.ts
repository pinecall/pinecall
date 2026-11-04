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
    expect(lines[1]).toMatch(/^QUOTA\s+USED\s+LIMIT\s+STARTS AGAIN$/);
    expect(ran.out).toMatch(/\nminutes\s+12\s+30\s+1 \w{3}\n/);
    // The quotas untouched and unlimited are one line, not rows of zeros.
    expect(ran.out).toContain("\nnothing used, no limit: messages · simulations · seats\n");
    expect(ran.out).not.toMatch(/simulations\s+0/);
    expect(ran.out).toMatch(/\nLLM tokens\s+20,500\.5\s+1,000,000\s+1 \w{3}\n/);
    expect(ran.out).toMatch(/\nbought numbers\s+0\s+0\n/);
    expect(ran.out).toMatch(/\nbudget\s+\$4\.25\s+\$60\s+1 \w{3}\n/);
    expect(ran.out).toMatch(/\nhosted apps\s+1\s+3\n/);
    expect(ran.out).toMatch(/\nknowledge chunks\s+340\s+2,000\n/);
    expect(ran.out).toContain("\nkeys  yours: anthropic · the runtime lends google, cartesia, deepgram\n");
    expect(ran.out).not.toContain("→");
  });

  it("says where to buy more when the deployment sells plans, and that it lends nothing", async () => {
    answer("get", "/v1/limits", { ...LIMITS, lends: [], billing_url: "https://billing.pinecall.io/org" });
    answer("get", "/v1/provider-keys", { vendors: [] });
    const ran = await run(["limits"]);
    expect(ran.out).toContain("keys  yours: none · the runtime lends none: bring a key for every vendor");
    expect(ran.out).toContain("  → https://billing.pinecall.io/org buys more");
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
