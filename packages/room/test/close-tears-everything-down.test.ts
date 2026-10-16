// `close` is the component unmounting: the log, the seat, the paint and the linger, all of it, now.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FRAME_MS } from "../src/store.js";
import { framed, settle } from "./a-fake-gateway.js";
import { aRoom, LOG, TALKED } from "./a-room-at-hand.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("close", () => {
  it("tears a live call down: the log, the seat, the paint waiting", async () => {
    const { store, gateway, livekit, heard } = aRoom();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    gateway.push(framed(TALKED));
    await settle();
    const before = heard.length;
    store.close();
    await settle();

    expect(gateway.requests[0]?.aborted).toBe(true);
    expect(livekit.room.connected).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(FRAME_MS * 10);
    expect(heard).toHaveLength(before);
  });

  it("stops a lingering log and a leave that was waiting, and no timer fires afterwards", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    livekit.stallDisconnect = new Promise(() => {});
    const leaving = store.leave();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    store.close();
    await leaving;

    expect(gateway.requests[0]?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("leaves a room that answers no verb", async () => {
    const { store, minted } = aRoom();
    store.close();
    await store.start("talk");

    expect(minted).toEqual([]);
    expect(store.state.phase).toBe("idle");
  });
});
