/** broken.ts: a judge that broke marks the rows it cites, and a seq no row carries lands on the row before it. */

import { expect, test } from "vitest";

import type { CallScore } from "@pinecall/core/wire/events-call";

import { brokenAt } from "../src/screens/call/broken";
import type { Row } from "../src/screens/call/timeline-rows";

const row = (kind: Row["kind"], seq: number): Row => ({ kind, seq }) as unknown as Row;

const ROWS = [row("turn", 10), row("tool", 12), row("state", 14), row("turn", 20), row("quiet", 22), row("turn", 30)];

const judged = (judges: { name: string; verdict: string; seqs: number[]; reason: string }[]): CallScore =>
  ({
    passed: false,
    judge_calls: 1,
    judges: judges.map(({ name, verdict, seqs, reason }) => ({ name, verdict, reason, criteria: "", evidence: { seqs } })),
  }) as unknown as CallScore;

test("a judge that broke marks the turns it cites, with its reason", () => {
  const broken = brokenAt(judged([{ name: "ended-well", verdict: "broken", seqs: [30], reason: "asked a question and hung up" }]), ROWS);
  expect([...broken.entries()]).toEqual([[30, [{ judge: "ended-well", reason: "asked a question and hung up" }]]]);
});

test("a seq no row carries, a tool's result or a state change, lands on the row before it", () => {
  const broken = brokenAt(judged([{ name: "grounded", verdict: "broken", seqs: [13, 15], reason: "said a time the tool never gave" }]), ROWS);
  expect([...broken.keys()]).toEqual([12]);
});

test("a judge that held, or one that cites nothing, marks no row; two judges on one row are both said", () => {
  const broken = brokenAt(
    judged([
      { name: "consent", verdict: "held", seqs: [20], reason: "" },
      { name: "promises", verdict: "broken", seqs: [], reason: "promised a call back" },
      { name: "grounded", verdict: "broken", seqs: [20], reason: "a date" },
      { name: "ended-well", verdict: "broken", seqs: [20], reason: "no goodbye" },
    ]),
    ROWS,
  );
  expect(broken.get(20)?.map((one) => one.judge)).toEqual(["grounded", "ended-well"]);
  expect(broken.size).toBe(1);
  expect(brokenAt(null, ROWS).size).toBe(0);
});
