/** Signing out removes the stored key. */

import { beforeEach, expect, test } from "vitest";

import { forgetKey, keepKey, keptKey } from "../src/lib/session-key";

// No DOM in this directory: a Map stands in for the browser's string storage.
const kept = new Map<string, string>();

beforeEach(() => {
  kept.clear();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      localStorage: {
        getItem: (name: string) => kept.get(name) ?? null,
        setItem: (name: string, value: string) => void kept.set(name, value),
        removeItem: (name: string) => void kept.delete(name),
      },
    },
  });
});

test("a person holds one key, and signing out leaves the browser holding none", async () => {
  await keepKey("pc_berna");

  expect(await keptKey()).toBe("pc_berna");
  // Legacy storage name, still read for browsers signed in before the move to core.
  expect(kept.get("pinecall.key")).toBe("pc_berna");
  await forgetKey();
  expect(await keptKey()).toBeNull();
  expect(kept.size).toBe(0);
});

test("signing out of a tab that held nothing is not an error", async () => {
  await expect(forgetKey()).resolves.toBeUndefined();
  expect(await keptKey()).toBeNull();
});
