// One bundle, two consoles: production at the root of the gateway's one name, the sandbox under
// `/sandbox`, the world read off the path (lib/mode.ts). Production's console runs the org; the
// sandbox's is the workshop, with its own tokens and provider keys. Which screens each has is ONE
// table (lib/mode.ts), and this pins it.

import { describe, expect, it } from "vitest";

import { headersFor } from "@pinecall/core/api";
import { AGENT_SCREENS, BOX_SCREENS, ORG_SCREENS, has, rowOf, rowsOf, screenAt, screensOf, tabsOf } from "../src/lib/mode.js";

const names = (table: typeof ORG_SCREENS, world: "production" | "sandbox"): string[] =>
  screensOf(table, world).map((screen) => screen.name);

const tabs = (table: typeof ORG_SCREENS, key: string, world: "production" | "sandbox"): string[] => {
  const row = table.find((screen) => screen.key === key);
  return row === undefined ? [] : tabsOf(table, row, world).map((screen) => screen.name);
};

// One word, one place. What is looked at — Overview, Calls, Quality — is three rows whoever is in
// view; with every agent in view Agents lists them, and what runs the org is the workspace at the
// sidebar's foot. Nothing that is ONE agent's — its callers, its goldens, its lexicon — is the org's.
const looked = (table: typeof ORG_SCREENS, world: "production" | "sandbox"): string[] =>
  rowsOf(table, world).filter((screen) => screen.group === undefined).map((screen) => screen.name);
const harness = (table: typeof ORG_SCREENS, world: "production" | "sandbox"): string[] =>
  rowsOf(table, world).filter((screen) => screen.group === "harness").map((screen) => screen.name);
const workspace = (world: "production" | "sandbox"): string[] =>
  rowsOf(ORG_SCREENS, world).filter((screen) => screen.group === "workspace").map((screen) => screen.name);

describe("production's console", () => {
  it("looks at the org from four rows: its overview, every call, how they are judged, and its agents", () => {
    expect(looked(ORG_SCREENS, "production")).toEqual(["Overview", "Calls", "Quality", "Observability", "Agents", "Knowledge"]);
  });

  it("lists under Agents what runs them: the apps the box hosts and the secrets they start with", () => {
    expect(tabs(ORG_SCREENS, "agents", "production")).toEqual(["Agents", "Apps", "Secrets"]);
    expect(tabs(ORG_SCREENS, "knowledge", "production")).toEqual(["Docs", "Memory"]);
    expect(screenAt("/docs")?.key).toBe("org-docs");
  });

  it("runs the org from the workspace: its numbers, its people, its bill, its data and its settings", () => {
    expect(workspace("production")).toEqual(["Numbers", "Team", "Usage", "Privacy", "Settings"]);
    expect(tabs(ORG_SCREENS, "org-settings", "production")).toEqual(["API keys", "Providers", "Telemetry", "Alerts"]);
  });

  it("keeps the org's data under Privacy, a tab each: its rules, consent, export and erasure, who read what", () => {
    expect(tabs(ORG_SCREENS, "org-data", "production")).toEqual(["Rules", "Consent", "Export & erase", "Access log"]);
    expect(screenAt("/data/erasures")?.key).toBe("data-erasures");
  });

  it("keeps what the bell tells a person as theirs, never a row of the org's", () => {
    expect(rowsOf(ORG_SCREENS, "production").filter((screen) => screen.group === "yours").map((screen) => screen.name)).toEqual(["Notifications"]);
    expect(workspace("production")).not.toContain("Notifications");
  });

  it("puts the harness in its own section: simulations, the callers they play, the calls that broke, the judges and the monitors", () => {
    expect(harness(ORG_SCREENS, "production")).toEqual(["Simulations", "Personas", "Cases", "Judges", "Monitors"]);
    expect(tabs(ORG_SCREENS, "quality", "production")).toEqual(["Quality"]);
    expect(screenAt("/judges")?.key).toBe("judges");
    expect(screenAt("/monitors")?.key).toBe("monitors");
    expect(screenAt("/simulations")?.key).toBe("simulations");
  });

  it("reads every call on one screen, with no tab of its own: the table is Calls' own view", () => {
    expect(tabs(ORG_SCREENS, "calls", "production")).toEqual(["Calls"]);
    expect(screenAt("/calls/call_9f")?.key).toBe("calls");
  });

  it("has no org-wide Lexicon: the words are one agent's", () => {
    expect(names(ORG_SCREENS, "production")).not.toContain("Lexicon");
  });

  it("talks and chats with what is deployed, and has no Dev chat: that one mounts the class in a developer's own directory", () => {
    expect(has(AGENT_SCREENS, "talk", "production")).toBe(true);
    expect(has(AGENT_SCREENS, "devchat", "production")).toBe(false);
  });
});

// The box is run from the page that shows production, by a person the box made an operator. The
// rows are marked, so nobody else is drawn one — and the sandbox's console has none at all.
describe("the box's screens", () => {
  it("are an operator's, on production's console", () => {
    expect(screensOf(BOX_SCREENS, "production", true).map((screen) => screen.name)).toEqual(["Organizations", "Fleet", "Carriers", "Routes", "Traceback", "Box usage", "Box settings"]);
    expect(BOX_SCREENS.every((screen) => screen.operator === true && screen.under === undefined && screen.path.startsWith("box/"))).toBe(true);
  });

  it("are drawn for nobody else", () => {
    expect(screensOf(BOX_SCREENS, "production")).toEqual([]);
    expect(screensOf(BOX_SCREENS, "production", false)).toEqual([]);
    expect(screensOf(BOX_SCREENS, "sandbox", true)).toEqual([]);
  });

  it("leave an org's own screens as they were, operator or not", () => {
    expect(screensOf(ORG_SCREENS, "production", true)).toEqual(screensOf(ORG_SCREENS, "production"));
  });
});

describe("the sandbox's console", () => {
  it("is the workshop: the same rows looked at, no numbers, people or bill, and its own API keys, provider keys and notices", () => {
    expect(looked(ORG_SCREENS, "sandbox")).toEqual(["Overview", "Calls", "Quality", "Observability", "Agents", "Knowledge"]);
    expect(workspace("sandbox")).toEqual(["Privacy", "Settings"]);
    expect(tabs(ORG_SCREENS, "org-settings", "sandbox")).toEqual(["API keys", "Providers", "Telemetry", "Alerts", "Phone testing"]);
  });

  it("has every screen of an agent, Dev chat among them", () => {
    expect(names(AGENT_SCREENS, "sandbox")).toEqual(["Overview", "Calls", "Quality", "Playground", "Dev chat", "Test", "Goldens", "Knowledge", "Docs", "Memory", "Configure", "Pipeline", "Lexicon", "Widget", "Simulations", "Personas", "Cases", "Judges", "Monitors"]);
  });
});

// One agent in view is the same three rows the org has, with only its calls, and what builds it.
describe("an agent's screens", () => {
  it("are the org's three rows looked at, then what builds the agent, and never a word the workspace says", () => {
    expect(looked(AGENT_SCREENS, "production")).toEqual(["Overview", "Calls", "Quality"]);
    expect(rowsOf(AGENT_SCREENS, "production").filter((screen) => screen.group === "build").map((screen) => screen.name)).toEqual(["Playground", "Test", "Knowledge", "Configure", "Pipeline", "Lexicon", "Widget"]);
    const words = rowsOf(AGENT_SCREENS, "production").map((screen) => screen.name);
    expect(words.filter((word) => workspace("production").includes(word))).toEqual([]);
  });

  it("read its calls where the org reads them, under its own prefix", () => {
    expect(tabs(AGENT_SCREENS, "calls", "production")).toEqual(["Calls"]);
    expect(screenAt("/a/clinica-norte/calls/call_9f")?.key).toBe("calls");
  });

  it("keep what it runs on a row each: its settings, the pipeline, its lexicon and the widget", () => {
    expect(tabs(AGENT_SCREENS, "settings", "production")).toEqual(["Configure"]);
    expect(screenAt("/a/clinica-norte/lexicon")?.key).toBe("lexicon");
    expect(screenAt("/lexicon")).toBeUndefined();
  });

  it("keeps under Test what comes before a change ships: its overview and its goldens", () => {
    expect(tabs(AGENT_SCREENS, "test", "production")).toEqual(["Test", "Goldens"]);
    expect(tabs(AGENT_SCREENS, "quality", "production")).toEqual(["Quality"]);
  });

  it("has the org's harness rows, its own: simulations, its callers, its cases, its judges and its monitors", () => {
    expect(harness(AGENT_SCREENS, "production")).toEqual(harness(ORG_SCREENS, "production"));
    expect(screenAt("/a/clinica-norte/simulations/call_9f")?.key).toBe("simulations");
  });

  it("read a path in the agent's table, so its Configure is not the org's Settings", () => {
    expect(screenAt("/a/clinica-norte/configure")?.key).toBe("settings");
    expect(screenAt("/settings")?.key).toBe("org-settings");
    expect(screenAt("/a/clinica-norte/personas/el-que-cancela")?.key).toBe("personas");
    const goldens = screenAt("/a/clinica-norte/goldens");
    expect(goldens === undefined ? undefined : rowOf(AGENT_SCREENS, goldens).name).toBe("Test");
  });
});

// Both consoles ride one key of that browser's, and every request names the world of the page it
// came from — the path's — so the gateway serves the world the page is looking at and refuses a
// request that believes it is talking to the other (the runtime's auth/world.py).
describe("either console", () => {
  it("names its world and its key on every request", () => {
    expect(headersFor({ base: "/", key: "pk_1", world: "sandbox" })).toEqual({ authorization: "Bearer pk_1", "pinecall-env": "sandbox" });
    expect(headersFor({ base: "/", key: "pk_1", world: "production" })).toEqual({ authorization: "Bearer pk_1", "pinecall-env": "production" });
  });

  it("names the colleague's corner an admin opened, in the sandbox", () => {
    expect(headersFor({ base: "/", key: "pk_1", world: "sandbox", corner: "mem_2" })).toEqual({
      authorization: "Bearer pk_1",
      "pinecall-env": "sandbox",
      "pinecall-corner": "mem_2",
    });
  });
});
