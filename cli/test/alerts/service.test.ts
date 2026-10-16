/** The alerts service against the gateway: what each use case sends, and what it makes of the answer. */

import { describe, expect, it } from "vitest";

import { GatewayError, PinecallError, UsageError } from "../../src/errors.js";
import * as service from "../../src/alerts/service.js";
import { answer, KEY, refuse } from "../support/gateway.js";
import { testContext } from "../support/context.js";

const A_MONITOR = {
  id: "mon_8b1d2e3f4a5c",
  name: "slow answers",
  metric: "e2e_median_s",
  above: true,
  threshold: 2,
  window_days: 7,
  agent: null,
  created_by: "ana@clinica.test",
  fired_on: null,
  fired_value: null,
};

describe("monitors", () => {
  it("adds one with the gateway's field names, signed for the env asked", async () => {
    const sent = answer("post", "/v1/monitors", A_MONITOR);
    const { ctx } = testContext({ env: "production" });
    const input = service.AddMonitorInput.parse({ name: "slow answers", metric: "e2e_median_s", above: true, threshold: 2 });
    expect(await service.addMonitor(ctx, input)).toEqual(A_MONITOR);
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toEqual({ name: "slow answers", metric: "e2e_median_s", above: true, threshold: 2, window_days: 7 });
    expect(sent[0]!.env).toBe("production");
    expect(sent[0]!.authorization).toBe(`Bearer ${KEY}`);
  });

  it("sends the agent only when one is named", async () => {
    const sent = answer("post", "/v1/monitors", { ...A_MONITOR, agent: "front-desk" });
    const { ctx } = testContext();
    await service.addMonitor(ctx, service.AddMonitorInput.parse({ name: "x", metric: "held_rate", above: false, threshold: 0.9, windowDays: 30, agent: "front-desk" }));
    expect(sent[0]!.body).toMatchObject({ above: false, window_days: 30, agent: "front-desk" });
  });

  it("refuses a metric the gateway does not name, before anything is sent", () => {
    expect(() => service.AddMonitorInput.parse({ name: "x", metric: "latency", above: true, threshold: 1 })).toThrow(/--metric names one of/);
  });

  it("refuses an id that is not a monitor's without asking the gateway", async () => {
    const { ctx } = testContext();
    await expect(service.removeMonitor(ctx, "8b1d")).rejects.toBeInstanceOf(UsageError);
  });

  it("removes one by its id", async () => {
    const sent = answer("delete", "/v1/monitors/:id");
    const { ctx } = testContext();
    expect(await service.removeMonitor(ctx, "mon_8b1d2e3f4a5c")).toEqual({ id: "mon_8b1d2e3f4a5c" });
    expect(sent[0]!.path).toBe("/v1/monitors/mon_8b1d2e3f4a5c");
  });

  it("lists them out of the gateway's envelope", async () => {
    answer("get", "/v1/monitors", { monitors: [A_MONITOR] });
    const { ctx } = testContext();
    expect(await service.listMonitors(ctx)).toEqual([A_MONITOR]);
  });
});

describe("webhook", () => {
  it("sends the secret once and answers that posts are signed, never the secret", async () => {
    const sent = answer("put", "/v1/webhook");
    const { ctx } = testContext();
    const kept = await service.setWebhook(ctx, service.SetWebhookInput.parse({ url: "https://hooks.example.com/p", secret: "s3cret" }));
    expect(sent[0]!.body).toEqual({ url: "https://hooks.example.com/p", secret: "s3cret" });
    expect(kept).toEqual({ url: "https://hooks.example.com/p", signed: true });
  });

  it("a URL that did not take the test post is a failed check", async () => {
    answer("post", "/v1/webhook/test", { sent: false, error: "502 from the URL" });
    const { ctx } = testContext();
    const failed = service.testWebhook(ctx);
    await expect(failed).rejects.toBeInstanceOf(PinecallError);
    await expect(failed).rejects.toThrow("the URL did not take it: 502 from the URL");
  });

  it("reads none as null", async () => {
    answer("get", "/v1/webhook", null);
    const { ctx } = testContext();
    expect(await service.getWebhook(ctx)).toBeNull();
  });
});

describe("telemetry", () => {
  it("sends the headers' values, and answers only their names", async () => {
    const sent = answer("put", "/v1/telemetry");
    const { ctx } = testContext();
    const input = service.SetCollectorInput.parse({ endpoint: "https://otlp.example.com/v1/traces", headers: { "dd-api-key": "k" } });
    expect(await service.setCollector(ctx, input)).toEqual({ endpoint: "https://otlp.example.com/v1/traces", header_names: ["dd-api-key"], pii: false });
    expect(sent[0]!.body).toEqual({ endpoint: "https://otlp.example.com/v1/traces", headers: { "dd-api-key": "k" }, pii: false });
  });

  it("carries the gateway's refusal whole", async () => {
    refuse("delete", "/v1/telemetry", 403, "a member of the org may not change its telemetry");
    const { ctx } = testContext();
    const failed = service.clearCollector(ctx);
    await expect(failed).rejects.toBeInstanceOf(GatewayError);
    await expect(failed).rejects.toMatchObject({ status: 403, detail: "a member of the org may not change its telemetry" });
  });
});
