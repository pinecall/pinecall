// A view that cannot be rendered fails its call, not the process: the log says why and the call goes on.

import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import { Agent, mount, type Mounted } from "../../src/index.js";

const KEY = "pk_test";
const SLUG = "greedy";

/** Its view writes state, which only a tool or a hook may. */
class Greedy extends Agent {
  released = "";

  override render(): null {
    this.released = "10:15";
    return null;
  }
}

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;

beforeEach(async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mounted = mount(Greedy, { pc, slug: SLUG });
  await pc.connect();
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
  vi.restoreAllMocks();
});

async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function started(call: string): void {
  gateway.emit(SLUG, call, "call.started", { channel: "web", direction: "inbound", from: "v", to: SLUG, caller: null, started_at: Date.now() / 1000 });
}

function failures(): string[] {
  return gateway
    .commandsOf("call.log")
    .filter((command) => command.data["name"] === "render.failed")
    .map((command) => String((command.data["data"] as { message: string }).message));
}

it("logs the sentence on the call and keeps serving it, instead of ending the process", async () => {
  started("CA_1");
  await settled();

  expect(failures()).toEqual([expect.stringMatching(/state field released was assigned outside a tool/)]);
  expect(mounted.instanceOf("CA_1")).toBeDefined();
});

it("fails each turn its view cannot be rendered for, and the other calls are not touched", async () => {
  started("CA_1");
  started("CA_2");
  await settled();
  gateway.emit(SLUG, "CA_1", "turn.user", { speech_id: "s1", text: "hola", metrics: {} });
  await settled();

  expect(failures()).toHaveLength(3);
  expect(mounted.instanceOf("CA_2")).toBeDefined();
});
