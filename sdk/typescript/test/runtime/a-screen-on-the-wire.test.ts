// A screen, on the wire: it travels in the call's state as a public field, follows the state, and its page may give a task.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";

import { describe as describe_ } from "../../src/agent/docstrings.js";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { mount } from "../../src/runtime/connect.js";

import Books from "./asks/books.js";
import Draws from "./asks/draws.js";

const KEY = "pk_test";
const CALL = "CA_1";
const SLUG = "draws";
const FILE = fileURLToPath(new URL("./asks/draws.ts", import.meta.url));
describe_(Draws, readFileSync(FILE, "utf8"), FILE);

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mount(Draws, { pc, slug: SLUG });
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

function commands(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

function screen(): unknown {
  return (commands("state.set").at(-1)?.["state"] as Record<string, unknown>)["screen"];
}

async function called(name: string, args: Record<string, unknown>, id: string): Promise<void> {
  gateway.emit(SLUG, CALL, "tool.call", { call_id: id, name, arguments: args });
  await settled();
}

async function fromThePage(name: string, data: Record<string, unknown>): Promise<void> {
  gateway.emit(SLUG, CALL, "event.received", { name, data, source: "participant", identity: "visitor" });
  await settled();
}

it("declares its screen public, and the event a page gives a task with", () => {
  const config = commands("agent.configure")[0]?.["config"] as { state_fields: unknown[]; events: unknown[] };
  expect(config.state_fields).toContainEqual({ name: "screen", visibility: "public" });
  expect(config.events).toContainEqual({ name: "task.give", from: ["participant"] });
});

it("sends no screen while the class draws nothing", () => {
  expect(commands("state.set").every((sent) => !("screen" in (sent["state"] as object)))).toBe(true);
});

it("sends the screen in the state when a tool moved it, and again when the page did", async () => {
  await called("free", {}, "t1");
  expect(screen()).toEqual([{ part: "times", props: { times: ["09:30", "11:00"], picked: "" }, children: [] }]);
  await fromThePage("time.picked", { time: "11:00" });
  expect(screen()).toEqual([{ part: "times", props: { times: ["09:30", "11:00"], picked: "11:00" }, children: [] }]);
});

it("draws what a tool asks for, and finishes the tool on what the page gives", async () => {
  await called("book", { time: "09:30" }, "t1");
  expect(screen()).toEqual([{ part: "form", props: { task: "email" }, children: [] }]);
  await fromThePage("task.give", { task: "email", given: { email: "Ana@Example.com" } });
  expect(screen()).toEqual([{ part: "booked", props: { time: "", sentTo: "ana@example.com" }, children: [] }]);
  const told = String(commands("agent.reply").at(-1)?.["instructions"]);
  expect(told).toContain("book is done with this result");
  expect(told).toContain("ana@example.com");
});

it("says on the form why what the page gave was refused, and tells the model nothing", async () => {
  await called("book", { time: "09:30" }, "t1");
  await fromThePage("task.give", { task: "email", given: { email: "ana at example" } });
  expect(JSON.stringify(screen())).toContain("is not an email address");
  expect(commands("agent.reply")).toEqual([]);
});

it("puts what the agent shows over the screen, at once", async () => {
  await called("announce", { text: "Closed on Friday" }, "t1");
  expect(screen()).toEqual([{ part: "banner", props: { text: "Closed on Friday" }, children: [] }]);
});

it("declares neither for a class that draws no screen", async () => {
  mount(Books, { pc, slug: "books" });
  await settled();
  const config = commands("agent.configure").at(-1)?.["config"] as { state_fields?: unknown; events?: unknown };
  expect(JSON.stringify(config.state_fields ?? [])).not.toContain("screen");
  expect(JSON.stringify(config.events ?? [])).not.toContain("task.give");
});
