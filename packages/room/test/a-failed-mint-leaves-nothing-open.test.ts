// A ticket the tenant's server could not mint is a failed call, with nothing opened on the way.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { settle } from "./a-fake-gateway.js";
import { aRoom, LOG, MINTED } from "./a-room-at-hand.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a failed mint", () => {
  it("fails with the server's sentence, and opens neither the log nor a seat", async () => {
    const { store, gateway, livekit } = aRoom({
      tokens: async () => {
        throw new Error("every seat of the fleet is taken");
      },
    });
    await store.start("talk");

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("every seat of the fleet is taken");
    expect(store.state.connection).toBe("ended");
    expect(gateway.requests).toEqual([]);
    expect(livekit.loads).toBe(0);
  });

  it("closes the log an earlier call left lingering", async () => {
    let mints = 0;
    const { store, gateway, livekit } = aRoom({
      tokens: async () => {
        mints += 1;
        if (mints > 1) throw new Error("the key was revoked");
        return MINTED;
      },
    });
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("chat");
    livekit.room.hangUp();
    expect(store.state.phase).toBe("ended");
    expect(gateway.requests[0]?.aborted).toBe(false);

    await store.start("chat");
    await settle();

    expect(store.state.phase).toBe("failed");
    expect(gateway.requests[0]?.aborted).toBe(true);
    expect(gateway.requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
