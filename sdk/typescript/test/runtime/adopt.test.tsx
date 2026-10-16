// call.attached: adopting a call mid-conversation from its current state.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, expect, it } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

import ClinicaNorte from "../agent/clinica-norte.js";
import { mount, type Mounted } from "../../src/runtime/connect.js";

const KEY = "pk_test";
const SLUG = "clinica-norte";
const CALL = "CA_1";
const FILE = fileURLToPath(new URL("../agent/clinica-norte.tsx", import.meta.url));
const SOURCE = readFileSync(FILE, "utf8");
const ANA = { id: "p1", name: "Ana", phone: "+34 600 000 001" };
const YESTERDAY = Date.now() / 1000 - 24 * 60 * 60;

let gateway: FakeGateway;
let pc: Pinecall;
let mounted: Mounted;

beforeEach(async () => {
  gateway = await FakeGateway.start({ apiKey: KEY });
  pc = new Pinecall({ url: gateway.url, apiKey: KEY });
  pc.onErrors(() => {});
  mounted = mount(ClinicaNorte, { pc, source: SOURCE, file: FILE, slug: SLUG });
  await pc.connect();
  await settled();
});

afterEach(async () => {
  pc.close();
  await gateway.close();
});

async function settled(): Promise<void> {
  for (let turn = 0; turn < 20; turn++) await new Promise((resolve) => setTimeout(resolve, 1));
}

function theLine(from: string, startedAt: number): Record<string, unknown> {
  return { channel: "phone", direction: "inbound", from, to: "+34 910 000 000", caller: null, started_at: startedAt };
}

function attached(state: Record<string, unknown>, startedAt = Date.now() / 1000): void {
  // An unknown caller: an onCall that ran would have left the patient undefined.
  gateway.emit(SLUG, CALL, "call.attached", { app: "app_new", started: theLine("+34 699 999 999", startedAt), state, seq: 41 });
}

function commands(type: string): Record<string, unknown>[] {
  return gateway.commandsOf(type).map((command) => command.data);
}

it("adopts a call the gateway attaches mid-conversation, and sends the whole prompt again", async () => {
  attached({ patient: ANA, slots: [] });
  await settled();
  expect(commands("prompt.set").map((set) => set["name"])).toEqual(["identity", "tools", "view"]);
  const tools = commands("tools.set").at(-1)?.["tools"] as { name: string }[];
  expect(tools.map((tool) => tool.name)).toEqual(["freeSlots", "transfer"]);
  expect(commands("state.set")).toEqual([]);
});

it("gives an adopted call the claim it carried, so a view about the screen answers the same", async () => {
  gateway.emit(SLUG, CALL, "call.attached", {
    app: "app_new",
    started: theLine("+34 699 999 999", Date.now() / 1000),
    state: { patient: ANA, slots: [] },
    seq: 41,
    claimed: "4821",
  });
  await settled();
  const instance = mounted.instanceOf(CALL) as unknown as { call: { claimed: string | null } };
  expect(instance.call.claimed).toBe("4821");
});

it("gives an adopted call the snapshot's fields and runs no onCall", async () => {
  attached({ patient: ANA, slots: [] });
  await settled();
  const instance = mounted.instanceOf(CALL) as unknown as { patient?: { name: string } };
  expect(instance.patient?.name).toBe("Ana");
});

it("answers a tool on an adopted call, from the state it was handed", async () => {
  attached({ patient: ANA, slots: [] });
  gateway.emit(SLUG, CALL, "tool.call", { call_id: "t1", name: "freeSlots", arguments: { day: "2026-03-02" } });
  await settled();
  const result = commands("tool.result").at(-1);
  expect(result?.["error"]).toBeUndefined();
  expect(result?.["output"]).toHaveLength(2);
});

it("re-syncs, and does not rebuild, a call it already serves when the gateway attaches it again", async () => {
  gateway.emit(SLUG, CALL, "call.started", theLine(ANA.phone, Date.now() / 1000));
  await settled();
  const instance = mounted.instanceOf(CALL);
  const sent = commands("prompt.set").length;
  attached({ patient: ANA, slots: [] });
  await settled();
  expect(mounted.instanceOf(CALL)).toBe(instance);
  expect(commands("prompt.set").length - sent).toBe(3);
});

it("gives an adopted call the day it opened, not the day it was handed over", async () => {
  attached({ patient: ANA, slots: [] }, YESTERDAY);
  await settled();
  const instance = mounted.instanceOf(CALL) as unknown as { call: { today: string } };
  const opened = new Date(YESTERDAY * 1000);
  const day = `${opened.getFullYear()}-${String(opened.getMonth() + 1).padStart(2, "0")}-${String(opened.getDate()).padStart(2, "0")}`;
  expect(instance.call.today).toBe(day);
});
