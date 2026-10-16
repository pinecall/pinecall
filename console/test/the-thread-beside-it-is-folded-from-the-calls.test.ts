// The side pane is derived from the listed calls, with no extra gateway request.

import { type SessionLine } from "@pinecall/core/wire/rest";
import { describe, expect, it } from "vitest";

import { flagReads, standingOf } from "../src/screens/inbox/standing";

const A_CALL: SessionLine = {
  call: "CA_1",
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
  outcome: "Quoted a move-out clean",
  cost: null,
};

const line = (fields: Partial<SessionLine>): SessionLine => ({ ...A_CALL, ...fields });

describe("a thread's standing", () => {
  it("counts the calls, sums what ended, and keeps both ends of the thread", () => {
    const standing = standingOf([line({ call: "CA_2", started_at: 5_000, ended_at: 5_060 }), line({})]);
    expect(standing.conversations).toBe(2);
    expect(standing.seconds).toBe(180);
    expect([standing.first, standing.last]).toEqual([1_000, 5_000]);
  });

  it("leaves a call still going out of the length, because it is not one yet", () => {
    const standing = standingOf([line({ status: "active", ended_at: null }), line({})]);
    expect(standing.seconds).toBe(120);
    expect(standing.live).toBe(true);
  });

  it("names every door the person reached the agent by, each once", () => {
    const standing = standingOf([line({ channel: "whatsapp" }), line({ channel: "web" }), line({ channel: "whatsapp" })]);
    expect(standing.channels).toEqual(["whatsapp", "web"]);
  });

  it("adds the judges up over the calls anybody judged, and counts no others", () => {
    const standing = standingOf([
      line({ score: { held: 2, judged: 3, passed: false, reason: "quoted a price" } }),
      line({ score: { held: 2, judged: 2, passed: true, reason: null } }),
      line({}),
    ]);
    expect([standing.held, standing.judged]).toEqual([4, 5]);
  });

  it("raises each flag once over the whole thread, in the words a reviewer reads", () => {
    const standing = standingOf([line({ flags: ["escalated", "promise"] }), line({ flags: ["escalated"] })]);
    expect(standing.flags).toEqual(["escalated", "promise"]);
    expect(flagReads("low_score")).toBe("a judge broke");
  });

  it("folds an empty thread into nothing rather than into zeroes that lie", () => {
    expect(standingOf([])).toMatchObject({ conversations: 0, seconds: 0, first: null, last: null, channels: [], flags: [] });
  });
});
