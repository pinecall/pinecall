// Leaving while the page waits for a call aborts the ask the gateway is holding, and nothing is asked after it.

import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { settle } from "./a-fake-gateway.js";
import { aRoom, ASKED, CODE, GW } from "./a-room-at-hand.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

it("aborts the held ask and asks nothing more", async () => {
  const { store, gateway } = aRoom({ expect: async () => CODE, gateway: GW });
  gateway.answer(ASKED, { stream: [], then: "hold" });
  const going = store.byPhone();
  await settle();
  expect(store.state.phase).toBe("expecting");

  await store.leave();
  await going;
  await vi.advanceTimersByTimeAsync(30_000);
  await settle();

  expect(store.state.phase).toBe("ended");
  expect(gateway.requests).toHaveLength(1);
  expect(gateway.requests[0]?.aborted).toBe(true);
});
