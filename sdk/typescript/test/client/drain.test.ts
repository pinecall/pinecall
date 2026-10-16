// Draining: running tools finish and no socket is redialled.

import { afterEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway, type FakeGatewayOptions } from "../../src/client/testing/index.js";

const KEY = "pk_test";
const SLUG = "clinica-norte";

let gateway: FakeGateway | null = null;
let pc: Pinecall | null = null;

afterEach(async () => {
  pc?.close();
  pc = null;
  await gateway?.close();
  gateway = null;
});

async function holding(
  run: () => Promise<unknown> = async () => "10:00",
  options: FakeGatewayOptions = {},
): Promise<{ gateway: FakeGateway; pc: Pinecall }> {
  gateway = await FakeGateway.start({ apiKey: KEY, ...options });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY, backoff: { firstMs: 5, capMs: 5 } });
  pc.onErrors(() => {});
  const tool = { name: "freeSlots", description: "Free slots.", parameters: { type: "object" }, run };
  pc.agent(SLUG, { tools: [tool] });
  await pc.connect();
  return { gateway, pc };
}

const later = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

it("sends agent.drain for every agent and settles once the gateway answers", async () => {
  const { gateway, pc } = await holding();
  const done = await pc.drain();
  expect(gateway.commandsOf("agent.drain").map((command) => command.agent)).toEqual([SLUG]);
  expect(done).toEqual({ handed: 0, parked: 0, tools: 0, finished: 0 });
});

it("lets a tool running when the drain began finish and answer before it settles", async () => {
  const { gateway, pc } = await holding(async () => {
    await later(30);
    return "10:00";
  });
  gateway.emit(SLUG, "CA_1", "tool.call", { call_id: "t1", name: "freeSlots", arguments: {} });
  await later(5);
  const done = await pc.drain();
  expect(done).toMatchObject({ tools: 1, finished: 1 });
  for (let turn = 0; turn < 50 && gateway.commandsOf("tool.result").length === 0; turn++) await later(2);
  expect(gateway.commandsOf("tool.result").map((command) => command.data["output"])).toEqual(["10:00"]);
});

it("cuts a tool that outlasts the drain, and counts it", async () => {
  const { gateway, pc } = await holding(() => new Promise(() => {}));
  gateway.emit(SLUG, "CA_1", "tool.call", { call_id: "t1", name: "freeSlots", arguments: {} });
  await later(5);
  expect(await pc.drain({ toolsMs: 20 })).toMatchObject({ tools: 1, finished: 0 });
});

it("gives up on a gateway that never answers the drain, and still settles", async () => {
  const { pc } = await holding(undefined, { holdsDrain: true });
  expect(await pc.drain({ answerMs: 30 })).toEqual({ handed: 0, parked: 0, tools: 0, finished: 0 });
});

it("dials no new socket once a drain has begun", async () => {
  const { gateway, pc } = await holding(undefined, { holdsDrain: true });
  const draining = pc.drain({ answerMs: 30 });
  gateway.cut();
  await draining;
  await later(40);
  expect(gateway.commandsOf("agent.register")).toHaveLength(1);
});
