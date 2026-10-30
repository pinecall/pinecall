// A class that declares `docs` pushes the folder beside it once its agent is registered: every Markdown file, by path, the base's other files kept.

import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { Agent } from "../../src/index.js";
import { mount } from "../../src/runtime/connect.js";
import { markdownUnder } from "../../src/runtime/declared-docs.js";

const KEY = "pc_test_docs";
const PUSHED = { base: "front-desk", chunks: 7, language: "es", took_ms: 12.5, kept: 2 };

/** Reads its base per turn, and owns the folder beside it. */
class Reads extends Agent {
  static override docs = { base: "front-desk", k: 4 };
}

/** Declares no base: nothing beside it is pushed. */
class Silent extends Agent {}

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

function folder(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "declared-docs-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(join(dir, path, ".."), { recursive: true });
    writeFileSync(join(dir, path), text);
  }
  return dir;
}

function pushes(): { url: string; body: unknown; key: string | null }[] {
  const asked: { url: string; body: unknown; key: string | null }[] = [];
  const realFetch = globalThis.fetch;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (!url.includes("/v1/knowledge/")) return realFetch(input, init);
    const headers = new Headers(init?.headers);
    asked.push({ url, body: JSON.parse(String(init?.body)), key: headers.get("authorization") });
    return new Response(JSON.stringify(PUSHED), { status: 200 });
  });
  return asked;
}

it("reads every Markdown file under the folder by its path, and nothing for no folder", () => {
  const dir = folder({ "docs/hours.md": "# Hours", "docs/policies/insurance.md": "# Insurance", "docs/notes.txt": "no" });
  expect(markdownUnder(join(dir, "docs"))).toEqual([
    { path: "hours.md", text: "# Hours" },
    { path: "policies/insurance.md", text: "# Insurance" },
  ]);
  expect(markdownUnder(join(dir, "nowhere"))).toEqual([]);
});

it("pushes the folder beside the class once the agent is registered, once per process, and says what landed", async () => {
  const asked = pushes();
  const dir = folder({ "docs/hours.md": "# Hours" });
  const said: string[] = [];
  mount(Reads, { pc, slug: "front-desk", file: join(dir, "agent.tsx"), report: (line) => said.push(line) });
  await pc.connect();
  await vi.waitFor(() => expect(said).toEqual(["front-desk  1 file(s) pushed · 7 chunk(s) · 2 kept"]));
  expect(asked).toEqual([{ url: expect.stringMatching(/\/v1\/knowledge\/front-desk$/), body: { files: [{ path: "hours.md", text: "# Hours" }] }, key: `Bearer ${KEY}` }]);
});

it("pushes nothing for a class that declares no base, or a folder that is not there", async () => {
  const asked = pushes();
  const dir = folder({ "docs/hours.md": "# Hours" });
  mount(Silent, { pc, slug: "silent", file: join(dir, "agent.tsx") });
  mount(Reads, { pc, slug: "front-desk", file: join(folder({}), "agent.tsx") });
  await pc.connect();
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
  expect(asked).toEqual([]);
});
