/** The serve entry as a child: its door in its env and never its argv, registered agents read off its lines, told to leave once, killed if deaf. */

import { fileURLToPath } from "node:url";
import { PassThrough } from "node:stream";

import { describe, expect, it } from "vitest";

import { GatewayClient } from "../../src/api/client.js";
import { serveStart, spawnServing, type ServeStart } from "../../src/dev/child.js";
import { folder, project } from "../support/project.js";

const FAKE = fileURLToPath(new URL("../support/fake-serve.mjs", import.meta.url));
const REGISTERED = { type: "agent.registered", agent: "front-desk", call: null, data: { app: "app_1" } };

function fake(env: Record<string, string>): ServeStart {
  return { command: [process.execPath, FAKE], env: { PATH: process.env["PATH"], ...env } };
}

describe("the start", () => {
  it("carries the door in the environment, and the argv holds no key", () => {
    const gateway = new GatewayClient("https://gateway.test", "pc_live_secret", "production");
    const start = serveStart(gateway, "/p/agents/sales/agent.rb", "start", ["--slug", "sales"], { root: folder() }, { HOME: "/home/ana" });
    expect(start.env).toMatchObject({ PINECALL_URL: "https://gateway.test", PINECALL_KEY: "pc_live_secret", PINECALL_ENV: "production", HOME: "/home/ana" });
    expect(start.command.join(" ")).not.toContain("pc_live_secret");
  });

  it("an offline verb is given no gateway at all", () => {
    const start = serveStart(undefined, `${project()}/agents/front-desk/agent.py`, "prompt", [], { root: folder() }, { PINECALL_KEY: "kept-as-it-was" });
    expect(start.env).toEqual({ PINECALL_KEY: "kept-as-it-was" });
  });
});

describe("the child", () => {
  it("answers each agent's app once it registered, and leaves draining when asked", async () => {
    const other = new PassThrough();
    const child = spawnServing(fake({ FAKE_LINES: JSON.stringify(["compiling…", REGISTERED]) }), { other });
    expect(await child.registered("front-desk")).toBe("app_1");
    expect(child.app("front-desk")).toBe("app_1");
    expect(await child.stop()).toBe(0);
    expect(await child.stop()).toBe(0);
    expect(String(other.read())).toBe("compiling…\n");
  });

  it("a child that leaves before its agent registered is refused with its exit code", async () => {
    const child = spawnServing(fake({ FAKE_EXITS: "3" }), { other: new PassThrough() });
    await expect(child.registered("front-desk")).rejects.toThrow("the agent's process left (exit 3) before front-desk registered");
  });

  it("an agent that never registers is refused in time", async () => {
    const child = spawnServing(fake({}), { other: new PassThrough(), registersWithinMs: 50 });
    await expect(child.registered("front-desk")).rejects.toThrow("front-desk did not register within 0.05s");
    await child.stop();
  });

  it("a deaf child is killed once the grace is over", async () => {
    const child = spawnServing(fake({ FAKE_DEAF: "1", FAKE_LINES: JSON.stringify([REGISTERED]) }), { other: new PassThrough(), graceMs: 100 });
    await child.registered("front-desk");
    expect(await child.stop()).toBe(128);
  });

  it("a second signal kills what the first only asked to leave", async () => {
    const signals = new PassThrough();
    const child = spawnServing(fake({ FAKE_DEAF: "1", FAKE_LINES: JSON.stringify([REGISTERED]) }), { other: new PassThrough(), signals, graceMs: 60_000 });
    await child.registered("front-desk");
    signals.emit("SIGINT");
    signals.emit("SIGINT");
    expect(await child.exited).toBe(128);
  });

  it("a command that cannot start is the arguments' fault, named", async () => {
    const child = spawnServing({ command: ["/no/such/interpreter"], env: {} }, { other: new PassThrough() });
    await expect(child.exited).rejects.toThrow("/no/such/interpreter could not be started");
  });
});
