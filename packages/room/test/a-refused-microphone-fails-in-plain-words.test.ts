// A seat that could not be taken fails the call: in words a visitor can act on when it is the microphone.

import { describe, expect, it } from "vitest";

import { settle } from "./a-fake-gateway.js";
import { aRoom, LOG } from "./a-room-at-hand.js";

describe("a refused seat", () => {
  it("fails a spoken call in plain words, and closes the log it had opened", async () => {
    const { store, gateway, livekit } = aRoom();
    livekit.refuseMicrophone = new Error("NotAllowedError: Permission denied");
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    await settle();

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe(
      "I could not get to your microphone. Check the browser's permission, or write instead.",
    );
    expect(gateway.requests[0]?.aborted).toBe(true);
    expect(livekit.room.connected).toBe(false);
  });

  it("fails a written call with the room's own sentence", async () => {
    const { store, gateway, livekit } = aRoom();
    livekit.refuseConnect = new Error("could not establish signal connection");
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("chat");

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("could not establish signal connection");
    expect(store.state.connection).toBe("ended");
  });
});
