// A flow: its function run against the journal the gateway keeps, one stretch at a time.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { advance, cancelled, flow, secondsOf, started, StepUnwritten, type Called } from "../../src/runtime/flows.js";

import { KeptApp } from "./kept/gateway.js";

class Reminder extends Agent {}

const slugOf = (agent: unknown): string | undefined => (agent === Reminder ? "brightside-reminder" : undefined);

let kept: KeptApp;

beforeEach(() => {
  kept = new KeptApp();
  vi.stubGlobal("fetch", kept.fetch);
  vi.useFakeTimers({ now: new Date("2026-11-11T10:00:00Z"), toFake: ["Date"] });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("a flow", () => {
  it("is a name and a function", () => {
    expect(flow("remind-visit", async () => {}).name).toBe("remind-visit");
    expect(() => flow("Remind Visit", async () => {})).toThrow(DeclarationRefused);
    expect(() => flow("remind-visit", undefined as never)).toThrow(/a function/);
  });

  it("reads a length of time as a number and its unit", () => {
    expect([secondsOf("45s"), secondsOf("30m"), secondsOf("2h"), secondsOf("1d")]).toEqual([45, 1800, 7200, 86400]);
    expect(() => secondsOf("soon")).toThrow(/no length of time/);
  });

  it("is started once for one key", async () => {
    const remind = flow("remind-visit", async () => {});
    const first = await started(kept.door, remind, "visit-7", { id: 7 });
    const again = await started(kept.door, remind, "visit-7", { id: 7 });
    expect(again.id).toBe(first.id);
    expect(kept.runs.size).toBe(1);
  });
});

describe("a run", () => {
  it("is left at a sleep, and goes on from it when it is woken", async () => {
    const said: string[] = [];
    const remind = flow("remind-visit", async (visit, step) => {
      said.push("before");
      await step.sleepUntil(String(visit["at"]), { before: "24h" });
      said.push("after");
    });
    const run = await started(kept.door, remind, "visit-7", { at: "2026-11-14T09:30:00Z" });

    expect(await advance(kept.door, remind, run, slugOf)).toEqual({ status: "parked" });
    expect(kept.runs.get(run.id)).toMatchObject({ status: "sleeping", steps: [{ seq: 1, kind: "sleep", asked: { until: "2026-11-13T09:30:00.000Z" } }] });

    kept.wake(run.id, null);
    expect(await advance(kept.door, remind, kept.runs.get(run.id)!, slugOf)).toEqual({ status: "done" });
    // Each stretch runs the function from its top: what is outside a step runs again.
    expect(said).toEqual(["before", "before", "after"]);
    expect(kept.runs.get(run.id)!.status).toBe("done");
  });

  it("runs an effect once: on the next stretch it reads what the effect returned", async () => {
    let sent = 0;
    const remind = flow("remind-visit", async (_visit, step) => {
      const receipt = await step.run(() => `sms-${++sent}`);
      await step.sleep("2h");
      return receipt;
    });
    const run = await started(kept.door, remind, "visit-7", {});

    await advance(kept.door, remind, run, slugOf);
    kept.wake(run.id, null);
    await advance(kept.door, remind, kept.runs.get(run.id)!, slugOf);

    expect(sent).toBe(1);
    expect(kept.runs.get(run.id)!.steps[0]).toMatchObject({ kind: "run", result: "sms-1" });
  });

  it("has an agent call a number, and reads how the call ended", async () => {
    const ended: Called[] = [];
    const remind = flow("remind-visit", async (visit, step) => {
      ended.push(await step.call(String(visit["phone"]), Reminder, { instruction: "Remind Ana of her cleaning tomorrow at 9:30." }));
    });
    const run = await started(kept.door, remind, "visit-7", { phone: "+14155550142" });

    expect(await advance(kept.door, remind, run, slugOf)).toEqual({ status: "parked" });
    expect(kept.runs.get(run.id)!.steps[0]!.asked).toEqual({ agent: "brightside-reminder", to: "+14155550142", instruction: "Remind Ana of her cleaning tomorrow at 9:30." });

    kept.wake(run.id, { answered: false, reason: "no_answer", call: "call_1" });
    await advance(kept.door, remind, kept.runs.get(run.id)!, slugOf);
    expect(ended).toEqual([{ answered: false, reason: "no_answer", call: "call_1" }]);
  });

  it("reads a call a guard refused at once, without waiting", async () => {
    kept.refuses = { answered: false, refused: "QuietHours", message: "it is 23:10 there" };
    const ended: Called[] = [];
    const remind = flow("remind-visit", async (_visit, step) => {
      ended.push(await step.call("+14155550142", Reminder));
    });

    expect(await advance(kept.door, remind, await started(kept.door, remind, "visit-7", {}), slugOf)).toEqual({ status: "done" });
    expect(ended).toEqual([{ answered: false, refused: "QuietHours", message: "it is 23:10 there" }]);
  });

  it("waits for an event, and reads null when it gave up", async () => {
    const got: unknown[] = [];
    const remind = flow("remind-visit", async (visit, step) => {
      got.push(await step.waitFor("visit.confirmed", { match: { id: visit["id"] }, within: "2h" }));
    });
    const run = await started(kept.door, remind, "visit-7", { id: 7 });

    await advance(kept.door, remind, run, slugOf);
    expect(kept.runs.get(run.id)!.steps[0]!.asked).toEqual({ event: "visit.confirmed", match: { id: 7 }, until: "2026-11-11T12:00:00.000Z" });

    kept.wake(run.id, null);
    await advance(kept.door, remind, kept.runs.get(run.id)!, slugOf);
    expect(got).toEqual([null]);
  });

  it("sends an event to its app once", async () => {
    const remind = flow("remind-visit", async (_visit, step) => {
      await step.emit("visit.reminded", { id: 7 });
      await step.sleep("1d");
    });
    const run = await started(kept.door, remind, "visit-7", {});

    await advance(kept.door, remind, run, slugOf);
    kept.wake(run.id, null);
    await advance(kept.door, remind, kept.runs.get(run.id)!, slugOf);

    expect(kept.events).toEqual([{ id: 1, name: "visit.reminded", data: { id: 7 } }]);
  });

  it("is failed with what its function threw", async () => {
    const remind = flow("remind-visit", async () => {
      throw new TypeError("no phone on the visit");
    });
    const run = await started(kept.door, remind, "visit-7", {});

    expect(await advance(kept.door, remind, run, slugOf)).toEqual({ status: "failed", error: "TypeError: no phone on the visit" });
    expect(kept.runs.get(run.id)!.status).toBe("failed");
  });

  it("is failed when its function asks for another step than its journal holds", async () => {
    const first = flow("remind-visit", async (_visit, step) => void (await step.sleep("1h")));
    const changed = flow("remind-visit", async (_visit, step) => void (await step.run(() => 1)));
    const run = await started(kept.door, first, "visit-7", {});
    await advance(kept.door, first, run, slugOf);
    kept.wake(run.id, null);

    const ended = await advance(kept.door, changed, kept.runs.get(run.id)!, slugOf);
    expect(ended).toMatchObject({ status: "failed", error: expect.stringContaining("step 1 was a sleep and is now a run") });
  });

  it("is left as it was when the gateway could not be written to", async () => {
    kept.down = "the database is busy";
    const remind = flow("remind-visit", async (_visit, step) => void (await step.sleep("1h")));
    const run = await started(kept.door, remind, "visit-7", {});

    await expect(advance(kept.door, remind, run, slugOf)).rejects.toThrow(StepUnwritten);
    expect(kept.runs.get(run.id)!.status).toBe("ready");
  });

  it("refuses to call as a class the process does not serve", async () => {
    class Stranger extends Agent {}
    const remind = flow("remind-visit", async (_visit, step) => void (await step.call("+14155550142", Stranger)));

    const ended = await advance(kept.door, remind, await started(kept.door, remind, "visit-7", {}), slugOf);
    expect(ended).toMatchObject({ status: "failed", error: expect.stringContaining("Stranger is no agent this process serves") });
  });
});

describe("cancelOn", () => {
  it("cancels the waiting runs the event names, and leaves the rest", async () => {
    const remind = flow("remind-visit", async (_visit, step) => void (await step.sleep("1d"))).cancelOn("visit.cancelled", (gone, visit) => gone["id"] === visit["id"]);
    const seven = await started(kept.door, remind, "visit-7", { id: 7 });
    const eight = await started(kept.door, remind, "visit-8", { id: 8 });
    await advance(kept.door, remind, seven, slugOf);
    await advance(kept.door, remind, eight, slugOf);

    expect(await cancelled(kept.door, remind, "visit.cancelled", { id: 7 })).toBe(1);
    expect([kept.runs.get(seven.id)!.status, kept.runs.get(eight.id)!.status]).toEqual(["cancelled", "sleeping"]);
    expect(await cancelled(kept.door, remind, "visit.moved", { id: 8 })).toBe(0);
  });
});
