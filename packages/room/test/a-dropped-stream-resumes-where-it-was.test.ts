// A relay that goes away mid-call is asked again from the last seq read, a little later each time.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeGateway, framed, settle } from "./a-fake-gateway.js";
import { follow } from "./a-log-followed.js";
import { BOOKING } from "./a-real-booking.js";

const URL = "/api/log?call=call_1";
// The fixture's seqs are not 1..81: the 40th entry it holds is seq 126.
const FIRST = BOOKING.slice(0, 40);
const REST = BOOKING.slice(40);
const CURSOR = String(FIRST.at(-1)?.seq);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a dropped stream", () => {
  it("resumes where it was, backing off 500 ms and then 1000 ms", async () => {
    const gateway = new FakeGateway().answer(
      URL,
      { stream: [framed(FIRST)], then: "end" },
      { fails: true },
      { stream: [framed(REST)], then: "hold" },
    );
    const followed = follow(gateway, URL);
    await settle();
    expect(followed.fold.snapshot().entries).toHaveLength(40);
    expect(followed.connections).toEqual(["connecting", "live", "reconnecting"]);

    await vi.advanceTimersByTimeAsync(499);
    expect(gateway.requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    await settle();
    expect(gateway.requests).toHaveLength(2);
    expect(gateway.requests[1]?.lastEventId).toBe(CURSOR);

    await vi.advanceTimersByTimeAsync(999);
    expect(gateway.requests).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    await settle();
    expect(gateway.requests).toHaveLength(3);
    expect(gateway.requests[2]?.lastEventId).toBe(CURSOR);

    const { log, entries } = followed.fold.snapshot();
    expect(entries.map((entry) => entry.seq)).toEqual(BOOKING.map((entry) => entry.seq));
    expect(log.status).toBe("ended");
    expect(gateway.requests[0]?.lastEventId).toBeNull();
    expect(gateway.requests[0]?.accept).toBe("text/event-stream");
  });

  it("starts the backoff from 500 ms again once a stream is answered", async () => {
    const gateway = new FakeGateway().answer(
      URL,
      { stream: [framed(BOOKING.slice(0, 5))], then: "end" },
      { stream: [framed(BOOKING.slice(5, 10))], then: "end" },
      { stream: [], then: "hold" },
    );
    follow(gateway, URL);
    await settle();
    await vi.advanceTimersByTimeAsync(500);
    await settle();
    expect(gateway.requests).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(500);
    await settle();

    expect(gateway.requests).toHaveLength(3);
    expect(gateway.requests[2]?.lastEventId).toBe(String(BOOKING[9]?.seq));
  });
});
