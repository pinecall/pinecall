// A spoken seat turns the microphone on once connected, and plays the agent's audio until it goes.

import { describe, expect, it } from "vitest";

import { hiddenSink } from "../../src/seat/sink.js";
import { FakeTrack } from "../a-fake-livekit.js";
import { take } from "./a-seat-at-hand.js";

describe("a talk seat", () => {
  it("connects, then turns the microphone on", async () => {
    const { livekit } = await take("talk");

    expect(livekit.journal).toEqual(["connect wss://lk.example ticket"]);
    expect(livekit.room.localParticipant.microphone).toEqual([true]);
  });

  it("hears the agent: an audio track is played, and stops when it is unsubscribed", async () => {
    const { livekit, sink } = await take("talk");
    const voice = new FakeTrack("audio");
    livekit.room.subscribe(voice);
    expect(sink.playing).toEqual(voice.attached);
    expect(sink.playing).toHaveLength(1);

    livekit.room.unsubscribe(voice);
    expect(sink.playing).toEqual([]);
  });

  it("plays audio only: a video track is not attached", async () => {
    const { livekit, sink } = await take("talk");
    livekit.room.subscribe(new FakeTrack("video"));

    expect(sink.playing).toEqual([]);
  });

  it("empties the sink when it leaves", async () => {
    const { seat, livekit, sink } = await take("talk");
    livekit.room.subscribe(new FakeTrack("audio"));
    await seat.leave();

    expect(sink.playing).toEqual([]);
    expect(livekit.room.connected).toBe(false);
  });
});

describe("the hidden sink", () => {
  it("puts the voice in a hidden box at the end of the page, made when the first voice arrives", () => {
    const sink = hiddenSink();
    expect(document.body.children).toHaveLength(0);
    const voice = document.createElement("audio");
    sink.add(voice);

    const box = document.body.lastElementChild;
    expect(box?.contains(voice)).toBe(true);
    expect(box instanceof HTMLElement && box.style.display).toBe("none");

    sink.close();
    expect(document.body.children).toHaveLength(0);
  });
});
