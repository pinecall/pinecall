/** No CSS class is defined by two screens' stylesheets. */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

const SOURCE = fileURLToPath(new URL("../../src", import.meta.url));

// Vite bundles all of a page's stylesheets into one file, so every class is global. Prefix classes
// with what they belong to (`.said-mark`, `.timeline .mark`).
const A_CLASS = /^\s*(\.[A-Za-z0-9_-]+)(?=[\s,{:])/gm;

// The ui kit's stylesheet. Screens may scope into `.ui-` classes (`.sim-check .ui-check`) but must
// not define their own.
const THE_SHARED_ONE = "ui/ui.css";

test("no class is defined by two of the console's stylesheets", () => {
  const owners = new Map<string, string[]>();
  for (const file of stylesheets()) {
    for (const name of classesIn(readFileSync(join(SOURCE, file), "utf8"))) {
      owners.set(name, [...(owners.get(name) ?? []), file]);
    }
  }
  const shared = [...owners.entries()]
    .filter(([, files]) => new Set(files).size > 1)
    .map(([name, files]) => `${name}: ${[...new Set(files)].join(" and ")}`);
  expect(shared).toEqual([]);
});

test("no screen redefines the vocabulary the ui kit spells", () => {
  const page = new Set(classesIn(readFileSync(join(SOURCE, THE_SHARED_ONE), "utf8")));
  const taken: string[] = [];
  for (const file of stylesheets().filter((one) => one !== THE_SHARED_ONE)) {
    for (const name of classesIn(readFileSync(join(SOURCE, file), "utf8"))) {
      if (page.has(name)) taken.push(`${name}: ${file}`);
    }
  }
  expect(taken).toEqual([]);
});

/** Top-level classes a stylesheet defines; nested selectors are ignored. */
function classesIn(css: string): string[] {
  return [...css.matchAll(A_CLASS)].map((found) => found[1] as string);
}

function stylesheets(): string[] {
  return filesUnder(SOURCE)
    .filter((file) => file.endsWith(".css"))
    .map((file) => relative(SOURCE, file))
    .sort();
}

function filesUnder(root: string): string[] {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const here = join(root, entry.name);
    return entry.isDirectory() ? filesUnder(here) : [here];
  });
}
