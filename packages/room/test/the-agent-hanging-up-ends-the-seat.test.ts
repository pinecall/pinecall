// When the log says the call ended, the seat is left: the page does not sit in a room nobody is in.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frame, framed, settle } from "./a-fake-gateway.js";
import { aRoom, LAST_WORDS, LOG, TALKED } from "./a-room-at-hand.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("the agent hanging up", () => {
  it("ends the call and leaves the seat, and the log reads on to the score", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("talk");
    expect(store.state.phase).toBe("live");

    const [ended, ...after] = LAST_WORDS;
    if (ended === undefined) throw new Error("the booking has no call.ended");
    gateway.push(frame(ended));
    await settle();

    expect(store.state.phase).toBe("ended");
    expect(livekit.room.disconnects).toBe(1);
    expect(gateway.requests[0]?.aborted).toBe(false);

    gateway.push(framed(after));
    await settle();
    expect(store.state.connection).toBe("ended");
    expect(store.state.log.cost).not.toBeNull();
  });
});
