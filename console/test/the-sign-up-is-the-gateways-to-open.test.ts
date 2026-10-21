/** The sign-up is shown only where the gateway opens it, and each keyless door is knocked at from one file. */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

// Source dirs in the bundle, relative to the repository's root.
const REPOSITORY = fileURLToPath(new URL("../..", import.meta.url));
const SOURCES = ["console/src", "packages/core/src"];

// Every self-hosted runtime serves this page, so whether it takes sign-ups is the gateway's word
// (`/.well-known/pinecall`, `signup`), read by the screen before it draws a form.
test("the sign-up screen asks the floor before it draws a form", () => {
  const screen = code(readFileSync(join(REPOSITORY, "console/src/screens/login/signup.tsx"), "utf8"));
  expect(screen).toContain("discovered(base)");
  expect(screen).toContain("!floor.signup");
});

// The keyless doors, each reached from exactly one file of the core.
test("the sign-up doors are reached from exactly one file", () => {
  expect(filesReaching("\"/v1/signup\"")).toEqual(["packages/core/src/signup.ts"]);
  expect(filesReaching("/v1/signup/verify")).toEqual(["packages/core/src/signup.ts"]);
});

test("the login door is reached from exactly one file", () => {
  expect(filesReaching("\"/v1/login\"")).toEqual(["packages/core/src/login.ts"]);
});

// Slugs are made by the gateway at sign-up, of the org's name; nothing in the page derives one.
test("nothing in the console derives an org's slug", () => {
  expect(filesReaching("normalize(\"NFD\")")).toEqual([]);
  expect(filesReaching("normalize(\"NFKD\")")).toEqual([]);
});

// Strip comments first: a docstring may mention a door.
function filesReaching(text: string): string[] {
  return sources().filter((file) => code(readFileSync(join(REPOSITORY, file), "utf8")).includes(text));
}

function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function sources(): string[] {
  const found: string[] = [];
  const walk = (at: string): void => {
    for (const entry of readdirSync(at, { withFileTypes: true })) {
      const path = join(at, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (/\.(ts|tsx)$/.test(entry.name)) found.push(relative(REPOSITORY, path));
    }
  };
  for (const source of SOURCES) walk(join(REPOSITORY, source));
  return found.sort();
}
