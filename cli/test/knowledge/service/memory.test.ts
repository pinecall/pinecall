/** Memory against the gateway: one contact read and forgotten, the policy written whole in a corner, the recall golden scored. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/knowledge/service/memory.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { SETTINGS } from "../../support/fixtures.js";
import { folder, project } from "../../support/project.js";

describe("a contact", () => {
  it("is read by its number, escaped, and answered with it", async () => {
    const sent = answer("get", "/v1/contacts/:contact/memory", { facts: [] });
    const { ctx } = testContext();
    expect(await service.showContact(ctx, "+34600000001")).toEqual({ contact: "+34600000001", facts: [] });
    expect(sent[0]!.path).toBe("/v1/contacts/%2B34600000001/memory");
  });

  it("is forgotten with no question asked here: the command asks", async () => {
    answer("delete", "/v1/contacts/:contact/memory", { forgotten: 4 });
    const { ctx } = testContext();
    expect(await service.forgetContact(ctx, "+34600000001")).toEqual({ forgotten: 4 });
  });
});

describe("the policy", () => {
  it("with no list typed is read, from any folder with --agent", async () => {
    const sent = answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext({ cwd: folder() });
    expect(await service.policy(ctx, service.PolicyInput.parse({ agent: "sales" }))).toEqual({ agent: "sales", answer: SETTINGS });
    expect(sent[0]!.path).toBe("/v1/agents/sales/settings");
  });

  it("with one list typed keeps the other that stands", async () => {
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    const sent = answer("put", "/v1/agents/:slug/settings", SETTINGS);
    const { ctx } = testContext();
    await service.policy(ctx, service.PolicyInput.parse({ forget: ["card numbers"] }));
    expect(sent[0]!.body).toMatchObject({ config: { memory: { remember: ["the caller's name"], forget: ["card numbers"] } }, note: "memory policy" });
  });
});

describe("the recall golden", () => {
  it("is the agent's goldens/memory.json, its questions sent whole", async () => {
    const questions = [{ holds: ["Ana is allergic to penicillin"], asks: "allergies?", expects: ["penicillin"] }];
    const root = project(["front-desk"], { "agents/front-desk/test/goldens/memory.json": JSON.stringify(questions) });
    const sent = answer("post", "/v1/contacts/memory/eval", { model: "pplx-embed-v1", questions: 1, k: 5, recall_at_k: 1, ndcg_at_10: 1, took_ms: 90, misses: [] });
    const { ctx } = testContext({ cwd: root });
    await service.evalMemory(ctx, { k: 5 });
    expect(sent[0]!.body).toEqual({ questions, k: 5 });
  });

  it("refuses a missing golden with the shape it must have", async () => {
    const { ctx } = testContext();
    await expect(service.evalMemory(ctx, {})).rejects.toThrow("{holds, asks, expects}");
  });
});
