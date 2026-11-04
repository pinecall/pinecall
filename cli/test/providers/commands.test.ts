/** `pinecall providers` as typed: the catalog as a table, a key read off stdin and never printed, the org's vendors by name. */

import { describe, expect, it } from "vitest";

import { answer } from "../support/gateway.js";
import { run } from "../support/run.js";
import { CATALOG } from "../support/fixtures.js";

describe("pinecall providers", () => {
  it("alone is the catalog, then how many and the platform's defaults", async () => {
    answer("get", "/v1/providers", CATALOG);
    const ran = await run(["providers"]);
    expect(ran.code).toBe(0);
    // The vendors that run a call, then how many wait and on what: a vendor with no key is a count, not a row.
    expect(ran.out).toBe(
      [
        "VENDOR     DOES  STANDING",
        "anthropic  llm   ready",
        "deepgram   stt   ready",
        "2 run a call here · 1 have no key · ours: llm anthropic · stt deepgram · tts cartesia",
        "  → pinecall providers add <vendor> brings a key · --all lists every vendor and the realtime models",
        "",
      ].join("\n"),
    );
  });

  it("--all lists every vendor with its standing, and the realtime models a row a vendor", async () => {
    answer("get", "/v1/providers", { ...CATALOG, realtime: { xai: ["grok-voice-3.0", "grok-voice-latest"] } });
    const ran = await run(["providers", "--all"]);
    expect(ran.out).toMatch(/\ncartesia\s+stt tts\s+no key\n/);
    expect(ran.out).toMatch(/\nREALTIME\s+MODELS\nxai\s+grok-voice-3\.0, grok-voice-latest\n/);
    expect(ran.out).toContain("  → pinecall providers add <vendor> brings a key\n");
  });

  it("--does keeps one job, and an unknown job is refused", async () => {
    answer("get", "/v1/providers", CATALOG);
    const ran = await run(["providers", "--does", "llm"]);
    expect(ran.out).toContain("\n1 run a call here · ours:");
    const wrong = await run(["providers", "--does", "vision"]);
    expect(wrong.code).toBe(2);
    expect(wrong.err).toContain("no modality called vision");
  });

  it("add reads the key off stdin and prints the vendor alone", async () => {
    const sent = answer("put", "/v1/provider-keys/:vendor");
    const ran = await run(["providers", "add", "openai"], { stdin: "sk-proj-123\n" });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ key: "sk-proj-123" });
    expect(ran.out).toBe("openai\n");
    expect(ran.out + ran.err).not.toContain("sk-proj-123");
  });

  it("add with nothing piped brings nothing", async () => {
    const ran = await run(["providers", "add", "openai"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("no key was given");
  });

  it("list prints the vendors and nothing else", async () => {
    answer("get", "/v1/provider-keys", { vendors: ["anthropic", "openai"] });
    expect((await run(["providers", "list"])).out).toBe("anthropic\nopenai\n");
    answer("get", "/v1/provider-keys", { vendors: [] });
    expect((await run(["providers", "list"])).out).toContain("no provider key brought");
  });
});
