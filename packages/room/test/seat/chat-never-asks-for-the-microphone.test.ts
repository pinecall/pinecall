// A written conversation joins the room too — typed lines ride it — but never touches a microphone.

import { describe, expect, it } from "vitest";

import { FakeTrack } from "../a-fake-livekit.js";
import { take } from "./a-seat-at-hand.js";

describe("a chat seat", () => {
  it("joins the room and never asks for the microphone", async () => {
    const { livekit } = await take("chat");

    expect(livekit.room.connected).toBe(true);
    expect(livekit.room.localParticipant.microphone).toEqual([]);
  });

  it("sends a typed line on lk.chat", async () => {
    const { seat, livekit } = await take("chat");
    await seat.send("Thursday would be great");

    expect(livekit.room.localParticipant.sent).toEqual([{ text: "Thursday would be great", topic: "lk.chat" }]);
  });

  it("never plays the agent's voice", async () => {
    const { livekit, sink } = await take("chat");
    const voice = new FakeTrack("audio");
    livekit.room.subscribe(voice);

    expect(voice.attached).toEqual([]);
    expect(sink.playing).toEqual([]);
  });
});
