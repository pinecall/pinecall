/** `pinecall docs | memory | remember` as typed: a push and a score a line each, a miss exits 1, forgetting needs --yes off a terminal. */

import { describe, expect, it } from "vitest";

import { answer } from "../support/gateway.js";
import { SETTINGS } from "../support/fixtures.js";
import { project } from "../support/project.js";
import { run } from "../support/run.js";

const GOLDEN = JSON.stringify([{ asks: "When are you open?", expects: "hours.md" }]);
const SCORE = { base: "front-desk", model: "pplx-embed-v1", questions: 1, k: 8, recall_at_k: 1, ndcg_at_10: 0.931, took_ms: 410.2, misses: [] };

describe("pinecall docs", () => {
  it("push prints the base, the files, the chunks, the language and the time", async () => {
    answer("put", "/v1/knowledge/:base", { base: "front-desk", chunks: 12, language: "english", took_ms: 830.4 });
    const ran = await run(["docs", "push"], { cwd: project(["front-desk"], { "agents/front-desk/docs/hours.md": "# Hours" }) });
    expect(ran.code).toBe(0);
    expect(ran.out).toBe("front-desk · 1 files · 12 chunks · english · 830 ms\n");
  });

  it("eval exits 1 on a miss, and names the question and what came back", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    answer("post", "/v1/knowledge/:base/eval", { ...SCORE, recall_at_k: 0, misses: [{ asks: "When are you open?", expects: ["hours.md"], found: ["pricing.md"] }] });
    const ran = await run(["docs", "eval"], { cwd: project(["front-desk"], { "agents/front-desk/test/goldens/docs.json": GOLDEN }) });
    expect(ran.code).toBe(1);
    expect(ran.out).toContain("front-desk · pplx-embed-v1 · 1 questions · recall@8 0.00 · nDCG@10 0.93 · 410 ms");
    expect(ran.out).toContain("  missed: When are you open? → wanted hours.md, got pricing.md");
  });

  it("eval refuses a k that is no number", async () => {
    expect((await run(["docs", "eval", "--k", "many"])).err).toContain("--k takes a number, not many");
  });

  it("attach says which corner and version it landed in", async () => {
    answer("get", "/v1/knowledge", { bases: [{ base: "front-desk", chunks: 9, model: "acme-embed", pushed_at: 0 }] });
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    answer("put", "/v1/agents/:slug/settings", { ...SETTINGS, yours: { holder: "mem_ana", version: 1, author: "ana", note: null, set_at: 0, config: {} } });
    expect((await run(["docs", "attach", "front-desk", "--k", "4"])).out).toBe("front-desk · front-desk attached · your corner v1\n");
  });

  it("attached lists which agents read which base", async () => {
    answer("get", "/v1/knowledge/attached", { bases: [{ base: "faq", agents: ["front-desk", "sales"] }] });
    expect((await run(["docs", "attached"])).out).toBe("faq · read by front-desk, sales\n");
  });
});

describe("pinecall memory", () => {
  it("<contact> alone shows what was kept, a superseded fact with the day it stopped holding", async () => {
    answer("get", "/v1/contacts/:contact/memory", {
      facts: [
        { text: "allergic to penicillin", category: "health", valid_from: 1_792_000_000, invalidated_at: null },
        { text: "lives in Getafe", category: null, valid_from: 1_791_000_000, invalidated_at: 1_792_000_000 },
      ],
    });
    const ran = await run(["memory", "+34600000001"]);
    expect(ran.out).toMatch(/^- allergic to penicillin \(health\)\n- lives in Getafe · until \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n$/);
  });

  it("forget off a terminal is refused without --yes, and nothing is erased", async () => {
    const ran = await run(["memory", "forget", "+34600000001"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("run it again with --yes");
  });

  it("forget --yes erases and says how many facts", async () => {
    answer("delete", "/v1/contacts/:contact/memory", { forgotten: 4 });
    expect((await run(["memory", "forget", "+34600000001", "--yes"])).out).toBe("forgotten: 4\n");
  });

  it("policy with nothing typed prints the three corners", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const ran = await run(["memory", "policy"]);
    expect(ran.out).toContain("  yours       (team's)");
    expect(ran.out).toContain("    remember  the caller's name");
    expect(ran.out).toContain("  production  v7 · nothing remembered");
  });
});

describe("pinecall remember", () => {
  it("exits 1 when a case broke, with what it kept and what it should not have", async () => {
    answer("post", "/v1/agents/:slug/memory/extraction", {
      agent: "front-desk",
      model: "claude-haiku-5-5",
      cases: 1,
      held: 0,
      took_ms: 1200,
      results: [{ name: "card", held: false, wrote: ["card ends 4242"], broke: [{ check: "never", detail: "kept a card number" }] }],
    });
    const ran = await run(["remember"], { cwd: project(["front-desk"], { "agents/front-desk/test/memory/card.json": JSON.stringify({ said: [["caller", "my card is 4242"]] }) }) });
    expect(ran.code).toBe(1);
    expect(ran.out).toContain("front-desk · claude-haiku-5-5 · 1 case · 0 held · 1200 ms");
    expect(ran.out).toContain("  ✗ card");
    expect(ran.out).toContain("      never  kept a card number");
    expect(ran.out).toContain("      kept      card ends 4242");
    expect(ran.err).toContain("1 of 1 cases broke");
  });
});
