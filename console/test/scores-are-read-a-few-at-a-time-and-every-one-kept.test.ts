// Twenty reads at once on every entry of the feed, each discarded when the next entry came, took the gateway's pool (2026-10-21).

import { type SessionLine } from "@pinecall/core/wire/rest";
import { describe, expect, it } from "vitest";

import { aFewAtATime, wanting, type Kept, type Scored } from "../src/lib/use-scores";

const A_CALL: SessionLine = {
  call: "call_1",
  agent: "clinica-norte",
  live: false,
  last_seq: 12,
  status: "ended",
  channel: "web",
  direction: "inbound",
  from: "web_44081bc0e202",
  to: null,
  caller: null,
  started_at: 1_000,
  ended_at: 1_120,
  end_reason: "caller_hung_up",
  outcome: null,
  cost: null,
};

const line = (fields: Partial<SessionLine>): SessionLine => ({ ...A_CALL, ...fields });
const read = (one: SessionLine, score: Scored["score"] = null): Scored => ({ line: one, read: true, score, refused: null });
const kept = (one: SessionLine, score: Scored["score"] = null): [string, Kept] => [one.call, { scored: read(one, score), seq: one.last_seq }];
const aScore: NonNullable<Scored["score"]> = { passed: true, judges: [], judge_calls: 1 };

describe("which calls want a read", () => {
  it("reads a call once, and again only while it had no score and its log has moved", () => {
    const first = line({ call: "call_1", last_seq: 12 });
    expect(wanting([first], new Map(), new Set())).toEqual([first]);
    expect(wanting([first], new Map([kept(first)]), new Set())).toEqual([]);
    const moved = line({ call: "call_1", last_seq: 14 });
    expect(wanting([moved], new Map([kept(first)]), new Set())).toEqual([moved]);
    expect(wanting([moved], new Map([kept(first, aScore)]), new Set())).toEqual([]);
  });

  it("believes a list that says the call has no score, and leaves a read in flight alone", () => {
    const unscored = line({ call: "call_2", score: null });
    expect(wanting([unscored], new Map(), new Set())).toEqual([]);
    const flying = line({ call: "call_3" });
    expect(wanting([flying], new Map(), new Set(["call_3"]))).toEqual([]);
  });
});

describe("reading a few at a time", () => {
  it("never has more than a few reads out, and keeps each as it lands", async () => {
    const lines = Array.from({ length: 9 }, (_, n) => line({ call: `call_${String(n)}` }));
    let out = 0;
    let most = 0;
    const landed: string[] = [];
    await aFewAtATime(
      lines,
      4,
      async (one) => {
        out += 1;
        most = Math.max(most, out);
        await new Promise((tick) => setTimeout(tick, 1));
        out -= 1;
        return read(one);
      },
      (one) => landed.push(one.call),
    );
    expect(most).toBe(4);
    expect([...landed].sort()).toEqual(lines.map((one) => one.call).sort());
  });

  it("keeps the rows that landed even when one read fails", async () => {
    const lines = [line({ call: "call_a" }), line({ call: "call_b" })];
    const landed: string[] = [];
    await aFewAtATime(lines, 1, async (one) => read(one), (one) => landed.push(one.call));
    expect(landed).toEqual(["call_a", "call_b"]);
  });
});
