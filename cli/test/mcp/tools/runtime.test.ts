/** The `runtime` tool with nothing started: what `status` says before and after `pinecall-runtime setup` signed this machine in. */

import { describe, expect, it } from "vitest";

import { LOCAL_GATEWAY, SESSION_FILE } from "../../../src/project/session.js";
import { runtime } from "../../../src/mcp/tools/runtime.js";
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
      says: "no runtime on this machine yet: call runtime with action up",
    });
    write(home, SESSION_FILE, JSON.stringify({ gateways: { [LOCAL_GATEWAY]: { key: "pc_live_local", org: "default" } }, last: LOCAL_GATEWAY }));
    expect(await runtime.call({ action: "status" }, contextAt(home))).toEqual({ running: false, handed: true, gateway: "http://127.0.0.1:8080" });
  });

  it("up names the install line when pinecall-runtime is not on this machine", async () => {
    const context = contextAt(folder());
    context.processEnv.PATH = folder();
    await expect(runtime.call({ action: "up" }, context)).rejects.toThrow("pinecall-runtime is not installed on this machine");
  });
});
