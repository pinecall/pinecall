// A burst of entries is one paint; a phase is heard at once; every state heard is a new object.

import { type Entry } from "../src/wire/envelope.js";
import { initialState } from "../src/wire/reduce.js";
import { type State } from "../src/wire/state.js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LogFold } from "../src/log/fold.js";
import { SseParser } from "../src/log/sse.js";
import { cell, FRAME_MS, type Cell } from "../src/store.js";
import { framed, settle } from "./a-fake-gateway.js";
import { aRoom, LOG } from "./a-room-at-hand.js";
import { BOOKING } from "./a-real-booking.js";

interface Drawn {
  phase: string;
  log: State;
  entries: Entry[];
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

/** A store fed the whole booking in one chunk, the way the room feeds it. */
function fed(): { store: Cell<Drawn>; heard: Drawn[]; fold: LogFold } {
  const store = cell<Drawn>({ phase: "idle", log: initialState(), entries: [] });
  const heard: Drawn[] = [];
  store.subscribe((state) => heard.push(state));
  const fold = new LogFold(() => {});
  for (const message of new SseParser().feed(framed(BOOKING))) {
    if (fold.take(message) !== null) store.paint(() => fold.snapshot());
  }
  return { store, heard, fold };
}

describe("the store", () => {
  it("paints 81 entries that arrived in one chunk once, within a frame", async () => {
    const { heard } = fed();
    expect(heard).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(FRAME_MS);

    expect(heard).toHaveLength(1);
    expect(heard[0]?.entries).toHaveLength(BOOKING.length);
    expect(heard[0]?.log.status).toBe("ended");
  });

  it("publishes a phase at once, and a paint that was waiting rides along", () => {
    const { store, heard } = fed();
    store.publish({ phase: "live" });

    expect(heard).toHaveLength(1);
    expect(heard[0]?.phase).toBe("live");
    expect(heard[0]?.entries).toHaveLength(BOOKING.length);
  });

  it("hands out a new object each time, and never changes one it handed out", async () => {
    const { store, heard, fold } = fed();
    await vi.advanceTimersByTimeAsync(FRAME_MS);
    const painted = heard[0];
    store.publish({ phase: "ended" });

    expect(heard[1]).not.toBe(painted);
    expect(painted?.phase).toBe("idle");
    expect(painted?.log).not.toBe(fold.now);
  });

  it("is not heard for a patch that changes nothing", () => {
    const { store, heard } = fed();
    store.publish({});
    store.publish({ phase: store.state.phase === "idle" ? "live" : "idle" });
    const before = heard.length;
    store.publish({ phase: store.state.phase });

    expect(heard).toHaveLength(before);
  });

  it("stops a watcher hearing once it unsubscribes", () => {
    const store = cell({ phase: "idle" });
    const heard: string[] = [];
    const stop = store.subscribe((state) => heard.push(state.phase));
    store.publish({ phase: "opening" });
    stop();
    store.publish({ phase: "live" });

    expect(heard).toEqual(["opening"]);
  });

  it("leaves nothing running once closed", async () => {
    const { store, heard } = fed();
    store.close();
    await vi.advanceTimersByTimeAsync(FRAME_MS * 10);
    store.publish({ phase: "live" });

    expect(heard).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("the room's store", () => {
  it("paints 81 entries in one chunk at most twice in a frame, with its phase heard at once", async () => {
    const { store, gateway, heard } = aRoom();
    gateway.answer(LOG, { stream: [], then: "hold" });
    await store.start("chat");
    const before = heard.length;
    gateway.push(framed(BOOKING));
    await settle();
    await vi.advanceTimersByTimeAsync(FRAME_MS);

    const painted = heard.slice(before).filter((state, at, all) => state.log !== (all[at - 1] ?? heard[before - 1])?.log);
    expect(painted.length).toBeGreaterThan(0);
    expect(painted.length).toBeLessThanOrEqual(2);
    expect(store.state.phase).toBe("ended");
    expect(store.state.entries).toHaveLength(BOOKING.length);
  });
});
