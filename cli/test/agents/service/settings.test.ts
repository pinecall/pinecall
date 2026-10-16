/** An agent's settings against the gateway: a write puts what it moved in the corner it lands on, guarded by that corner. */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as service from "../../../src/agents/service/index.js";
import { NO_LANGUAGE } from "../../../src/agents/service/settings.js";
import { PinecallError, UsageError } from "../../../src/errors.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { SETTINGS, tuningRow } from "../../support/fixtures.js";
import { folder } from "../../support/project.js";

const WRITE = { team: false };

describe("set", () => {
  it("writes only what it moved into a person's empty corner: the rest keeps following the team's", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("mem_ana", 1, {}) });
    const { ctx } = testContext();
    await service.setSettings(ctx, service.SettingsInput.parse({ temperature: 0.3 }), service.WriteOptions.parse({ note: "warmer" }));
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/settings");
    expect(sent[0]!.body).toEqual({ config: { temperature: 0.3 }, if_version: 0, note: "warmer", team: false });
  });

  it("a server's token writes the team's corner and is guarded by its version", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext({ key: "pc_test_server" });
    await service.setSettings(ctx, { voice: "cartesia-luis" }, service.WriteOptions.parse({}));
    expect(sent[0]!.body).toMatchObject({ if_version: 3, config: { voice: "cartesia-luis" } });
  });

  it("--agent is the gateway's slug, from a folder with no project", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext({ cwd: folder() });
    await service.setSettings(ctx, { language: "es" }, service.WriteOptions.parse({ agent: "sales" }));
    expect(sent[0]!.path).toBe("/v1/agents/sales/settings");
  });

  it("names a model the four ways, and refuses one that names none", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await service.setSettings(ctx, { llm: "sonnet", judge: "openai" }, WRITE);
    expect(sent[0]!.body).toMatchObject({ config: { llm: "anthropic/claude-sonnet-5", judge: "openai" } });
    await expect(service.setSettings(ctx, { llm: "openai/" }, WRITE)).rejects.toThrow(/--llm openai\/ names no model/);
  });
});

describe("the fields as the wire takes them", () => {
  const standing = SETTINGS.team.config;

  it("a greeting is words, the model's own, or the model's own with an instruction", () => {
    expect(service.fieldsOf({ greeting: "Hello" }, {}).greeting).toEqual({ say: "Hello" });
    expect(service.fieldsOf({ greeting: "improvise" }, {}).greeting).toEqual({ reply: "" });
    expect(service.fieldsOf({ greeting: "improvise: warmly, in Spanish" }, {}).greeting).toEqual({ reply: "warmly, in Spanish" });
  });

  it("whether the greeting may be interrupted keeps the greeting that stands", () => {
    expect(service.fieldsOf({ "greeting-interruptible": "on" }, standing).greeting).toEqual({ say: "Clínica Norte, good morning", allow_interruptions: true });
  });

  it("a turn knob keeps the others that stand", () => {
    expect(service.fieldsOf({ "eot-threshold": 0.7 }, standing).turn).toEqual({ endpointing_ms: 400, eot_threshold: 0.7 });
  });

  it("the longest call is minutes sent as seconds, off as 0; recording is a boolean; any hang-up is an empty when", () => {
    expect(service.fieldsOf({ "max-duration": 15, record: "off", hangup: "any" }, {})).toEqual({ max_duration_s: 900, record: false, hangup: { when: "" } });
    expect(service.fieldsOf({ "max-duration": "off" }, {}).max_duration_s).toBe(0);
  });

  it("memory's lists keep the one not named", () => {
    expect(service.fieldsOf({ forget: ["card numbers"] }, standing).memory).toEqual({ remember: ["the caller's name"], forget: ["card numbers"] });
  });

  it("refuses what no call could run with, before anything is read", () => {
    expect(() => service.SettingsInput.parse({ "max-duration": 61 })).toThrow();
    expect(() => service.SettingsInput.parse({ "eot-threshold": 1.5 })).toThrow();
    expect(() => service.SettingsInput.parse({ language: " " })).toThrow(NO_LANGUAGE);
    expect(() => service.SettingsInput.parse({ "end-of-turn": "vad" })).toThrow();
  });
});

describe("clear, history, rollback", () => {
  it("clear of a field only the team's corner sets changes nothing in yours, and says so", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await expect(service.clearSettings(ctx, ["voice"], WRITE)).rejects.toThrow(/nothing changes in your corner/);
  });

  it("clear takes the fields named out of the corner's own row, and every field with none named", async () => {
    const mine = { voice: "cartesia-luis", turn: { endpointing_ms: 300 }, language: "es" };
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("mem_ana", 2, mine) });
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await service.clearSettings(ctx, ["voice", "turn"], WRITE);
    await service.clearSettings(ctx, [], WRITE);
    expect(sent.map((one) => (one.body as { config: unknown; note: string }).config)).toEqual([{ language: "es" }, {}]);
    expect(sent.map((one) => (one.body as { note: string }).note)).toEqual(["cleared voice, turn", "cleared"]);
  });

  it("clear refuses a field it does not know", async () => {
    const { ctx } = testContext();
    await expect(service.clearSettings(ctx, ["colour"], WRITE)).rejects.toThrow(/no field called colour/);
  });

  it("history asks the team's corner with --team", async () => {
    const sent = answer("get", "/v1/agents/:slug/settings/history", { world: "sandbox", holder: "", rows: [] });
    const { ctx } = testContext();
    await service.settingsHistory(ctx, undefined, true);
    expect(sent[0]!.query).toEqual({ team: "true" });
  });

  it("rollback takes a version that is one", async () => {
    const sent = answer("post", "/v1/agents/:slug/settings/rollback", SETTINGS);
    const { ctx } = testContext();
    await expect(service.rollbackSettings(ctx, 0, WRITE)).rejects.toBeInstanceOf(UsageError);
    await service.rollbackSettings(ctx, 2, WRITE);
    expect(sent[0]!.body).toEqual({ version: 2, team: false });
  });
});

describe("pull, push and knowledge", () => {
  it("pull answers the corner read as a file, and refuses an empty one", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    expect(await service.pullSettings(ctx, undefined, false)).toEqual({ agent: "front-desk", world: "sandbox", holder: "", version: 3, config: SETTINGS.team.config });
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, team: null });
    await expect(service.pullSettings(ctx, undefined, false)).rejects.toBeInstanceOf(PinecallError);
  });

  it("push sends a pulled file's config unguarded, as CI applies it", async () => {
    const sent = answer("put", "/v1/agents/:slug/settings", { ...SETTINGS, team: tuningRow("", 4, { voice: "x" }) });
    const file = join(folder(), "settings.json");
    writeFileSync(file, JSON.stringify({ agent: "front-desk", world: "sandbox", holder: "", version: 3, config: { voice: "x" } }));
    const { ctx } = testContext({ key: "pc_test_ci" });
    const pushed = await service.pushSettings(ctx, file, service.WriteOptions.parse({ team: true }));
    expect(sent[0]!.body).toEqual({ config: { voice: "x" }, if_version: null, note: `pushed from ${file}`, team: true });
    expect(pushed).toMatchObject({ corner: "the team's corner", version: 4 });
  });

  it("knowledge kept empty takes the field out, so the default stands again", async () => {
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("mem_ana", 1, { knowledge: "Open 9 to 5." }) });
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await service.writeKnowledge(ctx, "  \n", WRITE);
    expect((sent[0]!.body as { config: unknown }).config).toEqual({});
  });
});
