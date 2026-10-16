// A sealed call whose cursor is at the end is answered 204: the follow ends, and nobody asks again.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeGateway, framed, settle } from "./a-fake-gateway.js";
import { follow } from "./a-log-followed.js";
import { aRoom, LOG } from "./a-room-at-hand.js";
import { BOOKING } from "./a-real-booking.js";

const URL = "/api/log?call=call_1";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("a sealed call", () => {
  it("answers nothing more: the follow ends at the 204", async () => {
    const gateway = new FakeGateway().answer(URL, { status: 204 });
    const followed = follow(gateway, URL);
    await settle();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(followed.endings).toEqual([{ kind: "sealed" }]);
    expect(followed.connections).toEqual(["connecting"]);
    expect(gateway.requests).toHaveLength(1);
  });

  it("answers 204 to a resume at its end, after the stream dropped", async () => {
    const before = BOOKING.slice(0, -1);
    const gateway = new FakeGateway().answer(URL, { stream: [framed(before)], then: "end" }, { status: 204 });
    const followed = follow(gateway, URL);
    await settle();
    await vi.advanceTimersByTimeAsync(500);
    await settle();

    expect(followed.endings).toEqual([{ kind: "sealed" }]);
    expect(gateway.requests[1]?.lastEventId).toBe(String(before.at(-1)?.seq));
  });

  it("is told apart from a refusal, which names its status", async () => {
    const gateway = new FakeGateway().answer(URL, { status: 401, body: '{"detail":"no"}' });
    const followed = follow(gateway, URL);
    await settle();

    expect(followed.endings).toEqual([{ kind: "refused", status: 401 }]);
  });
});

describe("a sealed call, in a room", () => {
  it("ends the connection and leaves a room's phase to its seat", async () => {
    const { store, gateway } = aRoom();
    gateway.answer(LOG, { status: 204 });
    await store.start("chat");
    await settle();

    expect(store.state.connection).toBe("ended");
    expect(store.state.phase).toBe("live");
  });
});
