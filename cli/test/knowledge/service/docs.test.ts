/** The documents an agent searches: a folder of Markdown pushed as a base, a golden scored at the k a turn reads, a base attached in a corner. */

import { describe, expect, it } from "vitest";

import { PinecallError, UsageError } from "../../../src/errors.js";
import * as service from "../../../src/knowledge/service/docs.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { SETTINGS, tuningRow } from "../../support/fixtures.js";
import { folder, project, write } from "../../support/project.js";

const PUSHED = { base: "front-desk", chunks: 12, took_ms: 830.4 };
const SCORE = { base: "front-desk", model: "pplx-embed-v1", questions: 2, k: 4, recall_at_k: 1, ndcg_at_10: 0.93, took_ms: 410, misses: [] };
const GOLDEN = JSON.stringify([{ asks: "When are you open?", expects: "hours.md" }, { asks: "Do you take insurance?", expects: "insurance.md" }]);

describe("push", () => {
  it("sends every *.md under the agent's agents/<name>/docs/ as the slug's base, paths POSIX and sorted", async () => {
    const root = project(["front-desk"], { "agents/front-desk/docs/hours.md": "# Hours\n9 to 5", "agents/front-desk/docs/policies/insurance.md": "# Insurance", "agents/front-desk/docs/notes.txt": "not sent" });
    const sent = answer("put", "/v1/knowledge/:base", PUSHED);
    const { ctx } = testContext({ cwd: root });
    expect(await service.pushDocs(ctx, {})).toEqual([{ ...PUSHED, files: 2 }]);
    expect(sent[0]!.path).toBe("/v1/knowledge/front-desk");
    expect(sent[0]!.body).toEqual({ files: [{ path: "hours.md", text: "# Hours\n9 to 5" }, { path: "policies/insurance.md", text: "# Insurance" }] });
  });

  it("at a project of several agents pushes each that has documents, and names the rest", async () => {
    const root = project(["front-desk", "sales"], { "agents/sales/docs/pricing.md": "# Pricing" });
    answer("put", "/v1/knowledge/:base", ({ path }) => ({ ...PUSHED, base: path.split("/").pop() }));
    const { ctx } = testContext({ cwd: root });
    expect(await service.pushDocs(ctx, {})).toEqual([
      { agent: "front-desk", skipped: `no documents at ${root}/agents/front-desk/docs` },
      { agent: "sales", base: "sales", chunks: 12, took_ms: 830.4, files: 1 },
    ]);
  });

  it("a folder and a base both named need no project", async () => {
    const dir = folder();
    write(dir, "faq.md", "# FAQ");
    answer("put", "/v1/knowledge/:base", { ...PUSHED, base: "faq" });
    const { ctx } = testContext({ cwd: folder() });
    expect((await service.pushDocs(ctx, { dir, base: "faq" }))[0]).toMatchObject({ base: "faq", files: 1 });
  });

  it("refuses a folder that is not there, or holds no Markdown", async () => {
    const { ctx } = testContext();
    await expect(service.pushDocs(ctx, { dir: "/nowhere/at/all", base: "x" })).rejects.toThrow(service.NO_DIRECTORY("/nowhere/at/all"));
    const empty = folder();
    await expect(service.pushDocs(ctx, { dir: empty, base: "x" })).rejects.toThrow(service.NO_MARKDOWN(empty));
  });
});

describe("eval", () => {
  it("asks at the k the agent reads the base with, off its attachment", async () => {
    const root = project(["front-desk"], { "agents/front-desk/test/goldens/docs.json": GOLDEN });
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, team: tuningRow("", 3, { bases: [{ base: "front-desk", k: 4 }] }) });
    const sent = answer("post", "/v1/knowledge/:base/eval", SCORE);
    const { ctx } = testContext({ cwd: root });
    expect(await service.evalDocs(ctx, {})).toEqual([SCORE]);
    expect(sent[0]!.body).toEqual({ questions: JSON.parse(GOLDEN), k: 4 });
  });

  it("a k typed wins, and no attachment leaves it to the gateway", async () => {
    const root = project(["front-desk"], { "agents/front-desk/test/goldens/docs.json": GOLDEN });
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("post", "/v1/knowledge/:base/eval", SCORE);
    const { ctx } = testContext({ cwd: root });
    await service.evalDocs(ctx, { k: 8 });
    await service.evalDocs(ctx, {});
    expect(sent.map((one) => (one.body as { k?: number }).k)).toEqual([8, undefined]);
  });

  it("refuses a golden that is not there or holds no questions", async () => {
    const { ctx } = testContext();
    await expect(service.evalDocs(ctx, { golden: "/nowhere.json", base: "x" })).rejects.toThrow(/no golden at \/nowhere\.json/);
    const empty = write(folder(), "docs.json", "[]");
    await expect(service.evalDocs(ctx, { golden: empty, base: "x" })).rejects.toThrow(/holds no questions/);
  });

  it("reads k off the corner a key reads", () => {
    const answer = { ...SETTINGS, team: tuningRow("", 3, { bases: [{ base: "faq", k: 2 }, { base: "front-desk" }] }) };
    expect(service.kReadWith(answer as never, "faq")).toBe(2);
    expect(service.kReadWith(answer as never, "front-desk")).toBeUndefined();
    expect(service.kReadWith(null, "faq")).toBeUndefined();
  });
});

describe("attach and detach", () => {
  it("attach replaces the base's entry, keeps the others, guarded like any settings write", async () => {
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, team: tuningRow("", 3, { bases: [{ base: "faq", k: 2 }, { base: "front-desk", k: 8 }] }) });
    const sent = answer("put", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("mem_ana", 1, {}) });
    const { ctx } = testContext();
    const done = await service.attachBase(ctx, service.AttachBaseInput.parse({ base: "front-desk", k: 4, mode: "tool", minScore: 0.5 }));
    expect((sent[0]!.body as { config: { bases: unknown } }).config.bases).toEqual([{ base: "faq", k: 2 }, { base: "front-desk", k: 4, mode: "tool", min_score: 0.5 }]);
    expect(done).toEqual({ agent: "front-desk", base: "front-desk", corner: "your corner", version: 1 });
  });

  it("detach of a base the corner does not read is a failed check, and nothing is written", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await expect(service.detachBase(ctx, service.DetachBaseInput.parse({ base: "faq" }))).rejects.toThrow(new PinecallError(service.NOT_ATTACHED("front-desk", "faq")));
  });

  it("detach keeps an empty list, so the corner does not fall back to the team's", async () => {
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, team: tuningRow("", 3, { bases: [{ base: "faq" }] }) });
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await service.detachBase(ctx, service.DetachBaseInput.parse({ base: "faq" }));
    expect((sent[0]!.body as { config: { bases: unknown } }).config.bases).toEqual([]);
  });

  it("refuses a mode no turn reads with", () => {
    expect(() => service.AttachBaseInput.parse({ base: "faq", mode: "always" })).toThrow();
    expect(UsageError).toBeDefined();
  });
});
