/** Where a finished call's time went: every second given to one part, the parts adding up to the call. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { decodeEntry } from "@pinecall/core/wire/codec";
import { apply, initialState } from "@pinecall/core/wire/reduce";
import { expect, test } from "vitest";

import { timeSpentIn } from "../src/screens/call/over/time-spent.js";

// The runtime's golden call, as the core holds it (packages/core/test/golden/).
const entries = (
  JSON.parse(readFileSync(fileURLToPath(new URL("../../packages/core/test/golden/call-log.json", import.meta.url)), "utf8")) as unknown[]
).map(decodeEntry);
const state = entries.reduce(apply, initialState());
const spent = timeSpentIn(entries, state);
const part = (kind: string): number => spent?.parts.find((one) => one.kind === kind)?.seconds ?? 0;

test("the parts add up to the call, from its start to its end", () => {
  expect(spent?.length).toBeCloseTo(1786537552.4 - 1786537500.412, 6);
  expect(spent?.parts.reduce((sum, one) => sum + one.seconds, 0)).toBeCloseTo(spent?.length ?? 0, 6);
});

// Worked by hand from the golden turns' speaking times and its two tools.
test("each part is what the turns and tools say", () => {
  expect(part("before")).toBeCloseTo(0.324, 6);
  expect(part("caller")).toBeCloseTo(9.13, 6);
  expect(part("agent")).toBeCloseTo(28.294, 6);
  expect(part("both")).toBeCloseTo(0.32, 6);
  expect(part("on_the_agent")).toBeCloseTo(5.618, 6);
  expect(part("tool")).toBeCloseTo(0.222, 6);
  expect(part("on_the_caller")).toBeCloseTo(8.08, 6);
});

// The silence between each caller's turn and the agent's reply, from the turns' own timings on this log
// (0.90, 1.73, 0.94, 1.45 and 0.82 s), is the time waiting on the agent plus the tool that ran inside it.
test("waiting on the agent and on its tools is the silence before each reply, summed", () => {
  expect(part("on_the_agent") + part("tool")).toBeCloseTo(0.9 + 1.73 + 0.94 + 1.45 + 0.82, 5);
});

// The runtime writes one `call.transferred` for every transfer, the agent's or a supervisor's.
const transferred = (ok: boolean) =>
  decodeEntry({ seq: 999, ts: 1786537541.6, call: "CA_8f4a2c", agent: "clinica-norte", type: "call.transferred", ephemeral: false, data: { to: "+34910000002", mode: "warm", ok } });

test("from a transfer that took to the end, the call is with a person, whoever is heard", () => {
  const handed = timeSpentIn([...entries, transferred(true)], state);
  expect(handed?.parts.find((one) => one.kind === "person")?.seconds).toBeCloseTo(1786537552.4 - 1786537541.6, 6);
  expect(handed?.parts.reduce((sum, one) => sum + one.seconds, 0)).toBeCloseTo(handed?.length ?? 0, 6);
});

test("a transfer that failed leaves the call the agent's", () => {
  expect(timeSpentIn([...entries, transferred(false)], state)?.parts.map((one) => one.kind)).not.toContain("person");
});

test("a call still going is not read for it", () => {
  expect(timeSpentIn(entries, { ...state, ended_at: null })).toBeNull();
});
