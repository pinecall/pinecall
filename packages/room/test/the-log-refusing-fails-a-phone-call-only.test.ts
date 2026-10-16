// A relay that refuses the log is the whole call on the phone, and only the drawing of it in a room.

import { describe, expect, it } from "vitest";

import { settle } from "./a-fake-gateway.js";
import { aRoom, CALL, LOG } from "./a-room-at-hand.js";

describe("the log refusing", () => {
  it("fails a phone call, naming the status", async () => {
    const { store, gateway } = aRoom({ callMe: async () => ({ call: CALL }) });
    gateway.answer(LOG, { status: 401, body: '{"detail":"no key"}' });
    await store.callMe("+34600000001");
    await settle();

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("the log answered 401");
    expect(store.state.connection).toBe("ended");
  });

  it("leaves a call in a room live: the seat is the call, the log only draws it", async () => {
    const { store, gateway } = aRoom();
    gateway.answer(LOG, { status: 403 });
    await store.start("chat");
    await settle();

    expect(store.state.phase).toBe("live");
    expect(store.state.connection).toBe("ended");
    expect(store.state.error).toBe("");
  });
});
