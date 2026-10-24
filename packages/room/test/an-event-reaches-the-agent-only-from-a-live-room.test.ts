// `event()` tells the agent what the visitor did, through the seat; outside a live room it rejects, as `send()` does.

import { describe, expect, it } from "vitest";

import { framed } from "./a-fake-gateway.js";
import { aRoom, LOG, TALKED } from "./a-room-at-hand.js";

describe("an event from the page", () => {
  it("rejects before the call is live, and sends nothing", async () => {
    const { store } = aRoom();

    await expect(store.event("page.viewed", { section: "pricing" })).rejects.toThrow("not in a call");
  });

  it("rides the seat once the call is live, with an empty data when none is given", async () => {
    const { store, gateway, livekit } = aRoom();
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("talk");
    await store.event("page.viewed", { section: "pricing" });
    await store.event("form.opened");

    expect(livekit.room.localParticipant.published).toEqual([
      { data: JSON.stringify({ name: "page.viewed", data: { section: "pricing" } }), topic: "pinecall.event" },
      { data: JSON.stringify({ name: "form.opened", data: {} }), topic: "pinecall.event" },
    ]);
  });

  it("hands the page what the agent shows, through onUi", async () => {
    const shown: unknown[] = [];
    const { store, gateway, livekit } = aRoom({ onUi: (data) => shown.push(data) });
    gateway.answer(LOG, { stream: [framed(TALKED)], then: "hold" });
    await store.start("talk");
    livekit.room.data(JSON.stringify({ type: "html", html: "<p>Tuesday 9:15</p>" }), "pinecall.ui");

    expect(shown).toEqual([{ type: "html", html: "<p>Tuesday 9:15</p>" }]);
  });
});
