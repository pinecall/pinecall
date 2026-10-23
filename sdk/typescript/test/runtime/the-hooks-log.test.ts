// A line a hook logs lands on the call's log: onCall's before the first prompt, onEnd's after the call ended.

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import { Agent, mount } from "../../src/index.js";

const KEY = "pk_test";
const SLUG = "talker";
const CALL = "CA_1";

class Talker extends Agent {
  override onCall(): void {
    this.log("onCall.saw", { medium: this.call.medium });
  }

  override onEnd(): void {
    this.log("outcome", { ended: true });
  }
}

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mount(Talker, { pc, slug: SLUG });
  await pc.connect();
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function logged(): { name: unknown; data: unknown }[] {
  return gateway.commandsOf("call.log").map((command) => ({ name: command.data["name"], data: command.data["data"] }));
}

it("lands a line onCall logged, though the hook runs before anything is followed", async () => {
  gateway.emit(SLUG, CALL, "call.started", { channel: "web", direction: "inbound", from: "v", to: SLUG, caller: null, started_at: Date.now() / 1000 });
  await settled();

  expect(logged()).toEqual([{ name: "onCall.saw", data: { medium: "voice" } }]);
});

it("lands a line onEnd logged, though the call's listeners are gone by then", async () => {
  gateway.emit(SLUG, CALL, "call.started", { channel: "web", direction: "inbound", from: "v", to: SLUG, caller: null, started_at: Date.now() / 1000 });
  await settled();
  gateway.emit(SLUG, CALL, "call.ended", { reason: "caller_hung_up", ended_by: "caller", ended_at: Date.now() / 1000, duration_s: 3 });
  await settled();

  expect(logged().map((line) => line.name)).toEqual(["onCall.saw", "outcome"]);
});

// The gateway seals a call on the app's word that its end hook ran, and a line logged after the seal is
// refused: the SDK says it will (at registration), and says it after the last line the hook logged.
it("says call.done after the lines onEnd logged, and registered saying it would", async () => {
  gateway.emit(SLUG, CALL, "call.started", { channel: "web", direction: "inbound", from: "v", to: SLUG, caller: null, started_at: Date.now() / 1000 });
  await settled();
  gateway.emit(SLUG, CALL, "call.ended", { reason: "caller_hung_up", ended_by: "caller", ended_at: Date.now() / 1000, duration_s: 3 });
  await settled();

  expect(gateway.commandsOf("agent.register")[0]?.data["says_done"]).toBe(true);
  const after = gateway.received.filter((command) => command.type === "call.log" || command.type === "call.done");
  expect(after.map((command) => command.type === "call.log" ? command.data["name"] : command.type)).toEqual(["onCall.saw", "outcome", "call.done"]);
  expect(gateway.commandsOf("call.done")[0]?.call).toBe(CALL);
});
