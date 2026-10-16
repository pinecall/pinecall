// `call.score` is the last thing a call's log ever says: the follow stops itself there.

import { TERMINAL_EVENT } from "../src/wire/registry.js";
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

describe("the stream", () => {
  it("ends at the score: folded, closed, and never asked again", async () => {
    const after = { seq: 999, type: "custom" };
    const gateway = new FakeGateway().answer(URL, { stream: [framed(BOOKING) + frame(after)], then: "hold" });
    const followed = follow(gateway, URL);
    await settle();

    expect(BOOKING.at(-1)?.type).toBe(TERMINAL_EVENT);
    expect(followed.fold.snapshot().entries).toHaveLength(BOOKING.length);
    expect(followed.endings).toEqual([{ kind: "scored" }]);
    expect(gateway.requests[0]?.aborted).toBe(true);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(gateway.requests).toHaveLength(1);
    expect(followed.connections).toEqual(["connecting", "live"]);
  });

  it("says nothing more once the room stopped it", async () => {
    const gateway = new FakeGateway().answer(URL, { stream: [framed(BOOKING.slice(0, 3))], then: "hold" });
    const followed = follow(gateway, URL);
    await settle();
    followed.stop();
    gateway.push(framed(BOOKING.slice(3)));
    await settle();

    expect(followed.fold.snapshot().entries).toHaveLength(3);
    expect(followed.endings).toEqual([]);
    expect(gateway.requests[0]?.aborted).toBe(true);
  });
});
