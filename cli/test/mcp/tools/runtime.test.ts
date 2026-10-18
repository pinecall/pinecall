/** The `runtime` tool with nothing started: what `status` says before and after `pinecall-runtime setup` signed this machine in, and the line `up` runs. */

import { describe, expect, it } from "vitest";

import { LOCAL_GATEWAY, SESSION_FILE } from "../../../src/project/session.js";
import { flagsOf, runtime } from "../../../src/mcp/tools/runtime.js";
import type { ToolContext } from "../../../src/mcp/tool.js";
import { folder, write } from "../../support/project.js";

function contextAt(home: string): ToolContext {
  return { processEnv: { PINECALL_HOME: home }, session: { runtime: undefined } } as unknown as ToolContext;
}

describe("the runtime tool", () => {
  it("status says there is no runtime on this machine until setup signed it in", async () => {
    const home = folder();
    expect(await runtime.call({ action: "status" }, contextAt(home))).toEqual({
      running: false,
      handed: false,
      says: "no runtime on this machine yet: call runtime with action recommend, then up",
    });
    write(home, SESSION_FILE, JSON.stringify({ gateways: { [LOCAL_GATEWAY]: { key: "pc_live_local", org: "default" } }, last: LOCAL_GATEWAY }));
    expect(await runtime.call({ action: "status" }, contextAt(home))).toEqual({ running: false, handed: true, gateway: "http://127.0.0.1:8080" });
  });

  it("recommend and up name the install line when pinecall-runtime is not on this machine", async () => {
    const context = contextAt(folder());
    context.processEnv.PATH = folder();
    await expect(runtime.call({ action: "recommend" }, context)).rejects.toThrow("pinecall-runtime is not installed on this machine");
    await expect(runtime.call({ action: "up" }, context)).rejects.toThrow("pinecall-runtime is not installed on this machine");
  });

  it("up runs setup --yes with a flag per stage given, and nothing else", () => {
    expect(flagsOf({})).toEqual(["setup", "--yes"]);
    expect(flagsOf({ llm: "local/gemma4:12b", judge: "anthropic", chat_only: true, email: "ana@example.com" })).toEqual([
      "setup",
      "--yes",
      "--llm",
      "local/gemma4:12b",
      "--judge",
      "anthropic",
      "--chat-only",
      "--email",
      "ana@example.com",
    ]);
    expect(flagsOf({ stt: "deepgram", turn: "stt", tts: "cartesia", caller: "local", models: "keys" })).toEqual(["setup", "--yes", "--stt", "deepgram", "--turn", "stt", "--tts", "cartesia", "--caller", "local", "--models", "keys"]);
  });
});
