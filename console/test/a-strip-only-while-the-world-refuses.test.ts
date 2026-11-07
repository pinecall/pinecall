/** The strip over every screen says what is used up and what that refuses, or that production is closed; a world that refuses nothing draws none. */

import { expect, test } from "vitest";

import { type Limits, LimitsSchema } from "@pinecall/core/wire/rest-org";
import { stripSaid, usedUp } from "../src/lib/used-up";

const NO_LIMIT = { limit: null, used: 0 };
const NOW = new Date(Date.UTC(2026, 10, 7));

// runtime api/limits.py: a trial in the sandbox, nothing used up yet.
const A_TRIAL: Limits = LimitsSchema.parse({
  minutes: { limit: 30, used: 12.4 },
  messages: { limit: 300, used: 4 },
  llm_tokens: { limit: 2000000, used: 51000 },
  concurrent_calls: { limit: 1, used: 0 },
  agents: NO_LIMIT,
  seats: NO_LIMIT,
  numbers: NO_LIMIT,
  evals: { limit: 500, used: 12 },
  simulations: { limit: 10, used: 3 },
  memory_facts: NO_LIMIT,
  knowledge_chunks: NO_LIMIT,
  hosted_apps: { limit: 3, used: 3 },
  budget_usd: NO_LIMIT,
  lends: ["deepgram"],
  billing_url: "https://billing.pinecall.io/",
  world: "sandbox",
});

test("a world with something left of everything draws no strip, whatever the caps on what it keeps say", () => {
  expect(usedUp(A_TRIAL)).toEqual([]);
  expect(stripSaid(A_TRIAL, NOW)).toBeNull();
});

test("the last minute used says so, what that refuses, and when the minutes start again", () => {
  const out = { ...A_TRIAL, minutes: { limit: 30, used: 30.7 } };
  expect(usedUp(out)).toEqual([{ quota: "minutes", used: 30.7, limit: 30 }]);
  expect(stripSaid(out, NOW)).toBe("Minutes used up in the sandbox: 30 of 30 minutes. Calls are refused until they start again on 1 Dec.");
});

test("several used up are said as one sentence, each refusal named once", () => {
  const out = { ...A_TRIAL, minutes: { limit: 30, used: 30 }, messages: { limit: 300, used: 300 }, simulations: { limit: 10, used: 10 }, world: "production" as const };
  expect(stripSaid(out, NOW)).toBe(
    "Minutes, messages and simulations used up in production: 30 of 30 minutes, 300 of 300 messages, 10 of 10 simulations. Calls and simulations are refused until they start again on 1 Dec.",
  );
});

test("the spend guard reads in dollars", () => {
  const out = { ...A_TRIAL, budget_usd: { limit: 290, used: 290.4 } };
  expect(stripSaid(out, NOW)).toBe("Monthly spend used up in the sandbox: $290 of $290. Calls are refused until they start again on 1 Dec.");
});

test("a production closed to the org is said as that, never as zero of zero", () => {
  const closed = { ...A_TRIAL, minutes: { limit: 0, used: 0 }, messages: { limit: 0, used: 0 }, world: "production" as const };
  expect(usedUp(closed)).toEqual([]);
  expect(stripSaid(closed, NOW)).toBe("Production is closed to this organization: it opens with a plan. Build and test in the sandbox meanwhile.");
  // The sandbox of the same org is open: the free plan is the sandbox.
  expect(stripSaid({ ...closed, world: "sandbox" }, NOW)).toBeNull();
});
