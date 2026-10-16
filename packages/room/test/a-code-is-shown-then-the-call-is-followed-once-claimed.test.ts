// "Call it": the page shows a number and a code, asks the gateway until a call claims the code, then follows that call.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frame, settle } from "./a-fake-gateway.js";
import { aPhoneLog } from "./a-phone-call.js";
import { aRoom, ASKED, CALL, CODE, GW } from "./a-room-at-hand.js";

const EVENTS = `${GW}/v1/calls/${CALL}/events?token=log_1`;
const standing = (status: string, call: string | null = null, log_token: string | null = null): string =>
  JSON.stringify({ code: CODE.code, status, expires_at: CODE.expires_at, call, log_token });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a code on the page", () => {
  it("is shown while expecting, asked again through a 5xx, and the claimed call is followed live", async () => {
    const { store, gateway, livekit } = aRoom({ expect: async () => CODE, gateway: GW, log: undefined });
    const phone = aPhoneLog();
    gateway.answer(
      ASKED,
      { status: 200, body: standing("waiting") },
      { status: 503 },
      { status: 200, body: standing("claimed", CALL, "log_1") },
    );
    gateway.answer(EVENTS, { stream: [], then: "hold" });

    const going = store.byPhone();
    await settle();
    expect(store.state).toMatchObject({
      phase: "expecting",
      mode: "phone",
      call: "",
      code: { code: "4821", number: "+34910000000", expiresAt: 1_790_000_600 },
    });

    await vi.advanceTimersByTimeAsync(500);
    await going;
    expect(gateway.requests.map((asked) => asked.url)).toEqual([ASKED, ASKED, ASKED, EVENTS]);
    expect(store.state).toMatchObject({ phase: "live", call: CALL, recording: `${GW}/v1/calls/${CALL}/recording?token=log_1` });

    gateway.push(frame(phone.started()));
    gateway.push(frame(phone.ended("agent_hung_up")));
    await settle();
    expect(store.state.phase).toBe("ended");
    expect(livekit.loads).toBe(0);
  });

  it("fails in words when the room was given no expect", async () => {
    const { store, gateway } = aRoom();
    await store.byPhone();

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toContain("no expect");
    expect(gateway.requests).toEqual([]);
  });
});
