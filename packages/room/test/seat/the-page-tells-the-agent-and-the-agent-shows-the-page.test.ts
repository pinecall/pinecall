// A fact about the page rides pinecall.event as {name, data}; what the agent shows on pinecall.ui reaches the page decoded.

import { describe, expect, it } from "vitest";

import { take } from "./a-seat-at-hand.js";

describe("the page and the agent", () => {
  it("sends an event as {name, data} on pinecall.event, reliably", async () => {
    const { seat, livekit } = await take("talk");
    await seat.event("plan.chosen", { plan: "pro" });

    expect(livekit.room.localParticipant.published).toEqual([
      { data: JSON.stringify({ name: "plan.chosen", data: { plan: "pro" } }), topic: "pinecall.event" },
    ]);
  });

  it("hands on what the agent shows, and nothing sent on any other topic", async () => {
    const { livekit, shown } = await take("talk");
    livekit.room.data(JSON.stringify({ type: "choices", options: [{ label: "Tuesday" }] }), "pinecall.ui");
    livekit.room.data(JSON.stringify({ seq: 4 }), "pinecall.log");

    expect(shown).toEqual([{ type: "choices", options: [{ label: "Tuesday" }] }]);
  });

  it("drops bytes that are not JSON rather than failing the page", async () => {
    const { livekit, shown } = await take("talk");
    livekit.room.data("not json", "pinecall.ui");

    expect(shown).toEqual([]);
  });
});
