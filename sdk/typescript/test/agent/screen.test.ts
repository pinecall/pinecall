// A screen: parts by name with plain props, components called through, and nothing the page cannot read.

import { describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { part, sceneLine, scenesOf, screenOf, showingTool } from "../../src/agent/screen.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { Fragment, jsx } from "../../src/views/jsx-runtime.js";

const Stage = part<{ desk: string }>("stage");
const Slot = part<{ time: string; with?: string }>("slot");

describe("a screen", () => {
  it("is its parts by name, each with what it was given and what it holds", () => {
    const drawn = screenOf(Stage({ desk: "front", children: [Slot({ time: "09:30" }), "or", Slot({ time: "11:00", with: "Dr. Lin" })] }));
    expect(drawn).toEqual([
      {
        part: "stage",
        props: { desk: "front" },
        children: [
          { part: "slot", props: { time: "09:30" }, children: [] },
          "or",
          { part: "slot", props: { time: "11:00", with: "Dr. Lin" }, children: [] },
        ],
      },
    ]);
  });

  it("calls a component that is no part, and draws nothing for what is not there", () => {
    const Two = () => [Slot({ time: "09:30" }), null, false, "  "];
    expect(screenOf(jsx(Fragment, { children: [jsx(Two, {}), undefined] }))).toEqual([{ part: "slot", props: { time: "09:30" }, children: [] }]);
    expect(screenOf(null)).toEqual([]);
  });

  it("leaves behind what is not data", () => {
    const Loose = part<{ time: string; onPick?: () => void; note?: string | undefined }>("loose");
    expect(screenOf(Loose({ time: "09:30", onPick: () => {}, note: undefined }))).toEqual([{ part: "loose", props: { time: "09:30" }, children: [] }]);
  });

  it("refuses a name a page could not map", () => {
    expect(() => part("Agenda")).toThrow(DeclarationRefused);
  });
});

describe("scenes", () => {
  it("are what the class declares, each with what it shows", () => {
    class Desk extends Agent {
      static override scenes = { agenda: "the open times you last read" };
    }
    expect(scenesOf(Desk)).toEqual({ agenda: "the open times you last read" });
    expect(scenesOf(Agent)).toEqual({});
  });

  it("are refused when one is named none, or says nothing", () => {
    class Named extends Agent {
      static override scenes = { none: "nothing" };
    }
    class Silent extends Agent {
      static override scenes = { agenda: " " };
    }
    expect(() => scenesOf(Named)).toThrow(DeclarationRefused);
    expect(() => scenesOf(Silent)).toThrow(DeclarationRefused);
  });

  it("are moved with a quiet tool, and the model is told which one is up and that it goes away", () => {
    const scenes = { agenda: "the open times you last read" };
    expect(showingTool(scenes)).toMatchObject({ name: "show_screen", quiet: true });
    expect(sceneLine(scenes, "agenda")).toContain("shows agenda (the open times you last read)");
    expect(sceneLine(scenes, "agenda")).toContain("goes away when you answer about something else");
    expect(sceneLine({}, null)).toBe("");
  });
});
