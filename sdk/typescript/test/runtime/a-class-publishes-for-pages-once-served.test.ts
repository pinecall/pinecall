// A class's `onServe` runs once its agent is registered: it records lines in the agent's voice and publishes a document through the gateway, and what it says reaches its person.

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { Agent, type Serve } from "../../src/index.js";
import { mount } from "../../src/runtime/connect.js";

const KEY = "pc_test_publishing";
const RECORDED = {
  lines: [{ id: "9f2c", text: "Hi there.", url: "https://gw/v1/lines/9f2c.mp3", duration_ms: 900, voice: "acme", timed: true, words: [{ text: "Hi", start_ms: 0, end_ms: 300 }, { text: "there.", start_ms: 300, end_ms: 800 }] }],
};

/** Greets the pages that show it. */
class Greeter extends Agent {
  static override async onServe(serve: Serve): Promise<void> {
    const [line] = await serve.record(["Hi there."]);
    await serve.publish("greeting", { audio: line?.url ?? null, first: line?.words[0]?.startMs ?? null });
    serve.say(`greeting recorded · ${line?.durationMs ?? 0} ms`);
  }
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

it("records and publishes once the agent is registered, with the key, and tells its person", async () => {
  const asked: { method: string; url: string; body: unknown; key: string | null }[] = [];
  const realFetch = globalThis.fetch;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (!url.includes("/lines") && !url.includes("/public/")) return realFetch(input, init);
    const headers = new Headers(init?.headers);
    asked.push({ method: init?.method ?? "GET", url, body: JSON.parse(String(init?.body)), key: headers.get("authorization") });
    return new Response(url.includes("/lines") ? JSON.stringify(RECORDED) : "{}", { status: 200 });
  });
  const said: string[] = [];
  mount(Greeter, { pc, slug: "greeter", report: (line) => said.push(line) });
  await pc.connect();

  await vi.waitFor(() => expect(said).toEqual(["greeting recorded · 900 ms"]));
  expect(asked).toEqual([
    { method: "POST", url: expect.stringMatching(/\/v1\/agents\/greeter\/lines$/), body: { texts: ["Hi there."] }, key: `Bearer ${KEY}` },
    { method: "PUT", url: expect.stringMatching(/\/v1\/agents\/greeter\/public\/greeting$/), body: { audio: "https://gw/v1/lines/9f2c.mp3", first: 0 }, key: `Bearer ${KEY}` },
  ]);
});

it("does nothing for a class that publishes nothing", async () => {
  const fetching = vi.spyOn(globalThis, "fetch");
  /** Publishes nothing. */
  class Quiet extends Agent {}
  mount(Quiet, { pc, slug: "quiet" });
  await pc.connect();
  await new Promise((resolve) => setTimeout(resolve, 20));

  expect(fetching.mock.calls.filter(([input]) => String(input).includes("/v1/agents/"))).toEqual([]);
});
