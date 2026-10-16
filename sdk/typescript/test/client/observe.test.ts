// Log reading: one URL as a page or a stream, with a cursor that survives reconnects.

import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Pinecall, type Observation } from "../../src/client/index.js";
import { FakeLog } from "../../src/client/testing/index.js";

const KEY = "pk_test";
const AGENT = "clinica-norte";
const CALL = "CA_8f4a2c";

let log: FakeLog;
let pc: Pinecall;

beforeEach(async () => {
  log = await FakeLog.start();
  pc = new Pinecall({ url: log.url, apiKey: KEY });
});

afterEach(async () => {
  await log.close();
});

function opens(): void {
  log.append(AGENT, CALL, "call.started", { channel: "phone", direction: "inbound", from: "+34600123456", to: "+34910000001", caller: null, started_at: 1786537500 });
}

function said(text: string): void {
  log.append(AGENT, CALL, "turn.user", {
    speech_id: "sp_1",
    item_id: "item_u1",
    text,
    metrics: { started_speaking_at: 1786537505.93, stopped_speaking_at: 1786537508.56, transcription_delay: 0.18, end_of_turn_delay: 0.41, on_user_turn_completed_delay: 0.003 },
  });
}

/** Collect a stream in the background until aborted. */
function reading(signal: AbortSignal): Observation[] {
  const seen: Observation[] = [];
  void (async () => {
    for await (const observation of pc.observe({ call: CALL }, { signal })) {
      seen.push(observation);
    }
  })();
  return seen;
}

describe("reading a log", () => {
  it("gives the page, what it folds to, and where to go next", async () => {
    opens();
    said("quería una cita");
    const { entries, state, live, next } = await pc.history({ call: CALL });
    expect(entries.map((entry) => entry.seq)).toEqual([1, 2]);
    expect(state.seq).toBe(2);
    expect(state.status).toBe("active");
    expect(state.from).toBe("+34600123456");
    expect(state.turns).toHaveLength(1);
    expect(live).toBe(true);
    expect(next).toBe(2);
  });

  it("starts from the cursor the reader gives it", async () => {
    opens();
    said("quería una cita");
    const { entries, next } = await pc.history({ call: CALL }, { after: 1 });
    expect(entries.map((entry) => entry.seq)).toEqual([2]);
    expect(next).toBe(2);
  });

  it("says the log is closed and nothing follows once the call ended", async () => {
    opens();
    log.append(AGENT, CALL, "call.ended", { reason: "caller_hung_up", ended_by: "caller", ended_at: 1786537600, duration_s: 100 });
    const page = await pc.history({ call: CALL }, { after: 2 });
    expect(page.entries).toEqual([]);
    expect(page.live).toBe(false);
    expect(page.next).toBeNull();
  });

  it("refuses a page that is not { entries, live, next }", async () => {
    // Legacy bare-array response: accepting it would silently drop the cursor.
    const old = createServer((_request, response) => response.writeHead(200, { "content-type": "application/json" }).end("[]"));
    await new Promise<void>((resolve) => old.listen(0, "127.0.0.1", resolve));
    const port = (old.address() as AddressInfo).port;
    const bare = new Pinecall({ url: `http://127.0.0.1:${port}`, apiKey: KEY });
    await expect(bare.history({ call: CALL })).rejects.toThrow(/entries, live, next/);
    await new Promise<void>((resolve) => old.close(() => resolve()));
  });

  it("streams what happens next, folded as it goes", async () => {
    const stop = new AbortController();
    opens();
    const seen = reading(stop.signal);
    await vi.waitFor(() => expect(seen).toHaveLength(1));
    said("quería una cita");
    await vi.waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[1]?.event.type).toBe("turn.user");
    expect(seen[1]?.state.turns).toHaveLength(1);
    stop.abort();
  });

  it("comes back on a fresher cursor and misses nothing", async () => {
    const stop = new AbortController();
    opens();
    const seen = reading(stop.signal);
    await vi.waitFor(() => expect(seen).toHaveLength(1));

    log.cut();
    said("se cortó");
    said("y seguimos");
    await vi.waitFor(() => expect(seen.map((one) => one.entry.seq)).toEqual([1, 2, 3]), { timeout: 5_000 });
    expect(seen[2]?.state.turns).toHaveLength(2);
    stop.abort();
  });

  it("says so when the first read never opens", async () => {
    const nowhere = new Pinecall({ url: "http://127.0.0.1:1", apiKey: KEY });
    await expect(nowhere.observe({ call: CALL }).next()).rejects.toThrow();
  });
});
