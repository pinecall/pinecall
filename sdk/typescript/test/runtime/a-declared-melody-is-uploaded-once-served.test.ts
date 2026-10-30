// A class that declares its hold melody names the file by its hash and uploads it once the agent registers, unless the gateway holds it already.

import { createHash } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { Agent } from "../../src/index.js";
import { mount, optionsFor } from "../../src/runtime/connect.js";
import { holdConfigOf } from "../../src/runtime/declared-hold.js";

const KEY = "pc_test_hold";
const MELODY = new Uint8Array([0x52, 0x49, 0x46, 0x46, 1, 2, 3, 4]);
const SHA = createHash("sha256").update(MELODY).digest("hex");

/** Plays its own file after a second and a half. */
class Plays extends Agent {
  static override hold = { file: "hold.mp3", afterS: 1.5 };
}

/** Plays nothing. */
class Quiet extends Agent {
  static override hold = "off" as const;
}

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
});

afterEach(async () => {
  vi.restoreAllMocks();
  pc.close();
  await gateway.close();
});

function beside(): string {
  const dir = mkdtempSync(join(tmpdir(), "declared-hold-"));
  writeFileSync(join(dir, "hold.mp3"), MELODY);
  return join(dir, "agent.tsx");
}

function doors(held: Record<string, unknown>): { method: string; url: string; body: Uint8Array | null }[] {
  const asked: { method: string; url: string; body: Uint8Array | null }[] = [];
  const realFetch = globalThis.fetch;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (!url.includes("/hold-audio")) return realFetch(input, init);
    const body = init?.body instanceof Uint8Array ? init.body : null;
    asked.push({ method: init?.method ?? "GET", url, body });
    const answer = init?.method === "PUT" ? { ...held, played: "custom", source_sha256: SHA, seconds: 41.2, name: "hold.mp3" } : held;
    return new Response(JSON.stringify(answer), { status: 200 });
  });
  return asked;
}

it("declares the file by its hash and the wait, and silence as off", () => {
  expect(holdConfigOf(Plays, beside())).toEqual({ clip: SHA, name: "hold.mp3", afterS: 1.5 });
  expect(holdConfigOf(Quiet, undefined)).toEqual({ off: true });
  expect(holdConfigOf(Agent, undefined)).toBeUndefined();
  expect(() => optionsFor(Plays, [], undefined, join(tmpdir(), "nowhere", "agent.tsx"))).toThrow("there is no such file beside the class");
});

it("uploads the file once the agent is registered, and not again when the gateway holds it", async () => {
  const file = beside();
  const said: string[] = [];
  const asked = doors({ played: "default", after_s: 2.5, fixed: true });
  mount(Plays, { pc, slug: "plays", file, report: (line) => said.push(line) });
  await pc.connect();
  await vi.waitFor(() => expect(said).toEqual(["plays  hold.mp3 uploaded as the hold melody · 41.2 s"]));
  expect(asked.map((one) => one.method)).toEqual(["GET", "PUT"]);
  expect(asked[1]?.url).toMatch(/\/v1\/agents\/plays\/hold-audio\?name=hold\.mp3$/);
  expect([...(asked[1]?.body ?? [])]).toEqual([...MELODY]);
  pc.close();

  const again = new Pinecall({ url: gateway.url, apiKey: KEY });
  again.onErrors(() => {});
  const held = doors({ played: "custom", after_s: 1.5, source_sha256: SHA, fixed: true });
  mount(Plays, { pc: again, slug: "plays", file });
  await again.connect();
  for (let turn = 0; turn < 30; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
  expect(held.map((one) => one.method)).toEqual(["GET"]);
  again.close();
});
