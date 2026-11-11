// The front desk as a class: the agenda it reads, the time it will not book, and the patient it shares.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { beforeEach, expect, it } from "vitest";
import { CallWorld, describe as describeClass, runHook, runTool, seal, setCall, toolNamed } from "@pinecall/agents";

import { clinic } from "../../../lib/clinic.js";
import FrontDesk from "../agent.js";

const FILE = fileURLToPath(new URL("../agent.ts", import.meta.url));
describeClass(FrontDesk, readFileSync(FILE, "utf8"), FILE);

const A_MONDAY = "2026-11-09";
const A_SUNDAY = "2026-11-08";
const ANA = "+14155550142";

let desk: FrontDesk;

function run(name: string, args: Record<string, unknown>): Promise<unknown> {
  return runTool(desk, toolNamed(desk, name)!, args);
}

beforeEach(async () => {
  clinic.visits.length = 0;
  desk = seal(new FrontDesk());
  setCall(desk, new CallWorld({ id: "CA_1", contact: ANA, from: ANA, channel: "phone" }, () => undefined));
  await runHook(desk, "onCall", { id: "CA_1", contact: ANA, from: ANA });
});

it("finds the patient by the number calling, and shares her with whoever takes the call next", () => {
  expect(desk.call.shared["patient"]).toMatchObject({ name: "Ana Lopez" });
});

it("reads a weekday's open times, and none on a weekend", async () => {
  expect(await run("freeSlots", { day: A_MONDAY })).toHaveLength(3);
  expect(String(await run("freeSlots", { day: A_SUNDAY }))).toContain("Nothing is open");
});

it("books only a time the agenda gave it, and tells the model when one was taken meanwhile", async () => {
  expect(String(await run("book", { day: A_MONDAY, time: "09:30", name: "Ana Lopez" }))).toContain("did not come from the agenda");
  await run("freeSlots", { day: A_MONDAY });
  expect(await run("book", { day: A_MONDAY, time: "09:30", name: "Ana Lopez" })).toMatchObject({ id: "v-1", time: "09:30" });
  expect(String(await run("book", { day: A_MONDAY, time: "09:30", name: "Jordan Lee" }))).toContain("just taken");
});
