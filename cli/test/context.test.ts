/** What a verb runs with: the key and gateway resolved once, a server's token held to its env, an agent by folder or by slug. */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { connectionLine, createContext } from "../src/context.js";
import { UsageError } from "../src/errors.js";
import { CollectingIO } from "../src/kit/io.js";
import { GATEWAY } from "./support/gateway.js";
import { folder, project } from "./support/project.js";

function contextFor(processEnv: NodeJS.ProcessEnv, cwd = project()) {
  return createContext({ io: new CollectingIO(), processEnv: { PINECALL_HOME: folder(), ...processEnv }, cwd });
}

describe("the gateway", () => {
  it("is refused without a key, naming how to get one", () => {
    expect(() => contextFor({}, folder()).gateway()).toThrow(/signed in nowhere: `pinecall login \[url\]`/);
  });

  it("follows the env the verb is in, and a person's key opens both", () => {
    const ctx = contextFor({ PINECALL_KEY: "pc_live_person", PINECALL_URL: `${GATEWAY}/` });
    expect(ctx.gateway().env).toBe("sandbox");
    ctx.env = "production";
    expect(ctx.gateway().env).toBe("production");
    expect(ctx.gateway().url).toBe(GATEWAY);
  });

  it("a sandbox server's token is refused in production before anything is asked", () => {
    const ctx = contextFor({ PINECALL_KEY: "pc_test_server" });
    ctx.env = "production";
    expect(() => ctx.gateway()).toThrow(UsageError);
  });

  it("the connection line says where the key came from", () => {
    const root = project();
    writeFileSync(join(root, ".env"), `PINECALL_KEY=pc_live_x\nPINECALL_URL=${GATEWAY}\n`);
    expect(connectionLine(contextFor({}, root))).toBe(`gateway ${GATEWAY} · key from .env · sandbox`);
  });
});

describe("the agent", () => {
  it("of a verb that reads files is the project's folder", () => {
    const ctx = contextFor({}, project(["front-desk"]));
    expect(ctx.agent("test").name).toBe("front-desk");
    expect(() => contextFor({}, folder()).agent("test")).toThrow(/no agent here/);
    expect(() => ctx.agent("test", { agent: "sales" })).toThrow("no agent sales in this project: it has front-desk");
  });

  it("of a verb that asks the gateway alone is the slug as typed, from any folder", () => {
    expect(contextFor({}, folder()).slug("sessions", { agent: "sales" })).toBe("sales");
    expect(contextFor({}, project(["front-desk"])).slug("sessions")).toBe("front-desk");
    expect(() => contextFor({}, project(["front-desk", "sales"])).slug("sessions")).toThrow(/--agent front-desk or --agent sales/);
  });

  it("a path given to --agent points at --file", () => {
    expect(() => contextFor({}, folder()).slug("sessions", { agent: "agents/sales/agent.ts" })).toThrow("a file is --file agents/sales/agent.ts");
  });

  it("--file names the agent by its folder", () => {
    const root = project(["front-desk"]);
    expect(contextFor({}, folder()).slug("sessions", { file: join(root, "agents/front-desk/agent.ts") })).toBe("front-desk");
  });
});
