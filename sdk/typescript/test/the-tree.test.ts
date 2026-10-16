// Repo layout rules: file size ceiling, a descriptive first line, no near-duplicate names.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const REPO = fileURLToPath(new URL("..", import.meta.url));

const TREES = ["src", "test"];

const A_FILE_A_PERSON_READS = 400;

/** Hand-written .ts and .tsx files, repo-relative, excluding builds and node_modules. */
function sources(): string[] {
  const found: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      if (name === "node_modules" || name === "dist") continue;
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (extname(path) === ".ts" || extname(path) === ".tsx") found.push(relative(REPO, path));
    }
  };
  for (const tree of TREES) walk(join(REPO, tree));
  return found.sort();
}

const SOURCES = sources();

describe("every file a person reads", () => {
  it("fits in one reading", () => {
    const long = SOURCES.filter((path) => readFileSync(join(REPO, path), "utf8").split("\n").length > A_FILE_A_PERSON_READS);

    expect(long, `over ${A_FILE_A_PERSON_READS} lines: split the idea, do not raise the ceiling`).toEqual([]);
  });

  // A shebang may precede it.
  it("opens by saying what it is", () => {
    const silent = SOURCES.filter((path) => {
      const lines = readFileSync(join(REPO, path), "utf8").split("\n");
      const first = (lines[0]?.startsWith("#!") ? lines[1] : lines[0]) ?? "";
      return !first.trimStart().startsWith("//") && !first.trimStart().startsWith("/*");
    });

    expect(silent, "the first line of a file says what it is").toEqual([]);
  });
});

describe("the names in one directory", () => {
  // e.g. `llm.ts` next to `llms.ts` is easy to mix up.
  it("differ by more than one letter", () => {
    const byDirectory = new Map<string, string[]>();
    for (const path of SOURCES) {
      const stem = basename(path).replace(/\.tsx?$/, "").replace(/\.test$/, "");
      byDirectory.set(dirname(path), [...(byDirectory.get(dirname(path)) ?? []), stem]);
    }
    const tooClose: string[] = [];
    for (const [directory, stems] of byDirectory) {
      for (let i = 0; i < stems.length; i++) {
        for (let j = i + 1; j < stems.length; j++) {
          const [a, b] = [stems[i]!, stems[j]!];
          if (a !== b && distance(a, b) <= 1) tooClose.push(`${directory}: ${a} / ${b}`);
        }
      }
    }

    expect(tooClose, "name one of them for what it holds").toEqual([]);
  });
});

describe("the repo root", () => {
  it("holds no TypeScript but the configs", () => {
    const loose = readdirSync(REPO).filter((name) => /\.tsx?$/.test(name) && !name.startsWith("vitest.config"));

    expect(loose, "a module at the root belongs to no idea: put it in src/").toEqual([]);
  });
});

// Levenshtein distance.
function distance(a: string, b: string): number {
  let previous = [...Array(b.length + 1).keys()];
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      row.push(Math.min(row[j - 1]! + 1, previous[j]! + 1, previous[j - 1]! + cost));
    }
    previous = row;
  }
  return previous[b.length]!;
}
