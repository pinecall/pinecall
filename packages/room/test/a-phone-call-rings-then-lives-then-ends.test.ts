// "Call me": no seat at all. The log says when it rings, when it is answered, and when it is over.

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

describe("a phone call", () => {
  it("rings, then lives, then ends — read from the log alone", async () => {
    const asked: string[] = [];
    const logged: unknown[][] = [];
    const { store, gateway, livekit } = aRoom({
      callMe: async (to) => {
        asked.push(to);
        return { call: CALL };
      },
      log: (...args) => {
        logged.push(args);
        return `/api/log?call=${args[0]}`;
      },
    });
    const phone = aPhoneLog();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.callMe("+34600000001");

    expect(asked).toEqual(["+34600000001"]);
    expect(logged).toEqual([[CALL]]);
    expect(store.state).toMatchObject({ phase: "ringing", mode: "phone", call: CALL });

    gateway.push(frame(phone.dialing()));
    await settle();
    expect(store.state.phase).toBe("ringing");

    gateway.push(frame(phone.started()));
    await settle();
    expect(store.state.phase).toBe("live");

    gateway.push(frame(phone.ended("agent_hung_up")));
    await settle();
    expect(store.state.phase).toBe("ended");
    expect(gateway.requests[0]?.aborted).toBe(false);

    gateway.push(frame(phone.scored()));
    await settle();
    expect(store.state.connection).toBe("ended");
    expect(livekit.loads).toBe(0);
  });

  it("fails with the server's sentence when the call could not be placed", async () => {
    const { store, gateway } = aRoom({
      callMe: async () => {
        throw new Error("the destination has never called this org");
      },
    });
    await store.callMe("+34600000001");

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toBe("the destination has never called this org");
    expect(gateway.requests).toEqual([]);
  });

  it("fails in words when the room was given no callMe", async () => {
    const { store } = aRoom();
    await store.callMe("+34600000001");

    expect(store.state.phase).toBe("failed");
    expect(store.state.error).toContain("no callMe");
  });
});
