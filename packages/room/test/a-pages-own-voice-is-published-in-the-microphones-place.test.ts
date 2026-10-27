// A page that brings a voice of its own (`voice`) has it published as the microphone in a spoken call, and the microphone is never asked for.

import { describe, expect, it } from "vitest";

import { settle } from "./a-fake-gateway.js";
import { aRoom, LOG } from "./a-room-at-hand.js";

describe("a page's own voice", () => {
  it("is published as the microphone, which is left alone", async () => {
    const track = { kind: "audio", id: "the page's own" } as unknown as MediaStreamTrack;
    const { store, gateway, livekit } = aRoom({ voice: async () => track });
    livekit.refuseMicrophone = new Error("never asked for");
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    await settle();

    expect(store.state.phase).toBe("live");
    expect(livekit.room.localParticipant.voices).toEqual([{ track, source: "microphone" }]);
    expect(livekit.room.localParticipant.microphone).toEqual([]);
  });

  it("is not published in a written call", async () => {
    const { store, gateway, livekit } = aRoom({ voice: () => ({}) as unknown as MediaStreamTrack });
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("chat");
    await settle();

    expect(livekit.room.localParticipant.voices).toEqual([]);
  });
});
