// Transfer verbs: the commands sent and the log entries they produce.

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import { Agent, mount, type Mounted } from "../../src/index.js";

const KEY = "pk_test";
const SLUG = "front-desk";
const CALL = "CA_1";
const THE_DESK = "+34910000099";

class FrontDesk extends Agent {
  web = true;
}

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mounted = mount(FrontDesk, { pc, slug: SLUG });
  await pc.connect();
  await settled();
  gateway.emit(SLUG, CALL, "call.started", {
    channel: "web",
    direction: "inbound",
    from: "visitor-1",
    to: "front-desk",
    caller: null,
    started_at: Date.now() / 1000,
  });
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function commands(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

function call(): FrontDesk["call"] {
  const agent = mounted.instanceOf(CALL) as FrontDesk;
  return agent.call;
}

it("asks for a transfer without a mode, and settles on what the log says happened", async () => {
  const transferring = call().transfer(THE_DESK);
  await settled();
  expect(commands("call.transfer")).toEqual([{ to: THE_DESK }]);

  gateway.emit(SLUG, CALL, "call.transferred", { to: THE_DESK, mode: "warm", ok: true });
  expect(await transferring).toEqual({ to: THE_DESK, mode: "warm", ok: true });
});

it("hears a transfer that did not take, with the reason the caller has to be told", async () => {
  const transferring = call().transfer(THE_DESK, { mode: "cold" });
  await settled();
  expect(commands("call.transfer")).toEqual([{ to: THE_DESK, mode: "cold" }]);

  gateway.emit(SLUG, CALL, "call.transferred", { to: THE_DESK, mode: "cold", ok: false, error: "busy" });
  expect(await transferring).toEqual({ to: THE_DESK, mode: "cold", ok: false, error: "busy" });
});

it("asks for a person and settles when a supervisor takes the line", async () => {
  const asking = call().attention("wants a refund", { waitS: 30 });
  await settled();
  expect(commands("call.attention")).toEqual([{ reason: "wants a refund", wait_s: 30 }]);

  const by = { id: "sup_1", name: "Lucía" };
  gateway.emit(SLUG, CALL, "attention.answered", { ok: true, by });
  expect(await asking).toEqual({ ok: true, by });
});

it("hears that nobody took the line", async () => {
  const asking = call().attention("wants a refund", { waitS: 30 });
  await settled();
  gateway.emit(SLUG, CALL, "attention.answered", { ok: false, by: null, error: "nobody took the line within 30s" });
  expect(await asking).toEqual({ ok: false, by: null, error: "nobody took the line within 30s" });
});

it("answers a verb still waiting when the call ends under it", async () => {
  const transferring = call().transfer(THE_DESK);
  const asking = call().attention("wants a refund", { waitS: 300 });
  await settled();
  gateway.emit(SLUG, CALL, "call.ended", {
    reason: "caller_hung_up",
    ended_by: "caller",
    ended_at: Date.now() / 1000,
    duration_s: 12,
  });

  expect((await transferring).ok).toBe(false);
  expect((await asking).error).toBe("the call ended before it was answered");
});

it("sends the verbs that expect no answer as they were written", async () => {
  const one = call();
  one.hold();
  one.unhold();
  one.dtmf("12,#");
  one.callback("+34600111222", { when: "mañana", note: "una duda" });
  one.optOut("please stop calling");
  one.optOut();
  one.hangup("done");
  await settled();

  expect(commands("call.hold")).toEqual([{}]);
  expect(commands("call.unhold")).toEqual([{}]);
  expect(commands("call.dtmf")).toEqual([{ digits: "12,#" }]);
  expect(commands("call.callback")).toEqual([{ number: "+34600111222", when: "mañana", note: "una duda" }]);
  expect(commands("call.opt_out")).toEqual([{ note: "please stop calling" }, {}]);
  expect(commands("call.hangup")).toEqual([{ reason: "done" }]);
});
