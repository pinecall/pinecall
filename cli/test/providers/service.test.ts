/** The vendor catalog, the org's own keys (sent once, never read back), and how a model is named. */

import { describe, expect, it } from "vitest";

import { UsageError } from "../../src/errors.js";
import * as service from "../../src/providers/service.js";
import { answer } from "../support/gateway.js";
import { testContext } from "../support/context.js";
import { CATALOG } from "../support/fixtures.js";

describe("the catalog", () => {
  it("keeps every vendor when no job is named", async () => {
    answer("get", "/v1/providers", CATALOG);
    const { ctx } = testContext();
    expect(await service.listProviders(ctx)).toEqual(CATALOG);
  });

  it("keeps the vendors that do the job asked, and the defaults whole", async () => {
    answer("get", "/v1/providers", CATALOG);
    const { ctx } = testContext();
    const found = await service.listProviders(ctx, { does: "stt" });
    expect(found.providers.map((one) => one.name)).toEqual(["cartesia", "deepgram"]);
    expect(found.defaults).toEqual(CATALOG.defaults);
  });
});

describe("the org's keys", () => {
  it("sends the key trimmed and answers the vendor alone", async () => {
    const sent = answer("put", "/v1/provider-keys/:vendor");
    const { ctx } = testContext();
    expect(await service.addProviderKey(ctx, { vendor: "openai", key: "  sk-proj-123\n" })).toEqual({ vendor: "openai" });
    expect(sent[0]!.path).toBe("/v1/provider-keys/openai");
    expect(sent[0]!.body).toEqual({ key: "sk-proj-123" });
  });

  it("refuses a blank key without sending it", async () => {
    const { ctx } = testContext();
    await expect(service.addProviderKey(ctx, { vendor: "openai", key: "   " })).rejects.toThrow(new UsageError(service.NO_KEY_GIVEN));
  });

  it("escapes a vendor's name in the path", async () => {
    const sent = answer("delete", "/v1/provider-keys/:vendor");
    const { ctx } = testContext();
    await service.removeProviderKey(ctx, "a/b");
    expect(sent[0]!.path).toBe("/v1/provider-keys/a%2Fb");
  });
});

describe("naming a model", () => {
  it("reads vendor/model, a short name as Anthropic's, a bare model as Anthropic's", () => {
    expect(service.parseModel("openai/gpt-5.4-mini")).toEqual({ provider: "openai", model: "gpt-5.4-mini" });
    expect(service.parseModel("haiku")).toEqual({ provider: "anthropic", model: "claude-haiku-5-5" });
    expect(service.parseModel("claude-opus-5")).toEqual({ provider: "anthropic", model: "claude-opus-5" });
  });

  it("names nothing for an empty side", () => {
    expect(service.parseModel("")).toBeUndefined();
    expect(service.parseModel("openai/")).toBeUndefined();
    expect(service.parseModel("/gpt")).toBeUndefined();
  });

  it("keeps every slash after the vendor's in a path", () => {
    expect(service.parseModelPath("livekit/openai/gpt-5-mini")).toEqual({ provider: "livekit", model: "openai/gpt-5-mini" });
    expect(service.parseModelPath("sonnet")).toEqual({ provider: "anthropic", model: "claude-sonnet-5" });
    expect(service.parseModelPath("openai")).toBeUndefined();
  });

  it("stores a short name expanded and anything else as typed", () => {
    expect(service.modelFieldOf("opus")).toBe("anthropic/claude-opus-5");
    expect(service.modelFieldOf("openai")).toBe("openai");
    expect(service.modelFieldOf("openai/gpt-5.4")).toBe("openai/gpt-5.4");
    expect(service.modelFieldOf("hf/Qwen/Qwen2.5-3B-Instruct")).toBe("hf/Qwen/Qwen2.5-3B-Instruct");
    expect(service.modelFieldOf("")).toBeUndefined();
  });
});
