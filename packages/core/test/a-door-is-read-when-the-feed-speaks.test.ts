/** use-fed.ts: a door is asked for while the feed is down, once as it comes back, and never while it is live. */

import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { paced } from "../src/use-fed";

let asked = 0;
const ask = (): void => {
  asked += 1;
};

beforeEach(() => {
  asked = 0;
  vi.useFakeTimers();
  vi.stubGlobal("window", { setInterval, clearInterval });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("until the feed opens the list is polled, then read once more, then left to the feed", () => {
  const pace = paced(ask, 3000);
  vi.advanceTimersByTime(6000);
  expect(asked).toBe(2);

  pace.connected("live");
  expect(asked).toBe(3);
  vi.advanceTimersByTime(60_000);
  expect(asked).toBe(3);
});

test("a feed that drops brings the polling back, and coming back reads what was missed", () => {
  const pace = paced(ask, 3000);
  pace.connected("live");
  asked = 0;

  pace.connected("reconnecting");
  vi.advanceTimersByTime(9000);
  expect(asked).toBe(3);

  pace.connected("live");
  expect(asked).toBe(4);
  vi.advanceTimersByTime(9000);
  expect(asked).toBe(4);
});

test("stopping leaves nothing asking", () => {
  const pace = paced(ask, 3000);
  pace.stop();
  vi.advanceTimersByTime(30_000);
  expect(asked).toBe(0);
});
