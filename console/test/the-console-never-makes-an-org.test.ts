/** The console signs people in but never calls the sign-up door. */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

// Source dirs in the bundle, relative to the repository's root.
const REPOSITORY = fileURLToPath(new URL("../..", import.meta.url));
const SOURCES = ["console/src", "packages/core/src"];

// Every self-hosted runtime serves this page, so a sign-up form would risk open registration on
// other people's boxes. The page calls `/v1/login`, never `/v1/signup`.
test("no file of the console knocks at the sign-up door", () => {
  expect(filesReaching("/v1/signup")).toEqual([]);
});

// The only keyless door it calls.
test("the login door is reached from exactly one file", () => {
  expect(filesReaching("\"/v1/login\"")).toEqual(["packages/core/src/login.ts"]);
});

// Slugs are minted by the gateway at sign-up; nothing in the page derives one.
test("nothing in the console derives an org's slug", () => {
  expect(filesReaching("normalize(\"NFD\")")).toEqual([]);
});

// Strip comments first: a docstring may mention the sign-up door.
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
