// Every simulation comes from the one simulated caller; grouped by address, six would be one thread.

import { type SessionLine } from "@pinecall/core/wire/rest";
import { describe, expect, it } from "vitest";

import { lettersOf, threadsOf, titleOf } from "../src/screens/inbox/threads";

const A_CALL: SessionLine = {
  call: "call_3f7d8c21aa",
  agent: "clinica-norte",
  live: false,
  last_seq: 12,
  status: "ended",
  channel: "web",
  direction: "inbound",
  from: "simulated_caller",
  to: null,
  caller: null,
  started_at: 1_000,
  ended_at: 1_120,
  end_reason: "caller_hung_up",
  outcome: null,
  cost: null,
};

const line = (fields: Partial<SessionLine>): SessionLine => ({ ...A_CALL, ...fields });

describe("a simulated call in the threads", () => {
  it("is a thread of its own, however many simulations ran", () => {
    const threads = threadsOf([line({}), line({ call: "call_aaaa1111", started_at: 2_000 }), line({ call: "call_bbbb2222", started_at: 3_000 })]);
    expect(threads.map((thread) => thread.contact)).toEqual(["call_bbbb2222", "call_aaaa1111", "call_3f7d8c21aa"]);
    expect(threads.every((thread) => thread.lines.length === 1)).toBe(true);
  });

  it("is named by its call, as a web visitor is, and says who was on it", () => {
    const [thread] = threadsOf([line({})]);
    expect(titleOf(thread!)).toBe("Simulation · 3f7d");
    expect(thread!.handle).toBe("simulated caller");
    expect(lettersOf(thread!)).toBe("S");
  });

  it("leaves a person's calls grouped by who they are", () => {
    const threads = threadsOf([line({ from: "+34612345678", call: "call_1" }), line({ from: "+34612345678", call: "call_2", started_at: 2_000 })]);
    expect(threads).toHaveLength(1);
    expect(threads[0]!.lines).toHaveLength(2);
  });
});
