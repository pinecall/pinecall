/** A call's log read for a benchmark: its lines against the recording's clock, a tool's answer under its call, and why a call does not count. */

import { describe, expect, it } from "vitest";

import type { Entry, Row } from "../../src/evals/calls.js";
import { linesOf, notCountedOf, recordingBegan, repliesOf } from "../../src/evals/transcript.js";

const A_ROW: Row = {
  call: "call_1",
  persona: "books-a-visit",
  against: { llm: "openai/gpt-5.4-mini" },
  started_at: 100,
  ended_at: 190,
  end_reason: "caller_hung_up",
  score: { passed: true, reason: null },
  cost_usd: 0.05,
  latency: { e2e_latency: 1.2, llm_node_ttft: null, tts_node_ttfb: null, transcription_delay: null, end_of_turn_delay: null },
  why: null,
};

const entry = (_seq: number, ts: number, type: string, data: Record<string, unknown> = {}): Entry => ({ ts, type, data });

describe("a call's lines", () => {
  const log = [
    entry(1, 100.4, "agent.state", { state: "speaking" }),
    entry(2, 103, "turn.agent", { text: "Brightside Dental. How can I help?", metrics: { started_speaking_at: 101.4, stopped_speaking_at: 103 } }),
    entry(3, 110, "turn.user", { text: "Move my cleaning to Wednesday.", metrics: { started_speaking_at: 106.4, stopped_speaking_at: 109.4 } }),
    entry(4, 111.4, "tool.call", { name: "openTimes", call_id: "t1", arguments: { day: "2026-12-02", service: "cleaning" } }),
    entry(5, 111.9, "tool.result", { call_id: "t1", output: "13:30 with Mia Torres" }),
    entry(6, 114, "turn.agent", { text: "I have one thirty", interrupted: true, metrics: { started_speaking_at: 112.4, stopped_speaking_at: 113.4, e2e_latency: 1.1 } }),
  ];

  it("are placed by the recording's clock, which begins at the log's first agent.state where the gateway does not say", () => {
    const began = recordingBegan(log, 100);
    expect(began).toEqual({ at: 100.4, said: false });
    expect(linesOf(log, began.at).map((line) => [line.who, line.at, line.until])).toEqual([["agent", 1, 2.6], ["caller", 6, 9], ["tool", 11, undefined], ["agent", 12, 13]]);
  });

  it("believe the gateway when its summary says when the recording began", () => {
    expect(recordingBegan([...log, entry(7, 190, "call.summary", { recording_started_at: 100.1 })], 100)).toEqual({ at: 100.1, said: true });
  });

  it("carry what a tool answered under its call, and mark a line the caller cut", () => {
    const lines = linesOf(log, 100.4);
    expect(lines[2]).toMatchObject({ who: "tool", text: "openTimes(day=2026-12-02, service=cleaning)", gave: "13:30 with Mia Torres" });
    expect(lines[3]?.cut).toBe(true);
    expect(repliesOf(log)).toEqual([1.1]);
  });
});

describe("why a call does not count", () => {
  it("is what the gateway says on its row, when it says", () => {
    expect(notCountedOf({ ...A_ROW, valid: false, invalid: { kind: "caller", why: "its voice broke up" } }, [])).toEqual({ kind: "caller", why: "its voice broke up" });
    expect(notCountedOf({ ...A_ROW, valid: true, end_reason: "error" }, [])).toBeNull();
  });

  it("is read off the log of a gateway that does not say: a vendor's refusal in its own words", () => {
    const log = [entry(1, 101, "error", { code: "component_failed", message: "openai refused this call's model: You have no credits remaining.\nmore" })];
    expect(notCountedOf({ ...A_ROW, end_reason: "timeout" }, log)).toEqual({ kind: "vendor", why: "openai refused this call's model: You have no credits remaining." });
  });

  it("is the platform's when the call ended in error or never started, and nothing for a model that was only wrong", () => {
    expect(notCountedOf({ ...A_ROW, end_reason: "error" }, [])).toEqual({ kind: "platform", why: "the call ended in error" });
    expect(notCountedOf({ ...A_ROW, why: "no agent joined room in 110s" }, [])?.kind).toBe("platform");
    expect(notCountedOf({ ...A_ROW, score: { passed: false, reason: "moved it to Tuesday" } }, [])).toBeNull();
  });
});
