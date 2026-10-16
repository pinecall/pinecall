// LiveKit is a WebRTC stack a page downloads only when it takes a seat: never for a phone call.

import { describe, expect, it } from "vitest";

import { aRoom, CALL, LOG } from "./a-room-at-hand.js";

describe("livekit", () => {
  it("is not loaded by making a room, by a failed mint, or by a phone call", async () => {
    let fail = true;
    const { store, livekit, gateway } = aRoom({
      tokens: async () => {
        if (fail) throw new Error("no");
        return { server_url: "wss://lk.example", participant_token: "ticket", call: CALL, log_token: "log_1" };
      },
      callMe: async () => ({ call: CALL }),
    });
    gateway.answer(LOG, { stream: [], then: "hold" }, { stream: [], then: "hold" });
    expect(livekit.loads).toBe(0);

    await store.start("talk");
    expect(livekit.loads).toBe(0);

    await store.callMe("+34600000001");
    await store.leave();
    expect(livekit.loads).toBe(0);

    fail = false;
    await store.start("chat");
    expect(livekit.loads).toBe(1);
  });
});
