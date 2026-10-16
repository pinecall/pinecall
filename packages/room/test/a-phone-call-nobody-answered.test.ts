// A call nobody picked up never goes live: from ringing, it ends.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frame, settle } from "./a-fake-gateway.js";
import { aPhoneLog } from "./a-phone-call.js";
import { aRoom, CALL, LOG } from "./a-room-at-hand.js";

const callMe = async (): Promise<{ call: string }> => ({ call: CALL });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a phone call nobody answered", () => {
  it("ends from ringing when the log says no_answer", async () => {
    const { store, gateway, heard } = aRoom({ callMe });
    const phone = aPhoneLog();
    gateway.answer(LOG, { stream: [frame(phone.dialing()) + frame(phone.ended("no_answer"))], then: "hold" });
    await store.callMe("+34600000001");
    await settle();

    expect(store.state.phase).toBe("ended");
    expect(store.state.log.end_reason).toBe("no_answer");
    expect(heard.map((state) => state.phase)).not.toContain("live");
  });

  it("ends from ringing when the relay answers that the call is sealed", async () => {
    const { store, gateway } = aRoom({ callMe });
    gateway.answer(LOG, { status: 204 });
    await store.callMe("+34600000001");
    await settle();

    expect(store.state.phase).toBe("ended");
    expect(store.state.connection).toBe("ended");
  });
});
