/** Minutes meter shows only when GET /v1/limits limits minutes; the upgrade link only when the box bills. */

import { expect, test } from "vitest";

import { type Limits, LimitsSchema } from "@pinecall/core/wire/rest-org";
import { minutesMeter } from "../src/lib/limits";

const NO_LIMIT = { limit: null, used: 0 };

// runtime api/limits.py, from a box that bills nobody.
const A_SELF_HOSTED_BOX: Limits = LimitsSchema.parse({
  minutes: { limit: null, used: 412.5 },
  messages: NO_LIMIT,
  llm_tokens: NO_LIMIT,
  concurrent_calls: NO_LIMIT,
  agents: NO_LIMIT,
  seats: NO_LIMIT,
  numbers: NO_LIMIT,
  evals: NO_LIMIT,
  simulations: NO_LIMIT,
  lends: null,
  billing_url: null,
  world: "production",
});

test("a box that limits no minutes draws no meter at all", () => {
  expect(minutesMeter(A_SELF_HOSTED_BOX)).toBeNull();
  expect(minutesMeter(null)).toBeNull();
});

test("a trial reads its minutes, and the link is there only where the box names where to pay", () => {
  const trial = { ...A_SELF_HOSTED_BOX, minutes: { limit: 30, used: 12.4 } };
  expect(minutesMeter(trial)).toEqual({ used: 12.4, limit: 30, billing: null });
  expect(minutesMeter({ ...trial, billing_url: "https://pinecall.io/billing" })?.billing).toBe("https://pinecall.io/billing");
});

test("a call that ran past the last minute never draws more than the limit", () => {
  expect(minutesMeter({ ...A_SELF_HOSTED_BOX, minutes: { limit: 30, used: 30.7 } })?.used).toBe(30);
});

test("the door's shape is the runtime's: a field renamed is refused", () => {
  expect(() => LimitsSchema.parse({ ...A_SELF_HOSTED_BOX, billing: null })).toThrow();
});
