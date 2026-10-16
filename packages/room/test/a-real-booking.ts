/** The booking call of 2026-09-22 as entries: 81 of them off the gateway, saved as they came. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { decodeEntry } from "../src/wire/codec.js";
import { type Entry } from "../src/wire/envelope.js";

// A fixture made by hand would agree with whatever the code believes; this one cannot.
export const BOOKING: readonly Entry[] = read("./fixtures/a-real-booking.json").map((raw) => decodeEntry(raw));

function read(path: string): unknown[] {
  const raw: unknown = JSON.parse(readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8"));
  if (!Array.isArray(raw)) throw new Error(`${path} is not a list of entries`);
  return raw;
}
