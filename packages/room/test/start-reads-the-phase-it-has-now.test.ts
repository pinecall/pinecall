// `start` asks the store where the conversation is, never a value it closed over when it was made.

import { describe, expect, it } from "vitest";

import { aRoom, held, LOG, MINTED } from "./a-room-at-hand.js";

describe("start", () => {
  it("is nothing while a call is opening or live, and opens again once it ended", async () => {
    const answers = [held<typeof MINTED>(), held<typeof MINTED>()];
    let asked = 0;
    const { store, gateway, livekit } = aRoom({
      tokens: () => {
        const next = answers[asked];
        asked += 1;
        if (next === undefined) throw new Error("asked too often");
        return next.promise;
      },
    });
    gateway.answer(LOG, { stream: [], then: "hold" }, { stream: [], then: "hold" });
    // Taken once, before anything happened — the way a button's handler holds it.
    const { start } = store;

    const first = start("talk");
    void start("talk");
    void start("chat");
    expect(asked).toBe(1);

    answers[0]?.resolve(MINTED);
    await first;
    expect(store.state.phase).toBe("live");
    await start("chat");
    expect(asked).toBe(1);

    livekit.room.hangUp();
    expect(store.state.phase).toBe("ended");
    const second = start("chat");
    expect(asked).toBe(2);
    expect(store.state.mode).toBe("chat");
    answers[1]?.resolve(MINTED);
    await second;
    expect(store.state.phase).toBe("live");
  });
});
