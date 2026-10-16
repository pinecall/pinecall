// A browser that has not let the page make a sound says so; one click answers it, and it is not asked again.

import { describe, expect, it } from "vitest";

import { FakeLivekit } from "../a-fake-livekit.js";
import { aRoom, LOG } from "../a-room-at-hand.js";
import { take } from "./a-seat-at-hand.js";

describe("sound, at the seat", () => {
  it("says whether the browser may play, and starts audio when asked", async () => {
    const livekit = new FakeLivekit();
    livekit.canPlaybackAudio = false;
    const { seat, wantsSound } = await take("talk", livekit);
    expect(seat.canPlaybackAudio()).toBe(false);

    livekit.room.playback(false);
    seat.playSound();
    await Promise.resolve();

    expect(livekit.room.audioStarts).toBe(1);
    expect(wantsSound).toEqual([true, false]);
    expect(seat.canPlaybackAudio()).toBe(true);
  });
});

describe("sound, in the room's state", () => {
  it("is asked for once when the call goes live, and one click answers it", async () => {
    const { store, gateway, livekit, heard } = aRoom();
    livekit.canPlaybackAudio = false;
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    expect(store.state.wantsSound).toBe(true);

    const asked = heard.length;
    livekit.room.playback(false);
    livekit.room.playback(false);
    expect(heard).toHaveLength(asked);

    store.playSound();
    await Promise.resolve();
    livekit.room.playback(true);

    const changes = heard.map((state) => state.wantsSound).filter((wanted, at, all) => at === 0 || wanted !== all[at - 1]);
    expect(changes).toEqual([false, true, false]);
    expect(livekit.room.audioStarts).toBe(1);
  });
});
