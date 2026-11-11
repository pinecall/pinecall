// The app's team on the wire, against a gateway that is not there: the call the front desk passes to billing.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";
import { type Agent, describe as describeClass, mount, type Team } from "@pinecall/agents";
import { Pinecall } from "@pinecall/agents/client";
import { FakeGateway } from "@pinecall/agents/client/testing";

import app from "../app.js";
import Billing from "../agents/brightside-billing/agent.js";
import FrontDesk from "../agents/brightside-front-desk/agent.js";

const KEY = "pk_test";
const CALL = "CA_1";
const SLUG = "brightside-front-desk";
const ANA = "+14155550142";

// Each class is handed its source, as `pinecall start` hands it: the tools' descriptions and types are read from it.
for (const [ctor, folder] of [[FrontDesk, "brightside-front-desk"], [Billing, "brightside-billing"]] as const) {
  const file = fileURLToPath(new URL(`../agents/${folder}/agent.ts`, import.meta.url));
  describeClass(ctor, readFileSync(file, "utf8"), file);
}

let gateway: FakeGateway;
let pc: Pinecall;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  const team: Team = new Map<new () => Agent, string>([[FrontDesk, "brightside-front-desk"], [Billing, "brightside-billing"]]);
  mount(FrontDesk, { pc, slug: SLUG, declares: app.declares(FrontDesk), team });
  await pc.connect();
  await settled();
  gateway.emit(SLUG, CALL, "call.started", { channel: "phone", direction: "inbound", from: ANA, to: "+14155550134", caller: null, started_at: Date.now() / 1000 });
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

async function settled(): Promise<void> {
  for (let turn = 0; turn < 30; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function sent(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

function open(): string[] {
  return (sent("tools.set").at(-1)?.["tools"] as { name: string }[]).map((spec) => spec.name).sort();
}

async function calls(name: string, args: Record<string, unknown>, id: string): Promise<void> {
  gateway.emit(SLUG, CALL, "tool.call", { call_id: id, name, arguments: args });
  await settled();
}

it("declares the line's greeting, the app's silence and its timezone for the agent that answers", () => {
  expect(sent("agent.configure")[0]?.["config"]).toMatchObject({
    timezone: "America/Los_Angeles",
    greeting: { say: "Brightside Dental. How can I help?" },
    idle: { says: ["Are you still there?"], after_s: 8, times: 2 },
  });
});

it("opens the front desk's tools and the transfer to billing, and declares every tool of the team", () => {
  expect(open()).toEqual(["book", "disputeCharge", "freeSlots", "transfer_to_billing"]);
  const declared = (sent("agent.configure")[0]?.["config"] as { tools: { name: string }[] }).tools.map((spec) => spec.name);
  expect(declared).toEqual(expect.arrayContaining(["askRefund", "listInvoices", "transfer_to_front_desk"]));
});

it("passes a disputed charge to billing, which already knows the patient and her invoices", async () => {
  await calls("disputeCharge", { invoice: "inv-302" }, "t1");
  expect(open()).toEqual(["askRefund", "listInvoices", "transfer_to_front_desk"]);
  expect(sent("call.log").at(-1)).toMatchObject({ name: "handoff", data: { from: SLUG, to: "brightside-billing", invoice: "inv-302" } });
  const state = sent("state.set").at(-1)?.["state"] as { invoices: { id: string }[] };
  expect(state.invoices.map((invoice) => invoice.id)).toEqual(["inv-301", "inv-302"]);
});
