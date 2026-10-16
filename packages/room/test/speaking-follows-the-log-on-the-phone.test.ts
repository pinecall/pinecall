// On the phone there is no room in the page: who is speaking is the log's participant.speaking.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frame, settle } from "./a-fake-gateway.js";
import { aPhoneLog } from "./a-phone-call.js";
import { aRoom, CALL, LOG } from "./a-room-at-hand.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("speaking, on the phone", () => {
  it("follows the log's participants: the agent, and the person on the line", async () => {
    const { store, gateway } = aRoom({ callMe: async () => ({ call: CALL }) });
    const phone = aPhoneLog();
    const opening = [phone.dialing(), phone.started(), phone.roomOpened(), phone.joined("agent_1", "agent"), phone.joined("sip_1", "sip")];
    gateway.answer(LOG, { stream: [opening.map((entry) => frame(entry)).join("")], then: "hold" });
    await store.callMe("+34600000001");
    await settle();
    expect(store.state.speaking).toEqual({ agent: false, user: false, level: 0 });

    gateway.push(frame(phone.speaking("agent_1", true)));
    await settle();
    expect(store.state.speaking).toEqual({ agent: true, user: false, level: 0 });

    gateway.push(frame(phone.speaking("agent_1", false)) + frame(phone.speaking("sip_1", true)));
    await settle();
    expect(store.state.speaking).toEqual({ agent: false, user: true, level: 0 });
  });
});
