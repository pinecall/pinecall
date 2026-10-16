/** Judging against the gateway: whose list, a judge written whole from its flags, a try, and the org's judging with whose key it runs on. */

import { describe, expect, it } from "vitest";

import { UsageError } from "../../src/errors.js";
import * as service from "../../src/judging/service.js";
import { answer } from "../support/gateway.js";
import { testContext } from "../support/context.js";
import { A_JUDGE, JUDGING } from "../support/fixtures.js";
import { folder } from "../support/project.js";

describe("whose list", () => {
  it("is the org's with --org, the project's one agent without", () => {
    const { ctx } = testContext();
    expect(service.ownerOf(ctx, { org: true })).toBeNull();
    expect(service.ownerOf(ctx, { org: false })).toBe("front-desk");
  });

  it("is the slug named, from any folder", () => {
    const { ctx } = testContext({ cwd: folder() });
    expect(service.ownerOf(ctx, { org: false, agent: "sales" })).toBe("sales");
  });

  it("refuses both at once", () => {
    const { ctx } = testContext();
    expect(() => service.ownerOf(ctx, { org: true, agent: "sales" })).toThrow(service.ONE_OR_THE_OTHER);
  });
});

describe("a judge of one's own", () => {
  it("is written whole: the question, a choice of two at least, a trigger, what it reads", () => {
    expect(service.judgeRequestOf({ asks: " Did it book? ", answer: "choice:booked, moved ,cancelled", when: "trigger: the caller asked for a slot", reads: "prompt,facts" })).toEqual({
      question: "Did it book?",
      answer: "choice",
      choices: ["booked", "moved", "cancelled"],
      when: "trigger",
      trigger: "the caller asked for a slot",
      reads: ["prompt", "facts"],
    });
  });

  it("defaults to a verdict asked of every call", () => {
    expect(service.judgeRequestOf({ asks: "Q" })).toEqual({ question: "Q", answer: "verdict", when: "always" });
  });

  it("refuses what it cannot answer, run on, or read", () => {
    expect(() => service.judgeRequestOf({})).toThrow(service.NO_QUESTION);
    expect(() => service.judgeRequestOf({ asks: "Q", answer: "choice:only-one" })).toThrow(/--answer choice:only-one/);
    expect(() => service.judgeRequestOf({ asks: "Q", when: "trigger:" })).toThrow(/--when trigger:/);
    expect(() => service.judgeRequestOf({ asks: "Q", reads: "prompt,transcript" })).toThrow(/--reads transcript/);
  });

  it("is put under the agent's list, and the list after is answered with what was done", async () => {
    const sent = answer("put", "/v1/agents/:slug/judges/:name", { judges: [A_JUDGE] });
    const { ctx } = testContext();
    const changed = await service.addJudge(ctx, "front-desk", "offers-next-slot", { asks: A_JUDGE.question });
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/judges/offers-next-slot");
    expect(changed).toEqual({ done: "offers-next-slot written", judges: [A_JUDGE] });
  });

  it("refuses a name the gateway would, before asking it", async () => {
    const { ctx } = testContext();
    await expect(service.addJudge(ctx, null, "Offers Next", { asks: "Q" })).rejects.toThrow(service.NAME_SHAPE("Offers Next"));
  });

  it("one of Pinecall's is switched under the org's list with `on` alone", async () => {
    const sent = answer("put", "/v1/org/judges/:name", { judges: [] });
    const { ctx } = testContext();
    await service.switchJudge(ctx, null, "consent", true);
    expect(sent[0]!.body).toEqual({ on: true });
  });
});

describe("a try", () => {
  it("asks the last calls, or the ones named, never both", async () => {
    const { ctx } = testContext();
    await expect(service.tryJudge(ctx, { name: "offers-next-slot" })).rejects.toThrow(service.WHICH_CALLS);
    await expect(service.tryJudge(ctx, { name: "offers-next-slot", last: 3, calls: ["a"] })).rejects.toThrow(service.WHICH_CALLS);
    await expect(service.tryJudge(ctx, { name: "offers-next-slot", last: 51 })).rejects.toThrow("--last 51 is not 1 to 50 calls");
  });

  it("sends a saved judge by name, and an unsaved one whole", async () => {
    const sent = answer("post", "/v1/agents/:slug/judges/try", { rows: [], evals: 0, cost_usd: 0 });
    const { ctx } = testContext();
    await service.tryJudge(ctx, { name: "offers-next-slot", last: 3 });
    await service.tryJudge(ctx, { name: "draft", calls: ["call_1"], asks: "Did it greet?" });
    expect(sent.map((one) => one.body)).toEqual([
      { name: "offers-next-slot", last: 3 },
      { name: "draft", question: "Did it greet?", answer: "verdict", when: "always", calls: ["call_1"] },
    ]);
  });
});

describe("the org's judging", () => {
  it("on Pinecall's model asks for no keys", async () => {
    answer("get", "/v1/org/judging", JUDGING);
    const { ctx } = testContext();
    expect(await service.getJudging(ctx)).toEqual({ ...JUDGING, own_key: false });
  });

  it("on a model of the org's says whether the org brought that vendor's key", async () => {
    answer("get", "/v1/org/judging", { ...JUDGING, model: { provider: "openai", model: "gpt-5.4-mini" } });
    answer("get", "/v1/provider-keys", { vendors: ["openai"] });
    const { ctx } = testContext();
    expect((await service.getJudging(ctx)).own_key).toBe(true);
  });

  it("off keeps the model that stands, since the endpoint takes the whole", async () => {
    const model = { provider: "openai", model: "qwen3-32b", options: { base_url: "http://gpu:8000/v1" } };
    answer("get", "/v1/org/judging", { ...JUDGING, model });
    const sent = answer("put", "/v1/org/judging", { ...JUDGING, on: false, model });
    answer("get", "/v1/provider-keys", { vendors: [] });
    const { ctx } = testContext();
    await service.setJudging(ctx, service.SetJudgingInput.parse({ on: false }));
    expect(sent[0]!.body).toEqual({ on: false, model });
  });

  it("--model keeps on or off as it stands, with the plugin's options", async () => {
    answer("get", "/v1/org/judging", { ...JUDGING, on: false });
    const sent = answer("put", "/v1/org/judging", JUDGING);
    const { ctx } = testContext();
    await service.setJudging(ctx, service.SetJudgingInput.parse({ model: "livekit/openai/gpt-5-mini", options: { base_url: "http://gpu:8000/v1" } }));
    expect(sent[0]!.body).toEqual({ on: false, model: { provider: "livekit", model: "openai/gpt-5-mini", options: { base_url: "http://gpu:8000/v1" } } });
  });

  it("--platform goes back to Pinecall's model", async () => {
    answer("get", "/v1/org/judging", { ...JUDGING, model: { provider: "openai", model: "x" } });
    const sent = answer("put", "/v1/org/judging", JUDGING);
    const { ctx } = testContext();
    await service.setJudging(ctx, service.SetJudgingInput.parse({ platform: true }));
    expect(sent[0]!.body).toEqual({ on: true });
  });

  it("refuses a model and the platform's at once, or options without a model, before asking", async () => {
    const { ctx } = testContext();
    await expect(service.setJudging(ctx, service.SetJudgingInput.parse({ platform: true, model: "haiku" }))).rejects.toBeInstanceOf(UsageError);
    await expect(service.setJudging(ctx, service.SetJudgingInput.parse({ options: { a: 1 } }))).rejects.toBeInstanceOf(UsageError);
  });
});
