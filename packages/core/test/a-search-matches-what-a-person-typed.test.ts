/** calls-search.ts: local search over id, numbers, caller and agent, and change detection. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import { expect, test } from "vitest";

import { floorMoved, matches } from "../src/calls-search";

const row = (fields: Partial<SessionLine>): SessionLine =>
  ({ call: "call_3f7d8c21", agent: "recepcion", live: true, status: "active", channel: "phone", direction: "inbound", from: "+34612345678", to: "+34910000000", caller: null, outcome: null, ...fields }) as SessionLine;

test("nothing typed matches every call", () => {
  expect(matches(row({}), "  ")).toBe(true);
});

test("a call matches by its id, its agent, its caller's name and its outcome, whatever the case", () => {
  expect(matches(row({}), "3F7D")).toBe(true);
  expect(matches(row({}), "recep")).toBe(true);
  expect(matches(row({ caller: { name: "Lucía Pérez" } }), "lucía")).toBe(true);
  expect(matches(row({ outcome: "cita reservada" }), "reservada")).toBe(true);
  expect(matches(row({}), "citas")).toBe(false);
});

test("three digits or more match a number however it is spaced", () => {
  expect(matches(row({}), "612 345")).toBe(true);
  expect(matches(row({}), "+34 910")).toBe(true);
  expect(matches(row({}), "619")).toBe(false);
});

test("a followed list moved when a call came, went first, or ended — and not when nothing did", () => {
  const lines = [row({ call: "a" }), row({ call: "b", status: "ended" })];
  expect(floorMoved(lines)).toBe(floorMoved([...lines]));
  expect(floorMoved(lines)).not.toBe(floorMoved([row({ call: "c" }), ...lines]));
  expect(floorMoved(lines)).not.toBe(floorMoved([row({ call: "a", status: "ended" }), lines[1] as SessionLine]));
});
