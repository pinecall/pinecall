// A conversation is kept by its resume token and started again with it: the same call while it
// waits for the visitor, else a new one carrying it on. Either way it is the server that mints.

import { describe, expect, it } from "vitest";

import { framed } from "./a-fake-gateway.js";
import { aRoom, LOG, MINTED, TALKED } from "./a-room-at-hand.js";

describe("a conversation resumed", () => {
  it("publishes the token to keep once the server minted, and \"\" when the gateway sent none", async () => {
    const asked: (string | undefined)[] = [];
    const kept = aRoom({
      tokens: async (_scope, resume) => {
        asked.push(resume);
        return { ...MINTED, resume_token: "resume_1" };
      },
    });
    kept.gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await kept.store.start("chat");
    expect(kept.store.state.resume).toBe("resume_1");
    expect(asked).toEqual([undefined]);

    const old = aRoom();
    old.gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await old.store.start("chat");
    expect(old.store.state.resume).toBe("");
  });

  it("hands the kept token to the server's mint, and leaving without hanging up says nothing", async () => {
    const asked: (string | undefined)[] = [];
    const { store, gateway, livekit } = aRoom({
      tokens: async (_scope, resume) => {
        asked.push(resume);
        return { ...MINTED, resume_token: "resume_2" };
      },
    });
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("chat", "resume_1");

    expect(asked).toEqual(["resume_1"]);
    expect(store.state.phase).toBe("live");
    expect(store.state.resume).toBe("resume_2");
    store.close();
    expect(livekit.room.localParticipant.published).toEqual([]);
  });
});
