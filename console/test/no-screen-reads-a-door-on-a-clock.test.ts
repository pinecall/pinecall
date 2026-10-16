/** A screen reads a door when the feed speaks, never on a clock: the only intervals are the ones that repaint a time. */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

const CONSOLE = fileURLToPath(new URL("..", import.meta.url));
const CORE = fileURLToPath(new URL("../../packages/core/src", import.meta.url));
const ROOT = fileURLToPath(new URL("../..", import.meta.url));

// Every interval of the page and why it is not a read: a repaint of how long something has lasted,
// or the clock a feed that is down is read on until it is back (`useFed`, the only one that reads).
const ALLOWED: Record<string, string> = {
  "console/src/shell/ringing.tsx": "repaints how long a call has rung",
  "console/src/screens/call/call.tsx": "repaints how long a call has lasted",
  "console/src/screens/talk/talk.tsx": "repaints how long a talk has lasted",
  "packages/core/src/use-fed.ts": "reads a door while the feed is down, and stops when it is back",
};

const A_CLOCK = /\bsetInterval\(|\brefetchInterval\b/;

function sources(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : sources(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

const ticking = [...sources(join(CONSOLE, "src")), ...sources(CORE)].filter((path) => A_CLOCK.test(readFileSync(path, "utf8"))).map((path) => relative(ROOT, path));

test("no screen or hook reads a door on a clock: it reads when the feed says a thing changed", () => {
  expect(ticking.filter((path) => !(path in ALLOWED))).toEqual([]);
});

test("the list of clocks that are allowed names only clocks that still tick", () => {
  expect(Object.keys(ALLOWED).filter((path) => !ticking.includes(path))).toEqual([]);
});
