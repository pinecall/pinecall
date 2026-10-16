// The call id exists before the room is joined, so the log is asked for first and seq 1 is read.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FRAME_MS } from "../src/store.js";
import { framed, settle } from "./a-fake-gateway.js";
import { aRoom, held, LOG, MINTED } from "./a-room-at-hand.js";
import { BOOKING } from "./a-real-booking.js";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("the log", () => {
  it("is asked for before the room is joined, with the ticket the tokens answered", async () => {
    const seen: unknown[] = [];
    const { store, gateway, journal } = aRoom({
      log: (call, minted) => {
        seen.push(minted);
        return `/api/log?call=${call}`;
      },
    });
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("talk");

    expect(journal).toEqual(["tokens talk", `log ${LOG}`, "connect wss://lk.example ticket"]);
    expect(seen).toEqual([MINTED]);
  });

  it("is read from seq 1 while the seat is still opening", async () => {
    const { store, gateway, livekit } = aRoom();
    const joining = held<void>();
    livekit.stallConnect = joining.promise;
    gateway.answer(LOG, { stream: [framed(BOOKING.slice(0, 1))], then: "hold" });
    const started = store.start("chat");
    await settle();
    await vi.advanceTimersByTimeAsync(FRAME_MS);

    expect(store.state.phase).toBe("opening");
    expect(store.state.call).toBe(MINTED.call);
    expect(store.state.log.seq).toBe(1);
    expect(store.state.entries).toHaveLength(1);
    expect(store.state.connection).toBe("live");

    joining.resolve();
    await started;
    expect(store.state.phase).toBe("live");
  });
});
