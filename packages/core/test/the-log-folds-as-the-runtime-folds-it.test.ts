/** The page's reducer and reader hold to the runtime's golden call log and the state it folds to. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

import { decodeEntry, eventOf } from "../src/wire/codec.js";
import { apply, initialState } from "../src/wire/reduce.js";

// Copied from the runtime's tests/wire/golden/: when its wire moves, these two files move with it.
const golden = (name: string): unknown =>
  JSON.parse(readFileSync(fileURLToPath(new URL(`./golden/${name}`, import.meta.url)), "utf8"));
const entries = (golden("call-log.json") as unknown[]).map(decodeEntry);

test("every entry of the golden log reads as the event its type names", () => {
  for (const entry of entries) {
    expect(eventOf(entry).type).toBe(entry.type);
  }
});

test("the golden log folds to the state the runtime folds it to", () => {
  const state = entries.reduce(apply, initialState());
  expect(state).toEqual(golden("call-log.state.json"));
});
