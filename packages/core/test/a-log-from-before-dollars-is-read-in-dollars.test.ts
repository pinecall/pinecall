/** A call logged before money in dollars said its cost and its judges' in euros: read as the same number of dollars, as the runtime reads it. */

import { expect, test } from "vitest";

import { CostSchema } from "../src/wire/defs.js";
import { CallScoreSchema } from "../src/wire/events-call.js";

const ROW = { provider: "api.anthropic.com", model: "claude-haiku-5-5", unit: "input_tokens", quantity: 1200, unit_price_usd: 0.000001 };

test("a summary's cost in euros, with the rate it carried, is the same number of dollars", () => {
  const read = CostSchema.parse({ eur: 0.0421, rate: { usd_per_eur: 1.08 }, rows: [{ ...ROW, eur: 0.0012 }], unpriced: [] });
  expect(read).toEqual({ usd: 0.0421, rows: [{ ...ROW, usd: 0.0012 }], unpriced: [] });
});

test("a cost in dollars is read as it stands, and a word nobody wrote is still refused", () => {
  const today = { usd: 0.0421, rows: [{ ...ROW, usd: 0.0012 }], unpriced: [] };
  expect(CostSchema.parse(today)).toEqual(today);
  expect(() => CostSchema.parse({ ...today, gbp: 1 })).toThrow();
});

test("a score's judge cost in euros is its judge cost in dollars", () => {
  const read = CallScoreSchema.parse({ judges: [], judge_calls: 2, judge_cost_eur: 0.003 });
  expect(read.judge_cost_usd).toBe(0.003);
});
