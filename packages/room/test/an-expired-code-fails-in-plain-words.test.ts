// A code nobody called with, or one the gateway will not talk about, is a failed phase and a sentence.

import { describe, expect, it } from "vitest";

import { aRoom, ASKED, CODE, GW } from "./a-room-at-hand.js";

describe("a code that no call claimed", () => {
  it("fails in plain words once it expired", async () => {
    const { store, gateway } = aRoom({ expect: async () => CODE, gateway: GW });
    const expired = { code: CODE.code, status: "expired", expires_at: CODE.expires_at, call: null, log_token: null };
    gateway.answer(ASKED, { status: 200, body: JSON.stringify(expired) });
    await store.byPhone();

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("the code expired: ask for another");
    expect(gateway.requests).toHaveLength(1);
  });

  it("fails naming the status when the gateway says no", async () => {
    const { store, gateway } = aRoom({ expect: async () => CODE, gateway: GW });
    gateway.answer(ASKED, { status: 403, body: '{"detail":"not this code"}' });
    await store.byPhone();

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("the code answered 403");
  });

  it("fails with the server's sentence when no code could be had", async () => {
    const { store, gateway } = aRoom({
      expect: async () => {
        throw new Error("agent clinica answers at no phone number in production");
      },
    });
    await store.byPhone();

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("agent clinica answers at no phone number in production");
    expect(gateway.requests).toEqual([]);
  });
});
