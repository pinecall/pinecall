/** `pinecall monitors | webhook | telemetry` as typed: flags into the service, the answer as lines or JSON, refusals as exit codes. */

import { describe, expect, it } from "vitest";

import { answer, refuse } from "../support/gateway.js";
import { run, runJson } from "../support/run.js";

const A_MONITOR = {
  id: "mon_8b1d2e3f4a5c",
  name: "judges slipping",
  metric: "held_rate",
  above: false,
  threshold: 0.9,
  window_days: 7,
  agent: "front-desk",
  created_by: "ana@clinica.test",
  fired_on: "2026-10-15",
  fired_value: 0.82,
};

describe("pinecall monitors", () => {
  it("alone lists them", async () => {
    answer("get", "/v1/monitors", { monitors: [A_MONITOR] });
    const ran = await run(["monitors"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toContain("held_rate below 0.9 over 7 days");
    expect(ran.out).toContain("fired 2026-10-15 at 0.82");
  });

  it("says so when the org watches nothing", async () => {
    answer("get", "/v1/monitors", { monitors: [] });
    expect((await run(["monitors", "list"])).out).toContain("this org watches nothing");
  });

  it("add --below sends a floor", async () => {
    const sent = answer("post", "/v1/monitors", A_MONITOR);
    const ran = await run(["monitors", "add", "judges slipping", "--metric", "held_rate", "--below", "0.9", "--agent", "front-desk"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ name: "judges slipping", metric: "held_rate", above: false, threshold: 0.9, window_days: 7, agent: "front-desk" });
    expect(ran.out).toBe("mon_8b1d2e3f4a5c · judges slipping · held_rate below 0.9 over 7 days · front-desk\n");
  });

  it("add needs one line, above or below, and is refused before anything is sent", async () => {
    const neither = await run(["monitors", "add", "x", "--metric", "calls"]);
    expect(neither.code).toBe(2);
    expect(neither.err).toContain("--above <n> or --below <n>");
    const both = await run(["monitors", "add", "x", "--metric", "calls", "--above", "1", "--below", "2"]);
    expect(both.code).toBe(2);
  });

  it("add refuses a window that is not 1, 7 or 30 days", async () => {
    expect((await run(["monitors", "add", "x", "--metric", "calls", "--above", "1", "--days", "3"])).code).toBe(2);
  });

  it("--json answers the gateway's object whole, anywhere on the line", async () => {
    answer("get", "/v1/monitors", { monitors: [A_MONITOR] });
    expect(await runJson(["monitors"])).toEqual([A_MONITOR]);
    const ran = await run(["monitors", "--json"]);
    expect(JSON.parse(ran.out)).toEqual([A_MONITOR]);
  });

  it("--prod asks production", async () => {
    const sent = answer("get", "/v1/monitors", { monitors: [] });
    await run(["monitors", "--prod"]);
    expect(sent[0]!.env).toBe("production");
  });
});

describe("pinecall webhook", () => {
  it("set --secret reads the secret off stdin, never a flag", async () => {
    const sent = answer("put", "/v1/webhook");
    const ran = await run(["webhook", "set", "https://hooks.example.com/p", "--secret"], { stdin: "s3cret\n" });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ url: "https://hooks.example.com/p", secret: "s3cret" });
    expect(ran.out).toContain("· signed");
    expect(ran.out).not.toContain("s3cret");
  });

  it("set --secret with nothing piped is refused", async () => {
    const ran = await run(["webhook", "set", "https://hooks.example.com/p", "--secret"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("an empty secret");
  });

  it("test exits 1 when the URL did not take it", async () => {
    answer("post", "/v1/webhook/test", { sent: false, error: "timed out" });
    const ran = await run(["webhook", "test"]);
    expect(ran.code).toBe(1);
    expect(ran.err).toContain("the URL did not take it: timed out");
  });

  it("a gateway refusal is exit 1 with the gateway's own sentence", async () => {
    refuse("get", "/v1/webhook", 403, "this key is not the org's admin");
    const ran = await run(["webhook"]);
    expect(ran.code).toBe(1);
    expect(ran.err).toContain("this key is not the org's admin");
  });
});

describe("pinecall telemetry", () => {
  it("set reads each header's value off stdin, in the order named", async () => {
    const sent = answer("put", "/v1/telemetry");
    const ran = await run(["telemetry", "set", "https://cloud.langfuse.com/api/public/otel/v1/traces", "--header", "Authorization", "x-langfuse-ingestion-version", "--pii"], { stdin: "Basic abc\n4\n" });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ endpoint: "https://cloud.langfuse.com/api/public/otel/v1/traces", headers: { Authorization: "Basic abc", "x-langfuse-ingestion-version": "4" }, pii: true });
    expect(ran.out).toContain("headers Authorization, x-langfuse-ingestion-version · with what was said");
  });

  it("refuses a URL that is not one", async () => {
    expect((await run(["telemetry", "set", "not-a-url"])).code).toBe(2);
  });

  it("without a key, nothing is sent and the sentence says how to get one", async () => {
    const ran = await run(["telemetry"], { key: null });
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("pinecall link");
  });
});
