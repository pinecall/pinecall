/** One call's medians are the runtime's: the five latencies and talk share, on the golden log. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

import { MEDIANS, measured, medians } from "../src/metrics.js";
import { decodeEntry } from "../src/wire/codec.js";

const entries = (JSON.parse(readFileSync(fileURLToPath(new URL("./golden/call-log.json", import.meta.url)), "utf8")) as unknown[]).map(decodeEntry);
const read = medians(entries);
const one = (name: string) => read.find((median) => median.name === name);

// What the runtime's log/reduce.py `samples` folds the same golden log to, printed from it on 2026-10-02:
// talk_share [0.7517339245626421].
test("every measure the runtime folds is read, in its order", () => {
  expect(read.map((median) => median.name)).toEqual([...MEDIANS]);
});

test("talk share is the agent's part of the time anybody spoke, one per call", () => {
  expect(one("talk_share")?.turns).toBe(1);
  expect(one("talk_share")?.seconds).toBeCloseTo(0.7517339245626421, 6);
  expect(measured("talk_share", 0.7517339245626421)).toBe("75%");
  expect(measured("e2e_latency", 0.94)).toBe("940 ms");
});
