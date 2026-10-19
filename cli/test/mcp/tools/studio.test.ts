/** The `studio` tool: an agent made, saved whole over the release read, a tool tried, deployed; what an action needs, refused by name before anything is sent. */

import { describe, expect, it } from "vitest";

import { studio } from "../../../src/mcp/tools/studio.js";
import type { ToolContext } from "../../../src/mcp/tool.js";
import { testContext } from "../../support/context.js";
import { answer } from "../../support/gateway.js";

const DEFINITION = {
  instructions: "You answer the phone for Clínica Norte.",
  tools: [{ name: "find_slot", description: "free slots on a day", url: "https://api.clinica.test/slots", params: [{ name: "day" }] }],
  collect: { fields: [{ name: "full_name", description: "the caller's name" }], send_to: "https://api.clinica.test/leads" },
};
const AN_AGENT = { name: "front-desk", env: "sandbox", release: 3, definition: { ...DEFINITION, greeting: null }, author: "ana@clinica.test", note: "", saved_at: 1_792_150_000, stopped: false };

function context(): ToolContext {
  return Object.assign(testContext().ctx, { session: {} as ToolContext["session"] });
}

describe("the studio tool", () => {
  it("list answers the org's Studio agents", async () => {
    answer("get", "/v1/studio/agents", { agents: [AN_AGENT] });
    expect(await studio.call({ action: "list" }, context())).toEqual({ agents: [AN_AGENT] });
  });

  it("new makes one, from the definition given", async () => {
    const sent = answer("post", "/v1/studio/agents", { ...AN_AGENT, release: 1 });
    expect(await studio.call({ action: "new", name: "front-desk", definition: DEFINITION }, context())).toMatchObject({ release: 1 });
    expect(sent[0]!.body).toEqual({ name: "front-desk", note: "", definition: DEFINITION });
  });

  it("save sends the whole definition based on the release read", async () => {
    const sent = answer("put", "/v1/studio/agents/:name", { ...AN_AGENT, release: 4 });
    expect(await studio.call({ action: "save", name: "front-desk", definition: DEFINITION, based_on: 3, note: "collects the name" }, context())).toMatchObject({ release: 4 });
    expect(sent[0]!.body).toEqual({ definition: DEFINITION, based_on: 3, note: "collects the name" });
  });

  it("save refuses without the definition or the release it was read at", async () => {
    await expect(studio.call({ action: "save", name: "front-desk", based_on: 3 }, context())).rejects.toThrow("save takes the whole `definition`");
    await expect(studio.call({ action: "save", name: "front-desk", definition: DEFINITION }, context())).rejects.toThrow("save takes `based_on`");
  });

  it("a definition with a field the gateway has no name for is refused by its schema", () => {
    expect(() => studio.call({ action: "save", name: "front-desk", based_on: 3, definition: { ...DEFINITION, instruction: "typo" } }, context())).toThrow();
  });

  it("try sends the tool and its arguments, and an unsaved definition when given", async () => {
    const sent = answer("post", "/v1/studio/agents/:name/try", { status: 200, body: { free: 2 }, error: null, duration_ms: 184 });
    expect(await studio.call({ action: "try", name: "front-desk", tool: "find_slot", arguments: { day: "2026-10-21" }, definition: DEFINITION }, context())).toEqual({ status: 200, body: { free: 2 }, error: null, duration_ms: 184 });
    expect(sent[0]!.body).toEqual({ tool: "find_slot", arguments: { day: "2026-10-21" }, definition: DEFINITION });
    await expect(studio.call({ action: "try", name: "front-desk" }, context())).rejects.toThrow("tool is needed");
  });

  it("deploy is asked in the sandbox and answers production's release", async () => {
    const sent = answer("post", "/v1/studio/agents/:name/deploy", { ...AN_AGENT, env: "production", release: 1 });
    expect(await studio.call({ action: "deploy", name: "front-desk" }, context())).toMatchObject({ env: "production", release: 1 });
    expect(sent[0]!.env).toBe("sandbox");
    expect(sent[0]!.body).toEqual({ note: "" });
  });

  it("every action but list takes the name", async () => {
    await expect(studio.call({ action: "show" }, context())).rejects.toThrow("name is needed");
  });
});
