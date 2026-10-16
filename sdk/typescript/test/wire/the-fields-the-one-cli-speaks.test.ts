/** call.started carries the state a call opens in, and agent.register says the socket answers the console. */

import { expect, it } from "vitest";

import { decodeEntry, eventOf } from "../../src/wire/codec.js";
import { COMMAND_SCHEMAS } from "../../src/wire/registry.js";

const started = { channel: "web", direction: "inbound", from: "web_7fb3", to: "clinica", caller: null, started_at: 1790878264.3 };

const entry = (type: string, data: Record<string, unknown>): unknown => ({
  seq: 2, ts: 1790878264.33, call: "call_1ee0", agent: "clinica", type, ephemeral: false, data,
});

it("reads call.started with the state the call opens in, keys as written", () => {
  const event = eventOf(decodeEntry(entry("call.started", { ...started, state: { patient_name: "Ana" } })));
  expect(event).toMatchObject({ data: { state: { patient_name: "Ana" } } });
});

it("reads call.started without a state as before", () => {
  const event = eventOf(decodeEntry(entry("call.started", started)));
  expect(event.data).not.toHaveProperty("state");
});

it("reads a call.attached whose started carries a state", () => {
  const attached = { app: "app_1", started: { ...started, state: { step: 2 } }, state: { step: 3 }, seq: 9 };
  expect(eventOf(decodeEntry(entry("call.attached", attached)))).toMatchObject({ data: { started: { state: { step: 2 } } } });
});

it("accepts agent.register with answers_dev, and without it", () => {
  const register = COMMAND_SCHEMAS["agent.register"];
  expect(register.safeParse({ routes: [], takes_unclaimed: false, answers_dev: true }).success).toBe(true);
  expect(register.safeParse({ routes: [] }).success).toBe(true);
});
