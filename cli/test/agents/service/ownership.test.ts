/** Who sets an agent: every write of a code app is refused in one sentence, a Studio agent is written as before. */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import * as service from "../../../src/agents/service/index.js";
import type { Env } from "../../../src/api/client.js";
import { UsageError } from "../../../src/errors.js";
import * as evals from "../../../src/evals/service/index.js";
import * as knowledge from "../../../src/knowledge/service/index.js";
import type { ToolContext } from "../../../src/mcp/tool.js";
import { agent, lexicon } from "../../../src/mcp/tools/agents.js";
import { docs, memory } from "../../../src/mcp/tools/knowledge.js";
import { testContext } from "../../support/context.js";
import { SETTINGS } from "../../support/fixtures.js";
import { answer, GATEWAY, refuse, server, type Sent, studioAgents } from "../../support/gateway.js";
import { folder } from "../../support/project.js";

const SENTENCE = service.SET_IN_ITS_CODE("front-desk");
const WRITE = service.WriteOptions.parse({});
const app = (name: string, kind: "code" | "studio"): Record<string, unknown> => ({ name, kind, release: 1, live_release: 1, failed_why: null, stopped: false, created_by: "m_1", created_at: 0 });

function hostedAs(kind: "code" | "studio"): void {
  answer("get", "/v1/hosted", { apps: [app("front-desk", kind)] });
  answer("get", "/v1/agents", { agents: [] });
}

function nothingListed(): void {
  answer("get", "/v1/hosted", { apps: [] });
  answer("get", "/v1/agents", { agents: [] });
}

// The writes a refused verb must not have sent, read after it ran.
function writesCaught(): () => Sent[] {
  const routes = ["/v1/agents/:slug/settings", "/v1/agents/:slug/lexicon", "/v1/agents/:slug/pipeline/hold-audio", "/v1/agents/:slug/pipeline/hold-audio/played", "/v1/agents/:slug/pipeline/hold-audio/after"].map((path) => answer("put", path, SETTINGS));
  return () => routes.flat();
}

describe("the refusal", () => {
  it("is one sentence naming the app, exit 2, and nothing is read or written", async () => {
    hostedAs("code");
    const written = writesCaught();
    const { ctx } = testContext({ env: "production" });
    const failed = await service.setSettings(ctx, { temperature: 0.3 }, WRITE).catch((error: unknown) => error);
    expect(failed).toBeInstanceOf(UsageError);
    expect((failed as UsageError).exit).toBe(2);
    expect((failed as UsageError).message).toBe("front-desk is set in its code: change it there and deploy");
    expect(written()).toEqual([]);
  });

  it("holds in production, and in the sandbox the write goes to the gateway, which refuses what the class declares", async () => {
    hostedAs("code");
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    await service.setSettings(testContext({ env: "sandbox" }).ctx, { temperature: 0.3 }, WRITE);
    expect(sent).toHaveLength(1);
    await expect(service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE)).rejects.toThrow(SENTENCE);
  });
});

describe("every write of a code app", () => {
  it("is refused through the one guard", async () => {
    hostedAs("code");
    const written = writesCaught();
    const rollback = answer("post", "/v1/agents/:slug/settings/rollback", SETTINGS);
    answer("get", "/v1/knowledge", { bases: [{ base: "faq", chunks: 1, model: "m", pushed_at: 0 }] });
    answer("get", "/v1/evals/groups/:id", { group: { id: "grp_1", agent: "front-desk" }, cases: [] });
    const applied = answer("post", "/v1/evals/groups/:id/apply", SETTINGS);
    const { ctx } = testContext({ env: "production" });
    const file = join(folder(), "pulled.json");
    writeFileSync(file, JSON.stringify({ config: { temperature: 0.3 } }));
    const melody = join(folder(), "espera.mp3");
    writeFileSync(melody, Buffer.from([0x49, 0x44, 0x33]));
    for (const write of [
      () => service.clearSettings(ctx, ["voice"], WRITE),
      () => service.rollbackSettings(ctx, 2, WRITE),
      () => service.pushSettings(ctx, file, WRITE),
      () => service.writeKnowledge(ctx, "Open 9 to 5", WRITE),
      () => service.sayWord(ctx, service.SayWordInput.parse({ word: "Ruiz", say: "roo-EETH" })),
      () => service.hearWords(ctx, service.WordsInput.parse({ words: ["Norte"] })),
      () => service.removeWords(ctx, service.WordsInput.parse({ words: ["Norte"] })),
      () => service.uploadMelody(ctx, undefined, melody),
      () => service.chooseMelody(ctx, undefined, "off"),
      () => service.waitBeforeMelody(ctx, undefined, 1.5),
      () => knowledge.attachBase(ctx, knowledge.AttachBaseInput.parse({ base: "faq" })),
      () => knowledge.detachBase(ctx, knowledge.DetachBaseInput.parse({ base: "faq" })),
      () => knowledge.policy(ctx, knowledge.PolicyInput.parse({ forget: ["card numbers"] })),
      () => evals.applyFix(ctx, "grp_1"),
    ]) await expect(write()).rejects.toThrow(SENTENCE);
    expect([...written(), ...rollback, ...applied]).toEqual([]);
  });

  it("the MCP tools say the same sentence", async () => {
    hostedAs("code");
    const context = Object.assign(testContext({ env: "production" }).ctx, { session: {} as ToolContext["session"] });
    await expect(agent.call({ action: "set", settings: { temperature: 0.3 } }, context)).rejects.toThrow(SENTENCE);
    await expect(lexicon.call({ action: "add", word: "Ruiz", say: "roo-EETH" }, context)).rejects.toThrow(SENTENCE);
    await expect(docs.call({ action: "detach", base: "faq" }, context)).rejects.toThrow(SENTENCE);
    await expect(memory.call({ action: "policy", forget: ["card numbers"] }, context)).rejects.toThrow(SENTENCE);
  });

  it("reading stays", async () => {
    hostedAs("code");
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext({ env: "production" });
    await expect(service.showSettings(ctx, undefined)).resolves.toMatchObject({ agent: "front-desk" });
  });
});

describe("how an agent is told apart", () => {
  it("a Studio agent the box hosts is written as before", async () => {
    studioAgents("front-desk");
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    await service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE);
    expect(sent).toHaveLength(1);
  });

  it("a class held now and hosted nowhere is code", async () => {
    answer("get", "/v1/hosted", { apps: [] });
    answer("get", "/v1/agents", { agents: [{ slug: "front-desk", channels: [], kind: "class" }] });
    await expect(service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE)).rejects.toThrow(SENTENCE);
  });

  it("a key that may not read the box's list still writes a Studio agent held now", async () => {
    refuse("get", "/v1/hosted", 403, "this key does not open app: it opens words");
    answer("get", "/v1/agents", { agents: [{ slug: "front-desk", channels: [], kind: "studio" }] });
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    await service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE);
    expect(sent).toHaveLength(1);
  });

  it("an agent no list names counts as code", async () => {
    nothingListed();
    await expect(service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE)).rejects.toThrow(SENTENCE);
  });

  it("in production, a Studio agent the sandbox alone has is written; a code app the sandbox has stays refused", async () => {
    // One list answered per env, as the gateway does by the header.
    let sandboxApps = [app("front-desk", "studio")];
    server.use(http.get(`${GATEWAY}/v1/hosted`, ({ request }) => HttpResponse.json({ apps: request.headers.get("pinecall-env") === "sandbox" ? sandboxApps : [] })));
    answer("get", "/v1/agents", { agents: [] });
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    await service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE);
    expect(sent).toHaveLength(1);
    sandboxApps = [app("front-desk", "code")];
    await expect(service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.4 }, WRITE)).rejects.toThrow(SENTENCE);
  });

  it("a gateway that fails says so, rather than an agent's kind", async () => {
    refuse("get", "/v1/hosted", 500, "no database");
    answer("get", "/v1/agents", { agents: [] });
    await expect(service.setSettings(testContext({ env: "production" }).ctx, { temperature: 0.3 }, WRITE)).rejects.toThrow("no database");
  });
});
