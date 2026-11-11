// A screen follows the conversation: a tool that shows a scene puts it up, a turn about something else takes it away, the model keeps it with show_screen.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";

import { describe as describe_ } from "../../src/agent/docstrings.js";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { mount } from "../../src/runtime/connect.js";

import Scenes from "./asks/scenes.js";

const KEY = "pk_test";
const CALL = "CA_1";
const SLUG = "scenes";
const FILE = fileURLToPath(new URL("./asks/scenes.ts", import.meta.url));
describe_(Scenes, readFileSync(FILE, "utf8"), FILE);

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mount(Scenes, { pc, slug: SLUG });
  await pc.connect();
  await settled();
  gateway.emit(SLUG, CALL, "call.started", { channel: "web", direction: "inbound", from: "", to: "", caller: null, started_at: Date.now() / 1000 });
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

async function settled(): Promise<void> {
  for (let turn = 0; turn < 30; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function shown(): string {
  const screen = (gateway.commandsOf("state.set").at(-1)?.data["state"] as { screen: { part: string }[] }).screen;
  return screen[0]!.part;
}

async function said(type: "turn.user" | "turn.agent", text: string, speech: string): Promise<void> {
  gateway.emit(SLUG, CALL, type, { speech_id: speech, text, ...(type === "turn.agent" ? { interrupted: false } : {}) });
  await settled();
}

async function called(name: string, args: Record<string, unknown>, id: string): Promise<unknown> {
  gateway.emit(SLUG, CALL, "tool.call", { call_id: id, name, arguments: args });
  await settled();
  return gateway.commandsOf("tool.result").find((result) => result.data["callId"] === id || result.data["call_id"] === id)?.data["output"];
}

it("offers the model a quiet tool to move the screen, with the class's scenes", () => {
  const declared = (gateway.commandsOf("agent.configure")[0]?.data["config"] as { tools: { name: string; quiet?: boolean; parameters: unknown }[] }).tools;
  const showing = declared.find((spec) => spec.name === "show_screen");
  expect(showing?.quiet).toBe(true);
  expect(JSON.stringify(showing?.parameters)).toContain('"enum":["agenda","none"]');
});

it("puts up the scene a tool shows, and takes it away when the caller's next turn is about something else", async () => {
  await said("turn.user", "What do you have on Tuesday?", "s1");
  await called("free", {}, "t1");
  await said("turn.agent", "I have 9:30 or 11.", "s1");
  expect(shown()).toBe("times");

  await said("turn.user", "Who are you?", "s2");
  await said("turn.agent", "I am the front desk.", "s2");
  expect(shown()).toBe("hello");
});

it("keeps the scene through a turn in which the model kept it, and takes it away when told none", async () => {
  await said("turn.user", "What do you have on Tuesday?", "s1");
  await called("free", {}, "t1");
  await said("turn.agent", "I have 9:30 or 11.", "s1");

  await said("turn.user", "The 11, is that with Dr. Lin?", "s2");
  expect(await called("show_screen", { scene: "agenda" }, "t2")).toBe("shown");
  await said("turn.agent", "11 is with Dr. Okafor.", "s2");
  expect(shown()).toBe("times");

  await called("show_screen", { scene: "none" }, "t3");
  expect(shown()).toBe("hello");
});

it("leaves the scene where it is after a turn the caller did not open", async () => {
  await said("turn.user", "What do you have on Tuesday?", "s1");
  await called("free", {}, "t1");
  await said("turn.agent", "I have 9:30 or 11.", "s1");
  await said("turn.agent", "The caller tapped 11 on their screen: is that the one?", "s2");
  expect(shown()).toBe("times");
});
