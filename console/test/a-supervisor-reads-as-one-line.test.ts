/** Each of the six supervise log entries renders as one sentence. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { expect, test } from "vitest";

import { supervisorMark } from "../src/lib/supervisor-mark";

const A_DESK = { id: "sup_a1b2c3", name: null };

test("each of the six moves reads as one sentence, with the desk that made it", () => {
  expect(supervisorMark(entry("supervisor.whispered", { by: A_DESK, text: "hay un hueco a las 15:40" }))).toEqual({
    said: "supervisor whispered: hay un hueco a las 15:40",
    by: "sup_a1b2c3",
  });
  expect(supervisorMark(entry("supervisor.said", { by: A_DESK, text: "un momento" }))?.said).toBe(
    "supervisor made the agent say: un momento",
  );
  expect(supervisorMark(entry("supervisor.took_over", { by: A_DESK }))?.said).toBe("supervisor took the line");
  expect(supervisorMark(entry("supervisor.released", { by: A_DESK }))?.said).toBe("supervisor handed the line back");
  expect(supervisorMark(entry("supervisor.transferred", { by: A_DESK, to: "+59899123456", mode: "cold" }))?.said).toBe(
    "supervisor transferred the call to +59899123456",
  );
  expect(supervisorMark(entry("supervisor.ended", { by: A_DESK, reason: "spam" }))?.said).toBe(
    "supervisor ended the call: spam",
  );
});

test("a desk with a name is read by it, and an end with no reason says only that it ended", () => {
  const named = entry("supervisor.ended", { by: { id: "sup_a1b2c3", name: "Bernardo" }, reason: null });
  expect(supervisorMark(named)).toEqual({ said: "supervisor ended the call", by: "Bernardo" });
});

test("an entry nobody at a desk wrote is no mark at all", () => {
  expect(supervisorMark(entry("tool.call", { call_id: "c1", name: "find_patient", arguments: {} }))).toBeNull();
  expect(supervisorMark(entry("turn.agent", { speech_id: "s1" }))).toBeNull();
});

function entry(type: string, data: Record<string, unknown>): Entry {
  return { seq: 12, ts: 1757000000, call: "call_x", agent: "clinica-norte", type, ephemeral: false, data };
}
