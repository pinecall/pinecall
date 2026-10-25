/** `pinecall agent | lexicon | pipeline | voices` as typed: the corners as a table, flags into one version, the words, the stages. */

import { describe, expect, it } from "vitest";

import { answer, refuse } from "../support/gateway.js";
import { lexiconRow, SETTINGS, tuningRow } from "../support/fixtures.js";
import { folder } from "../support/project.js";
import { run, runJson } from "../support/run.js";

describe("pinecall agent", () => {
  it("alone prints the corners side by side: the team's value under yours when yours is empty", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const ran = await run(["agent"]);
    expect(ran.code).toBe(0);
    const lines = ran.out.split("\n");
    expect(lines[0]).toBe("front-desk · sandbox");
    expect(lines.find((line) => line.trimStart().startsWith("voice "))).toMatch(/voice\s+\(team's\)\s+cartesia-ana\s+cartesia-ana/);
    expect(ran.out).toMatch(/greeting\s+\(team's\)\s+"Clínica Norte, good morning"/);
    expect(ran.out).toContain("yours: nothing set · team: v3 · ana@clinica.test");
  });

  it("a field the class declares reads `class` in every corner", async () => {
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, fixed: ["voice"] });
    expect((await run(["agent"])).out).toMatch(/\n {2}voice\s+class\s+class\s+class\n/);
  });

  it("--agent is a slug read from any folder", async () => {
    const sent = answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const ran = await run(["agent", "--agent", "sales"], { cwd: folder() });
    expect(ran.code).toBe(0);
    expect(sent[0]!.path).toBe("/v1/agents/sales/settings");
  });

  it("set turns the flags into one version: numbers as numbers, options as pairs, phrases as a list", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const ran = await run(["agent", "set", "--temperature", "0.4", "--llm-option", "reasoning_effort=low", "--llm-option", "max_tokens=300", "--record", "off", "--max-duration", "off", "--remember", "the caller's name", "the reason they called", "--note", "tighter"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toMatchObject({
      config: { temperature: 0.4, llm_options: { reasoning_effort: "low", max_tokens: 300 }, record: false, max_duration_s: 0, memory: { remember: ["the caller's name", "the reason they called"], forget: [] } },
      note: "tighter",
      team: false,
    });
  });

  it("set refuses a number that is not one, and a choice that is not on or off", async () => {
    expect((await run(["agent", "set", "--temperature", "warm"])).err).toContain("--temperature takes a number, not warm");
    expect((await run(["agent", "set", "--record", "maybe"])).code).toBe(2);
    expect((await run(["agent", "set", "--llm-option", "no-equals"])).err).toContain("is not key=value");
  });

  it("clear takes the fields named out of your own row, and a bare clear is refused", async () => {
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("mem_ana", 2, { greeting: { say: "Hi" }, memory: { remember: ["x"], forget: [] }, voice: "v" }) });
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    await run(["agent", "clear", "greeting", "memory"]);
    expect((sent[0]!.body as { config: Record<string, unknown> }).config).toEqual({ voice: "v" });
    const bare = await run(["agent", "clear"]);
    expect(bare.code).toBe(2);
    expect(bare.err).toContain("name the fields to clear, or --all");
  });

  it("pull prints your own row as a file", async () => {
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("mem_ana", 2, { voice: "v" }) });
    const ran = await run(["agent", "pull"]);
    expect(JSON.parse(ran.out)).toEqual({ agent: "front-desk", world: "sandbox", holder: "mem_ana", version: 2, config: { voice: "v" } });
  });

  it("knowledge says when nothing is known by heart", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    expect((await run(["agent", "knowledge"])).out).toContain("front-desk knows nothing by heart in your corner");
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, team: tuningRow("", 3, { knowledge: "Open 9 to 5.\nClosed Sundays.\n" }) });
    expect((await run(["agent", "knowledge"])).out).toBe("Open 9 to 5.\nClosed Sundays.\n");
  });

  it("list prints each process holding the org's agents", async () => {
    answer("get", "/v1/apps", { apps: [{ app: "app_1", agents: ["front-desk"], env: "sandbox", host: "ana-macbook", address: null, sdk: "ts 0.10.1", holder: { holder: "mem_ana", name: "ana@clinica.test" }, connected_at: 1_792_150_000 }] });
    expect((await run(["agent", "list"])).out).toMatch(/^app_1 {2}front-desk {2}ana@clinica\.test · ana-macbook · ts 0\.10\.1 · since \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n$/);
  });
});

describe("pinecall kill", () => {
  it("kills the agent beside the class, or the one named from any folder, and says nothing was erased", async () => {
    const sent = answer("post", "/v1/agents/:slug/kill", { agent: "front-desk", envs: ["sandbox"], apps: ["app_1"] });
    const ran = await run(["kill"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/kill");
    expect(ran.out).toContain("killed front-desk in sandbox: one app let go of it (app_1) and kept their other agents");
    expect(ran.out).toContain("its settings and calls stay");
    await run(["kill", "sales"], { cwd: folder() });
    expect(sent[1]!.path).toBe("/v1/agents/sales/kill");
  });

  it("says the gateway's refusal of a key that is not an admin's", async () => {
    refuse("post", "/v1/agents/:slug/kill", 403, "killing an agent is an admin's: it cuts every holder's app, and this key does not open team and app");
    const ran = await run(["kill", "front-desk"]);
    expect(ran.code).not.toBe(0);
    expect(ran.err).toContain("killing an agent is an admin's");
  });
});

describe("pinecall lexicon", () => {
  it("alone prints the words read and each corner's version", async () => {
    answer("get", "/v1/agents/:slug/lexicon", { world: "sandbox", yours: null, team: lexiconRow("", 2, [{ word: "Vidal", spoken: "bee-DAHL" }], ["Norte"]), production: null, fixed: [] });
    const ran = await run(["lexicon"]);
    expect(ran.out).toContain('said     Vidal → "bee-DAHL"');
    expect(ran.out).toContain("heard    Norte");
    expect(ran.out).toContain("yours: nothing set · team: v2");
  });

  it("add needs --say", async () => {
    expect((await run(["lexicon", "add", "Vidal"])).code).toBe(2);
  });

  it("hear takes several words at once", async () => {
    answer("get", "/v1/agents/:slug/lexicon", { world: "sandbox", yours: null, team: null, production: null, fixed: [] });
    const sent = answer("put", "/v1/agents/:slug/lexicon", { world: "sandbox", yours: null, team: null, production: null, fixed: [] });
    await run(["lexicon", "hear", "Norte", "Vidal"]);
    expect((sent[0]!.body as { lexicon: unknown }).lexicon).toEqual({ said: [], heard: ["Norte", "Vidal"] });
  });
});

describe("pinecall pipeline", () => {
  it("prints the three stages, the greeting, the medians and what is not available", async () => {
    answer("get", "/v1/agents/:slug/pipeline", {
      agent: "front-desk",
      hears: { vendor: "deepgram", model: "flux-general-multi", voice_id: null, language: "es" },
      decides: { vendor: "anthropic", model: "claude-haiku-5-5", voice_id: null, language: null },
      speaks: { vendor: "cartesia", model: "sonic-3", voice_id: "cartesia-ana", language: "es" },
      greeting: { say: null, reply: "warmly" },
      voices: [],
      calls: 12,
      medians: [{ name: "e2e_latency", seconds: 1.234, turns: 80 }, { name: "talk_share", seconds: 0.42, turns: 80 }],
      unavailable_reasons: { rime: "no key" },
    });
    const ran = await run(["pipeline"]);
    expect(ran.out).toContain("front-desk · 12 calls");
    expect(ran.out).toContain("hears     deepgram · flux-general-multi · es");
    expect(ran.out).toContain("speaks    cartesia · sonic-3 · cartesia-ana · es");
    expect(ran.out).toContain("greeting  the model improvises: warmly");
    expect(ran.out).toContain("e2e_latency 1.23s · talk_share 42%");
    expect(ran.out).toContain("rime is not available here: no key");
  });
});

describe("pinecall voices", () => {
  it("alone lists the gateway's own vendor's voices as a table", async () => {
    answer("get", "/v1/providers", { providers: [{ name: "cartesia", voices_listed: true }], defaults: { tts: "cartesia" } });
    answer("get", "/v1/voices", { tts: "cartesia", language: null, voices: [{ id: "ana-es", name: "Ana", language: "es", description: "", gender: "female", country: "ES", accent: "castilian" }] });
    const ran = await run(["voices"]);
    expect(ran.out).toMatch(/^ID\s+NAME\s+LANGUAGE\s+GENDER\s+FROM\nana-es\s+Ana\s+es\s+female\s+ES castilian\n$/);
  });

  it("--json is the list", async () => {
    answer("get", "/v1/providers", { providers: [{ name: "cartesia", voices_listed: true }], defaults: { tts: "cartesia" } });
    answer("get", "/v1/voices", { tts: "cartesia", language: "es", voices: [] });
    expect(await runJson(["voices", "--language", "es"])).toEqual([]);
  });
});
