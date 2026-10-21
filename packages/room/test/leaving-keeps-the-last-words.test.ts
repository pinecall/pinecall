// Leaving ends the call at once, and the agent's last words, the cost and the score still arrive.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FRAME_MS } from "../src/store.js";
import { framed, settle } from "./a-fake-gateway.js";
import { aRoom, held, LAST_WORDS, LOG, TALKED } from "./a-room-at-hand.js";
import { BOOKING } from "./a-real-booking.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("leaving", () => {
  it("is ended at once, and the log after it is still folded", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("chat");
    const leaving = store.leave();

    expect(store.state.phase).toBe("ended");
    await leaving;
    expect(livekit.room.connected).toBe(false);

    gateway.push(framed(LAST_WORDS));
    await settle();
    await vi.advanceTimersByTimeAsync(FRAME_MS);

    expect(store.state.entries).toHaveLength(BOOKING.length);
    expect(store.state.log.cost).not.toBeNull();
    expect(store.state.connection).toBe("ended");
  });

  it("says the visitor hung up at the gateway's door and in the room before the seat goes, so the call does not wait for them", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("chat");
    await store.leave();

    // At the door first, with the call's own token, asked to outlive the page; then in the room.
    const said = gateway.requests.filter((asked) => asked.method === "POST");
    expect(said.map((asked) => [asked.url, asked.keepalive])).toEqual([
      ["https://cloud.pinecall.io/v1/calls/call_1/hangup?token=log_1", true],
    ]);
    expect(livekit.room.localParticipant.published).toEqual([{ data: "{}", topic: "pinecall.hangup" }]);
  });

  it("does not wait more than three seconds on a room that never answers", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    livekit.stallDisconnect = held<void>().promise;
    let left = false;
    void store.leave().then(() => {
      left = true;
    });

    await vi.advanceTimersByTimeAsync(2_999);
    expect(left).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(left).toBe(true);
  });

  it("is nothing when there is no call", async () => {
    const { store, heard } = aRoom();
    await store.leave();

    expect(store.state.phase).toBe("idle");
    expect(heard).toEqual([]);
  });
});

describe("send", () => {
  it("sends in a live call, is nothing for an empty line, and refuses outside a call", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await expect(store.send("hello")).rejects.toThrow("not in a call");
    await store.start("chat");
    await store.send("   ");
    await store.send("hello");
    expect(livekit.room.localParticipant.sent).toEqual([{ text: "hello", topic: "lk.chat" }]);

    await store.leave();
    await expect(store.send("still there?")).rejects.toThrow("not in a call");
  });
});
