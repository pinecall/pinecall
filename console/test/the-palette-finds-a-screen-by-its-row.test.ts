// ⌘K lists every screen with the icon of the row it sits under, says the row a tab is of, and
// finds a hit by any word of it — a tab by its row's name, a call by who was on it or how it ended.

import { describe, expect, it } from "vitest";

import type { SessionLine } from "@pinecall/core/wire/rest";
import { agentHits, callHits, matching, saidBy, screenHits, type Hit } from "../src/shell/palette-hits.js";

const screens = screenHits({ scopes: null, billed: false, operator: false, agent: "", inView: false });
const screen = (label: string): Hit & { kind: "screen" } => {
  const hit = screens.find((one) => one.kind === "screen" && one.label === label);
  if (hit === undefined || hit.kind !== "screen") throw new Error(`no screen called ${label}`);
  return hit;
};

const aCall: SessionLine = {
  call: "call_7f3a9b2c",
  agent: "clinica-norte",
  live: false,
  last_seq: 12,
  status: "ended",
  channel: "phone",
  direction: "inbound",
  from: "+34600111222",
  to: "+34911222333",
  caller: { name: "María López" } as SessionLine["caller"],
  started_at: 1_762_500_000,
  ended_at: 1_762_500_090,
  end_reason: "caller_hung_up" as SessionLine["end_reason"],
  outcome: "Booked a visit for Tuesday",
  cost: null,
};

describe("the palette", () => {
  it("draws a row with its own icon, and a tab with its row's, naming the row", () => {
    expect(screen("Overview")).toMatchObject({ icon: "grid", where: "", to: "/" });
    expect(screen("Providers")).toMatchObject({ icon: "sliders", where: "Settings", to: "/providers" });
    expect(screen("Secrets")).toMatchObject({ icon: "bot", where: "Agents" });
  });

  it("puts the agent in view first, so 'calls' lands on its calls, and says the org's row is every agent's", () => {
    expect(screens.some((hit) => hit.group === "clinica-norte")).toBe(false);
    const inView = screenHits({ scopes: null, billed: false, operator: false, agent: "clinica-norte", inView: true });
    const calls = matching(inView, "calls").filter((hit) => hit.kind === "screen");
    expect(calls.map((hit) => hit.to)).toEqual(["/a/clinica-norte/calls", "/calls"]);
    expect(calls.map((hit) => hit.kind === "screen" && hit.where)).toEqual(["", "every agent"]);
    expect(inView.filter((hit) => hit.group === "clinica-norte").map((hit) => hit.to)).toContain("/a/clinica-norte/configure");
  });

  it("lists the first agent held after the org's screens when every agent is in view", () => {
    const wayIn = screenHits({ scopes: null, billed: false, operator: false, agent: "clinica-norte", inView: false });
    expect(wayIn[0]).toMatchObject({ group: "Screens", to: "/" });
    expect(wayIn.at(-1)).toMatchObject({ group: "clinica-norte" });
    expect(matching(wayIn, "calls")[0]).toMatchObject({ to: "/calls", where: "" });
  });

  it("opens a call under the agent in view, so it stays in view", () => {
    expect(callHits([aCall], "Calls", "/a/clinica-norte/calls")[0]?.to).toBe("/a/clinica-norte/calls/call_7f3a9b2c");
  });

  it("finds a tab by the row it sits under, every word in any order", () => {
    expect(matching(screens, "settings prov").map((hit) => hit.kind === "screen" && hit.label)).toEqual(["Providers"]);
    expect(matching(screens, "")).toHaveLength(screens.length);
  });

  it("finds a call by who was on it, its number, its agent or what came of it", () => {
    const [hit] = callHits([aCall], "Calls");
    expect(hit?.to).toBe("/calls/call_7f3a9b2c");
    expect(saidBy(hit as Hit)).toContain("María López");
    for (const words of ["maría", "600111", "clinica", "booked"]) expect(matching([hit as Hit], words)).toHaveLength(1);
    expect(matching([hit as Hit], "cancelled")).toHaveLength(0);
  });

  it("finds an agent by its slug or a channel it answers on", () => {
    const held = agentHits([{ slug: "clinica-norte", channels: ["phone", "web"], kind: "studio" }]);
    expect(matching(held, "web").map((hit) => hit.to)).toEqual(["/a/clinica-norte/overview"]);
    expect(matching(held, "whatsapp")).toHaveLength(0);
  });
});
