// A proxy answering 502 while the gateway behind it restarts is a gateway away, not a refusal.

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { FakeGateway, framed, settle } from "./a-fake-gateway.js";
import { follow } from "./a-log-followed.js";
import { BOOKING } from "./a-real-booking.js";

const URL = "/api/log?call=call_1";
const FIRST = BOOKING.slice(0, 40);
const REST = BOOKING.slice(40);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

it("asks again after a 502 and a 503, backing off, and resumes where it was", async () => {
  const gateway = new FakeGateway().answer(
    URL,
    { stream: [framed(FIRST)], then: "end" },
    { status: 502 },
    { status: 503 },
    { stream: [framed(REST)], then: "hold" },
  );
  const followed = follow(gateway, URL);
  await settle();
  await vi.advanceTimersByTimeAsync(500);
  await settle();
  await vi.advanceTimersByTimeAsync(1000);
  await settle();
  await vi.advanceTimersByTimeAsync(2000);
  await settle();
  expect(gateway.requests).toHaveLength(4);
  expect(gateway.requests[3]?.lastEventId).toBe(String(FIRST.at(-1)?.seq));
  expect(followed.endings).toEqual([{ kind: "scored" }]);
  expect(followed.fold.snapshot().entries).toHaveLength(BOOKING.length);
});

it("ends on a 401: the gateway saying no is not asked again", async () => {
  const gateway = new FakeGateway().answer(URL, { status: 401 });
  const followed = follow(gateway, URL);
  await settle();
  await vi.advanceTimersByTimeAsync(10_000);
  expect(gateway.requests).toHaveLength(1);
  expect(followed.endings).toEqual([{ kind: "refused", status: 401 }]);
});
