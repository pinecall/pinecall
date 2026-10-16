// With a seat, who is speaking is LiveKit's word: the agent is whoever speaks that is not the page.

import { describe, expect, it } from "vitest";

import { aRoom, LOG } from "../a-room-at-hand.js";
import { take } from "./a-seat-at-hand.js";

const AGENT = { identity: "agent_clinica", audioLevel: 0.42 };
const ME = { identity: "web_visitor", audioLevel: 0.2 };

describe("speaking, with a seat", () => {
  it("follows the room's active speakers", async () => {
    const { livekit, speaking } = await take("talk");
    livekit.room.speakers([AGENT]);
    livekit.room.speakers([ME]);
    livekit.room.speakers([AGENT, ME]);
    livekit.room.speakers([]);

    expect(speaking).toEqual([
      { agent: true, user: false, level: 0.42 },
      { agent: false, user: true, level: 0 },
      { agent: true, user: true, level: 0.42 },
      { agent: false, user: false, level: 0 },
    ]);
  });
});

describe("speaking, in the room's state", () => {
  it("is published when it changes, and not again for the same speakers", async () => {
    const { store, gateway, livekit, heard } = aRoom();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");
    const before = heard.length;
    livekit.room.speakers([AGENT]);
    livekit.room.speakers([AGENT]);

    expect(store.state.speaking).toEqual({ agent: true, user: false, level: 0.42 });
    expect(heard).toHaveLength(before + 1);
  });
});
