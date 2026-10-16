/** A call is two metered rows, its summary and its score: one line carries its minutes, the evals its score billed, and whether a simulated caller played it. */

import { expect, test } from "vitest";

import type { UsageRow } from "../src/screens/usage/door";
import { byCall, total } from "../src/screens/usage/folded";

const ROW: UsageRow = { cursor: 1, org: "clinica", agent: "clinica-norte", call: "CA_1", type: "call.summary", at: 10, minutes: 1.5, messages: 6, input_tokens: 0, output_tokens: 0, characters: 0, judge_calls: 0, evals: 0, simulated: false, cost_usd: 0.002 };

test("a call's summary and score fold into one line with the evals the score billed", () => {
  const [line] = byCall([ROW, { ...ROW, cursor: 2, type: "call.score", minutes: 0, messages: 0, judge_calls: 9, evals: 7, cost_usd: 0.001 }]);

  expect([line?.minutes, line?.judge_calls, line?.evals, line?.simulations]).toEqual([1.5, 9, 7, 0]);
});

test("a call a simulated caller played is one simulation, however many rows it wrote", () => {
  const simulated = { ...ROW, call: "CA_2", simulated: true };
  const all = total(byCall([ROW, simulated, { ...simulated, cursor: 3, type: "call.score", simulated: false, evals: 2 }]));

  expect([all.calls, all.simulations, all.evals]).toEqual([2, 1, 2]);
});
