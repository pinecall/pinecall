// A tool that asks, on the wire: the question as its result, one tool open meanwhile, and the answer finishing it.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";

import { describe as describe_ } from "../../src/agent/docstrings.js";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";
import { mount } from "../../src/runtime/connect.js";

import Books from "./asks/books.js";

const KEY = "pk_test";
const CALL = "CA_1";
const SLUG = "books";
const FILE = fileURLToPath(new URL("./asks/books.ts", import.meta.url));
describe_(Books, readFileSync(FILE, "utf8"), FILE);

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mount(Books, { pc, slug: SLUG });
  await pc.connect();
  await settled();
  gateway.emit(SLUG, CALL, "call.started", { channel: "phone", direction: "inbound", from: "+34600000001", to: "+34910000000", caller: null, started_at: Date.now() / 1000 });
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

function visible(): string[] {
  return (commands("tools.set").at(-1)?.["tools"] as { name: string }[]).map((spec) => spec.name).sort();
}

async function called(name: string, args: Record<string, unknown>, id: string): Promise<Record<string, unknown> | undefined> {
  gateway.emit(SLUG, CALL, "tool.call", { call_id: id, name, arguments: args });
  await settled();
  return commands("tool.result").find((result) => result["callId"] === id || result["call_id"] === id);
}

it("declares the tool each of its tasks is given with, and opens its own alone", () => {
  const declared = (commands("agent.configure")[0]?.["config"] as { tools: { name: string }[] }).tools.map((spec) => spec.name).sort();
  expect(declared).toEqual(["book", "give_email", "hours"]);
  expect(visible()).toEqual(["book", "hours"]);
});

it("answers the tool that asked with the question, and leaves the answer's tool alone open", async () => {
  const asked = await called("book", { time: "09:30" }, "t1");
  expect(String(asked?.["output"])).toContain("it needs the caller's email address");
  expect(visible()).toEqual(["give_email"]);
});

it("finishes the first tool on the answer: its result, its state, and its tools open again", async () => {
  await called("book", { time: "09:30" }, "t1");
  const given = await called("give_email", { email: "Ana@Example.com" }, "t2");
  expect(given?.["output"]).toEqual({ finished: "book", result: { time: "09:30", confirmation: "ana@example.com" } });
  expect(commands("state.set").at(-1)?.["state"]).toMatchObject({ sentTo: "ana@example.com" });
  expect(visible()).toEqual(["book", "hours"]);
});

it("asks again when the answer is no email address", async () => {
  await called("book", { time: "09:30" }, "t1");
  const refused = await called("give_email", { email: "ana at example" }, "t2");
  expect(JSON.stringify(refused)).toContain("is not an email address");
  expect(visible()).toEqual(["give_email"]);
});
