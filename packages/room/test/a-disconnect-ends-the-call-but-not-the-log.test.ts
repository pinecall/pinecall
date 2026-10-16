// The room closing ends the call for the visitor. The log is read on: the score is still to come.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FRAME_MS } from "../src/store.js";
import { framed, settle } from "./a-fake-gateway.js";
import { aRoom, LAST_WORDS, LOG, TALKED } from "./a-room-at-hand.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a disconnect", () => {
  it("ends the call, and the log is read until the score", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("talk");
    livekit.room.hangUp();

    expect(store.state.phase).toBe("ended");
    expect(gateway.requests[0]?.aborted).toBe(false);

    gateway.push(framed(LAST_WORDS));
    await settle();
    await vi.advanceTimersByTimeAsync(FRAME_MS);

    expect(store.state.log.cost).not.toBeNull();
    expect(store.state.connection).toBe("ended");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops reading once it has lingered, when the score never comes", async () => {
    const { store, gateway, livekit } = aRoom({ linger: 5_000 });
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("talk");
    livekit.room.hangUp();
    await vi.advanceTimersByTimeAsync(4_999);
    expect(gateway.requests[0]?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    expect(gateway.requests[0]?.aborted).toBe(true);
    expect(store.state.connection).toBe("ended");
  });
});
