/** The runs kept: two diffed by what moved, a real call promoted with its review notes, each judge's drift between two windows. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { UsageError } from "../../../src/errors.js";
import * as runs from "../../../src/evals/service/runs.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { aRun } from "../../support/fixtures.js";
import { folder } from "../../support/project.js";

const NOW = 1_792_200_000;
const DAY = 86_400;

describe("a diff", () => {
  it("names a score that flipped, one new and broken, and one no longer measured", () => {
    const was = aRun([{ metric: "tools", passed: true }, { metric: "grounded", passed: true }], "run_1");
    const now = aRun([{ metric: "tools", passed: false, reason: "never booked" }, { metric: "says", passed: false, reason: "no greeting" }], "run_2");
    expect(runs.movedBetween(was, now)).toEqual([
      { golden: "books-thursday", metric: "tools", was: "held", now: "broken", reason: "never booked" },
      { golden: "books-thursday", metric: "says", was: "not measured", now: "broken", reason: "no greeting" },
      { golden: "books-thursday", metric: "grounded", was: "held", now: "not measured", reason: "" },
    ]);
  });
});

describe("a promoted call", () => {
  const scored = (judges: [string, string][]): void =>
    void answer("get", "/v1/calls/:call/events", { entries: [{ seq: 40, type: "call.score", data: { judges: judges.map(([name, verdict]) => ({ name, verdict })) } }], next: null });

  it("is the gateway's golden of the call, written as a candidate with notes on what its expect asks", async () => {
    const sent = answer("get", "/v1/calls/:call/golden", { name: "call-9-consent", turns: [{ say: "Book me" }], expect: { not_tools: ["book"], grounded: true } });
    scored([["consent", "broken"], ["grounded", "broken"]]);
    const out = folder();
    const { ctx } = testContext();
    const promoted = await runs.promoteCall(ctx, runs.PromoteInput.parse({ call: "call_9", fromSeq: 12, out }));
    expect(sent[0]!.query).toEqual({ from_seq: "12" });
    expect(promoted.path).toBe(join(out, "call-9-consent.json"));
    expect(JSON.parse(readFileSync(promoted.path, "utf8"))).toEqual(promoted.candidate);
    expect(promoted.notes).toEqual([runs.CONSENT_BANS_THE_TOOL, runs.GROUNDED_IS_ASKED]);
  });

  it("of a call that held says to write what it must keep doing", async () => {
    answer("get", "/v1/calls/:call/golden", { name: "fine", turns: [] });
    scored([["grounded", "held"]]);
    const { ctx } = testContext();
    expect((await runs.promoteCall(ctx, runs.PromoteInput.parse({ call: "call_1", out: folder() }))).notes).toEqual([runs.NOTHING_BROKE]);
  });

  // T F11: `expected-outcome` fits no golden, so the expect is empty, and the note read as if the call held.
  it("of a call a judge broke that no golden field asks again names that judge", async () => {
    answer("get", "/v1/calls/:call/golden", { name: "cancel", turns: [{ say: "Cancel it" }], expect: {} });
    scored([["expected-outcome", "broken"], ["grounded", "held"]]);
    const { ctx } = testContext();
    expect((await runs.promoteCall(ctx, runs.PromoteInput.parse({ call: "call_2", out: folder() }))).notes).toEqual([runs.BROKE_UNASKED(["expected-outcome"])]);
  });
});

describe("drift", () => {
  const ended = (call: string, daysAgo: number) => ({ call, agent: "front-desk", live: false, last_seq: 40, ended_at: NOW - daysAgo * DAY });
  const score = (verdicts: [string, string][]) => ({ passed: verdicts.every(([, verdict]) => verdict !== "broken"), judges: verdicts.map(([name, verdict]) => ({ name, verdict, criteria: "", reason: verdict === "broken" ? "it lied" : "", evidence: { seqs: [9] } })) });

  it("is each judge's held-rate in the window against the time before it, in points", async () => {
    answer("get", "/v1/agents/:slug/sessions", { calls: [ended("now_1", 1), ended("now_2", 2), ended("before_1", 10), ended("before_2", 20), { ...ended("live", 0), live: true }] });
    const scores: Record<string, unknown> = {
      now_1: score([["grounded", "held"]]),
      now_2: score([["grounded", "broken"]]),
      before_1: score([["grounded", "held"]]),
      before_2: score([["grounded", "held"], ["consent", "skipped"]]),
    };
    const pages = answer("get", "/v1/calls/:call/events", ({ path }) => ({ entries: [{ seq: 40, type: "call.score", data: scores[path.split("/")[3]!] }], next: null }));
    const { ctx } = testContext();
    const drift = await runs.driftOf(ctx, runs.DriftInput.parse({ agent: "front-desk", window: 7 * DAY, baseline: 30 * DAY }), NOW);
    expect(drift.judges).toEqual([
      { judge: "consent", before: null, now: null, delta: null },
      { judge: "grounded", before: { held: 2, settled: 2, percent: 100 }, now: { held: 1, settled: 2, percent: 50 }, delta: -50 },
    ]);
    expect(drift.broke).toEqual([{ call: "now_2", judge: "grounded", seqs: [9], reason: "it lied" }]);
    expect(runs.drifted(drift)).toBe(true);
    expect(pages[0]!.query).toMatchObject({ after: "39", types: "call.score", limit: "4" });
  });

  it("refuses a baseline no longer than the window", async () => {
    const { ctx } = testContext();
    await expect(runs.driftOf(ctx, runs.DriftInput.parse({ agent: "front-desk", window: 7 * DAY, baseline: 7 * DAY }))).rejects.toBeInstanceOf(UsageError);
  });

  it("reads a window as seconds", () => {
    expect(["90m", "24h", "7d", "30s", "7 days"].map(runs.secondsOf)).toEqual([5400, 86_400, 604_800, 30, null]);
  });
});
