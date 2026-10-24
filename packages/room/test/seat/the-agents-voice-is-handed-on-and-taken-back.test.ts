// The element the agent's voice plays in is handed to the room when it arrives, and taken back when it goes.

import { describe, expect, it } from "vitest";

import { FakeTrack } from "../a-fake-livekit.js";
import { take } from "./a-seat-at-hand.js";

describe("the agent's voice", () => {
  it("is the element the sink plays, then nothing once the track is unsubscribed", async () => {
    const { livekit, sink, voices } = await take("talk");
    const voice = new FakeTrack("audio");
    livekit.room.subscribe(voice);

    const playing = sink.playing[0];
    expect(playing).toBeDefined();
    expect(voices).toEqual([playing]);

    livekit.room.unsubscribe(voice);
    expect(voices).toEqual([playing, null]);
  });

  it("is never handed on in a chat, which plays nothing", async () => {
    const { livekit, voices } = await take("chat");
    livekit.room.subscribe(new FakeTrack("audio"));

    expect(voices).toEqual([]);
  });
});
