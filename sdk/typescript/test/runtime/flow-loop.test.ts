// The loop a voice app keeps with the gateway: events heard once, flows started by an entry, runs taken further.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { voiceApp } from "../../src/runtime/app.js";
import { entryHeard, passHeard, workedOnce, type Working } from "../../src/runtime/flow-loop.js";
import { flow } from "../../src/runtime/flows.js";

import { KeptApp } from "./kept/gateway.js";

class FrontDesk extends Agent {}

let kept: KeptApp;
let said: string[];

const workingWith = (app: ReturnType<typeof voiceApp>): Working => ({ app, door: kept.door, slugOf: () => "brightside-front-desk", report: (line) => void said.push(line) });

const logged = (seq: number, name: string, data: Record<string, unknown>) => ({ seq, ts: 0, call: "call_1", agent: "brightside-front-desk", type: "custom", ephemeral: false, data: { name, data } });

beforeEach(() => {
  kept = new KeptApp();
  said = [];
  vi.stubGlobal("fetch", kept.fetch);
});

afterEach(() => vi.unstubAllGlobals());

describe("an entry of a call", () => {
  it("starts the flow app.on gave its name, once however often it is heard", async () => {
    const remind = flow("remind-visit", async (_visit, step) => void (await step.sleep("1d")));
    const working = workingWith(voiceApp("brightside").line("+14155550134", FrontDesk).on("visit.booked", remind));

    await entryHeard(working, logged(12, "visit.booked", { id: 7 }));
    await entryHeard(working, logged(12, "visit.booked", { id: 7 }));

    expect([...kept.runs.values()]).toMatchObject([{ flow: "remind-visit", input: { id: 7 }, status: "ready" }]);
    expect([...kept.keys.keys()]).toEqual(["remind-visit:call_1:12"]);
  });

  it("cancels the waiting runs that asked to be", async () => {
    const remind = flow("remind-visit", async (_visit, step) => void (await step.sleep("1d"))).cancelOn("visit.cancelled", (gone, visit) => gone["id"] === visit["id"]);
    const working = workingWith(voiceApp("brightside").line("+14155550134", FrontDesk).on("visit.booked", remind));
    await entryHeard(working, logged(12, "visit.booked", { id: 7 }));
    await workedOnce(working, 0);

    await entryHeard(working, logged(15, "visit.cancelled", { id: 7 }));

    expect([...kept.runs.values()].map((run) => run.status)).toEqual(["cancelled"]);
  });

  it("starts nothing when it is not kept", async () => {
    const remind = flow("remind-visit", async () => {});
    const working = workingWith(voiceApp("brightside").line("+14155550134", FrontDesk).on("visit.booked", remind));

    await entryHeard(working, { ...logged(12, "visit.booked", {}), ephemeral: true });

    expect(kept.runs.size).toBe(0);
  });
});

describe("the work an app is owed", () => {
  it("hands an event to its handlers and its flows, and says it was heard", async () => {
    const heard: unknown[] = [];
    const follow = flow("follow-up", async () => {});
    const app = voiceApp("brightside").line("+14155550134", FrontDesk);
    app.on("lab.ready", (call, data) => void heard.push([call.id, data])).on("lab.ready", follow);
    kept.send("lab.ready", { patient: "ana" });

    await workedOnce(workingWith(app), 0);

    expect(heard).toEqual([[null, { patient: "ana" }]]);
    expect(kept.heard).toEqual([1]);
    expect([...kept.keys.keys()]).toEqual(["follow-up:event:1"]);
  });

  it("takes each ready run one stretch further, and says which failed", async () => {
    const steps: string[] = [];
    const remind = flow("remind-visit", async (_visit, step) => {
      await step.run(() => steps.push("texted"));
      throw new Error("the clinic is closed");
    });
    const working = workingWith(voiceApp("brightside").line("+14155550134", FrontDesk).on("visit.booked", remind));
    await entryHeard(working, logged(12, "visit.booked", { id: 7 }));

    await workedOnce(working, 0);

    expect(steps).toEqual(["texted"]);
    expect(said).toEqual(["remind-visit run_1 failed: Error: the clinic is closed"]);
  });

  it("leaves a run of a flow the app does not have", async () => {
    const working = workingWith(voiceApp("brightside").line("+14155550134", FrontDesk));
    kept.runs.set("run_9", { id: "run_9", flow: "gone", input: {}, status: "ready", steps: [] });

    await workedOnce(working, 0);

    expect(kept.runs.get("run_9")!.status).toBe("ready");
    expect(said).toEqual(["run run_9 is of the flow gone, which this app does not have"]);
  });
});

describe("a pass heard on a call's log", () => {
  const app = (): ReturnType<typeof voiceApp> => voiceApp("brightside").line("+14155550134", FrontDesk);

  it("has the call take the teammate's model and voice", async () => {
    await passHeard(workingWith(app()), logged(20, "handoff", { from: "brightside-front-desk", to: "brightside-billing" }));

    expect(kept.asked).toEqual(['POST /v1/calls/call_1/stages {"agent":"brightside-billing"}']);
    expect(said).toEqual([]);
  });

  it("says nothing of a written call, which no worker runs, and says a refusal", async () => {
    kept.staged = 404;
    await passHeard(workingWith(app()), logged(20, "handoff", { to: "brightside-billing" }));
    expect(said).toEqual([]);

    kept.staged = 403;
    await passHeard(workingWith(app()), logged(21, "handoff", { to: "brightside-billing" }));
    expect(said).toEqual(["call_1 keeps the voice it had after its pass to brightside-billing: the gateway answered 403"]);
  });

  it("asks nothing for any other line", async () => {
    await passHeard(workingWith(app()), logged(20, "visit.booked", { to: "brightside-billing" }));
    expect(kept.asked).toEqual([]);
  });
});

describe("app.on with a flow", () => {
  it("refuses two flows of one name", () => {
    const app = voiceApp("brightside").on("visit.booked", flow("remind-visit", async () => {}));
    expect(() => app.on("visit.moved", flow("remind-visit", async () => {}))).toThrow(/two flows of brightside are named remind-visit/);
  });
});
