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
    expect(ran.out).toMatch(/cartesia\s+stt,tts\s+no key/);
    expect(ran.out).toContain("3 vendors · ours: llm anthropic · stt deepgram · tts cartesia");
  });

  it("--does keeps one job, and an unknown job is refused", async () => {
    answer("get", "/v1/providers", CATALOG);
    const ran = await run(["providers", "--does", "llm"]);
    expect(ran.out).toContain("1 vendors");
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
