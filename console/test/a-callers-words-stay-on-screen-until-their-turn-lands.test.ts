/** heard.ts: what the caller said stays on screen from the moment it is heard to the end until its turn lands. */

import { expect, test } from "vitest";

import type { Entry } from "@pinecall/core/wire/envelope";

import { heardSoFar } from "../src/screens/call/heard";

const at = (seq: number, type: string, data: Record<string, unknown>): Entry => ({ seq, ts: seq, call: "call_1", agent: "ana", type, ephemeral: type === "user.transcript", data });

const TURN = at(1, "turn.user", { speech_id: "s1", item_id: "i1", text: "Hello.", metrics: {} });
const FIRST = at(2, "user.transcript", { text: "Ten thirty on Tuesday works.", final: true });
const SECOND = at(3, "user.transcript", { text: "My email is Laura at example dot com.", final: true });

test("a stretch heard to the end stays while the turn it belongs to has not landed", () => {
  expect(heardSoFar([TURN, FIRST], null)).toBe("Ten thirty on Tuesday works.");
});

test("the stretches heard so far come before what is heard this instant", () => {
  expect(heardSoFar([TURN, FIRST], "My email")).toBe("Ten thirty on Tuesday works. My email");
  expect(heardSoFar([TURN, FIRST, SECOND], null)).toBe("Ten thirty on Tuesday works. My email is Laura at example dot com.");
});

test("the turn landing takes their place, and nothing is heard before anybody speaks", () => {
  const landed = at(4, "turn.user", { speech_id: "s2", item_id: "i2", text: "Ten thirty on Tuesday works. My email is Laura at example dot com.", metrics: {} });
  expect(heardSoFar([TURN, FIRST, SECOND, landed], null)).toBeNull();
  expect(heardSoFar([], null)).toBeNull();
});
