// An entry this copy of the wire cannot read is one entry, not a broken call: skipped, said, passed.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeGateway, frame, framed, settle } from "./a-fake-gateway.js";
import { follow } from "./a-log-followed.js";
import { BOOKING } from "./a-real-booking.js";

const URL = "/api/log?call=call_1";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("an unreadable entry", () => {
  it("is skipped, the reader is told why, and the rest of the call folds", async () => {
    const garbled = frame({ seq: 500, type: "turn.user" }, "{not json");
    const shapeless = frame({ seq: 501, type: "turn.user" }, '{"seq":"one"}');
    const gateway = new FakeGateway().answer(URL, {
      stream: [framed(BOOKING.slice(0, 10)) + garbled + shapeless + framed(BOOKING.slice(10))],
      then: "hold",
    });
    const followed = follow(gateway, URL);
    await settle();

    expect(followed.skipped).toHaveLength(2);
    expect(followed.skipped[0]).toContain("turn.user at 500");
    expect(followed.fold.snapshot().entries).toHaveLength(BOOKING.length);
    expect(followed.fold.snapshot().log.status).toBe("ended");
  });

  it("still moves the cursor: a resume starts after it", async () => {
    const garbled = frame({ seq: 500, type: "turn.user" }, "{not json");
    const gateway = new FakeGateway().answer(
      URL,
      { stream: [framed(BOOKING.slice(0, 3)) + garbled], then: "end" },
      { stream: [], then: "hold" },
    );
    follow(gateway, URL);
    await settle();
    await vi.advanceTimersByTimeAsync(500);
    await settle();

    expect(gateway.requests[1]?.lastEventId).toBe("500");
  });
});
