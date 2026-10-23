// A hook that throws fails its call, not the process: the log names the hook and the error, and the call goes on.

import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import { Agent, mount, type EventDeclarations, type Mounted } from "../../src/index.js";

const KEY = "pk_test";
const SLUG = "fragile";

/** Every hook throws, after writing what it had. */
class Fragile extends Agent {
  static override events: EventDeclarations = { "slot.released": { from: ["app"] } };

  opened = "";
  slot = "";

  override onCall(): void {
    this.opened = "partly";
    throw new Error("the agenda is down");
  }

  override onEvent(_name: string, data: Record<string, unknown>): void {
    this.slot = String(data["when"]);
    throw new Error("no such slot");
  }

  override onMemory(): void {
    throw new Error("memory is down");
  }

  override onEnd(): void {
    this.log("outcome", { ended: true });
    throw new Error("could not close");
  }
}

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;
let warned: ReturnType<typeof vi.spyOn>;

beforeEach(async () => {
  warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mounted = mount(Fragile, { pc, slug: SLUG });
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

function failures(): Record<string, unknown>[] {
  return gateway
    .commandsOf("call.log")
    .filter((command) => command.data["name"] === "hook.failed")
    .map((command) => command.data["data"] as Record<string, unknown>);
}

it("names onCall and its error, and opens the call anyway with what the hook had written", async () => {
  started("CA_1");
  await settled();

  expect(failures()).toEqual([{ hook: "onCall", error: "Error", message: "the agenda is down" }]);
  expect(mounted.instanceOf("CA_1")).toBeDefined();
  const [opening] = gateway.commandsOf("state.set");
  expect(opening?.data["state"]).toMatchObject({ opened: "partly" });
  expect(gateway.commandsOf("prompt.set").length).toBeGreaterThan(0);
  expect(warned).toHaveBeenCalledWith(expect.stringContaining("onCall threw and the call goes on: the agenda is down"));
});

it("names onEvent with the event it was handling, and the next event still reaches it", async () => {
  started("CA_1");
  await settled();
  gateway.emit(SLUG, "CA_1", "event.received", { name: "slot.released", data: { when: "10:15" }, source: "app" });
  gateway.emit(SLUG, "CA_1", "event.received", { name: "slot.released", data: { when: "11:00" }, source: "app" });
  await settled();

  expect(failures().slice(1)).toEqual([
    { hook: "onEvent", event: "slot.released", error: "Error", message: "no such slot" },
    { hook: "onEvent", event: "slot.released", error: "Error", message: "no such slot" },
  ]);
  expect((mounted.instanceOf("CA_1") as Fragile).slot).toBe("11:00");
});

it("names onMemory", async () => {
  started("CA_1");
  await settled();
  gateway.emit(SLUG, "CA_1", "memory.ops", { ops: [{ op: "recall", facts: [{ text: "prefiere la mañana" }], took_ms: 3 }] });
  await settled();

  expect(failures().map((failure) => failure["hook"])).toEqual(["onCall", "onMemory"]);
});

it("names onEnd, lets its own line land, and lets the call go; another call is not touched", async () => {
  started("CA_1");
  started("CA_2");
  await settled();
  gateway.emit(SLUG, "CA_1", "call.ended", { reason: "caller_hung_up", ended_by: "caller", ended_at: Date.now() / 1000, duration_s: 3 });
  await settled();

  expect(failures().filter((failure) => failure["hook"] === "onEnd")).toEqual([{ hook: "onEnd", error: "Error", message: "could not close" }]);
  expect(gateway.commandsOf("call.log").some((command) => command.data["name"] === "outcome")).toBe(true);
  expect(mounted.instanceOf("CA_1")).toBeUndefined();
  expect(mounted.instanceOf("CA_2")).toBeDefined();
});
