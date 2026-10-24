// The shape of the repo, as a test. A layout nobody checks is a layout that drifts back: a file that
// grew past reading, a module whose first line did not say what it was, a test directory named for
// nothing in src/.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const REPO = fileURLToPath(new URL("..", import.meta.url));

// The two trees of hand-written TypeScript.
const TREES = ["src", "test"];

// The pages at the root are read the same way the code is, and hold to the same ceiling.
const PAGES = ["README.md", "CLAUDE.md", "CHANGELOG.md"];

// 400 lines is the ceiling and 150 the norm. A file over it is not a style problem: it is two
// ideas that were never separated, and it stops fitting in a reading.
const A_FILE_A_PERSON_READS = 400;

/** Every .ts a person wrote, repo-relative, with node_modules and dist left out. */
function sources(): string[] {
  const found: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      if (name === "node_modules" || name === "dist") continue;
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (extname(path) === ".ts") found.push(relative(REPO, path));
    }
  };
  for (const tree of TREES) walk(join(REPO, tree));
  return found.sort();
}

/** Every directory under `tree`, relative to it. */
function directories(tree: string): string[] {
  const found: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (!statSync(path).isDirectory()) continue;
      found.push(relative(join(REPO, tree), path));
      walk(path);
    }
  };
  walk(join(REPO, tree));
  return found.sort();
}

const SOURCES = sources();

describe("every file a person reads", () => {
  it("fits in one reading", () => {
    const pages = PAGES.filter((page) => {
      try {
        return statSync(join(REPO, page)).isFile();
      } catch {
        return false;
      }
    });
    const long = [...SOURCES, ...pages].filter(
      (path) => readFileSync(join(REPO, path), "utf8").split("\n").length > A_FILE_A_PERSON_READS,
    );

    expect(long, `over ${A_FILE_A_PERSON_READS} lines: split the idea, do not raise the ceiling`).toEqual([]);
  });

  // The first line is what a reader has before anything else, so it says what the file is.
  it("opens by saying what it is", () => {
    const silent = SOURCES.filter((path) => {
      const first = readFileSync(join(REPO, path), "utf8").split("\n")[0] ?? "";
      return !first.startsWith("//") && !first.startsWith("/*");
    });

    expect(silent, "the first line of a file says what it is").toEqual([]);
  });
});

describe("the tests", () => {
  // A test file is named for the sentence it proves, so it cannot be named for the module. What
  // mirrors src/ is the directories: test/seat tests src/seat, and a test directory named for
  // nothing there is a test of something that moved.
  it("mirror src/ directory for directory", () => {
    const inSrc = new Set(directories("src"));
    const strays = directories("test").filter((dir) => dir !== "fixtures" && !inSrc.has(dir));

    expect(strays, "name the directory for the part of src/ it tests").toEqual([]);
  });
});

describe("the names in one directory", () => {
  // Two modules a reader cannot tell apart are two imports a writer will mix up.
  it("differ by more than one letter", () => {
    const byDirectory = new Map<string, string[]>();
    for (const path of SOURCES) {
      const stem = basename(path).replace(/\.ts$/, "").replace(/\.test$/, "");
      byDirectory.set(dirname(path), [...(byDirectory.get(dirname(path)) ?? []), stem]);
    }
    const tooClose: string[] = [];
    for (const [directory, stems] of byDirectory) {
      for (let i = 0; i < stems.length; i++) {
        for (let j = i + 1; j < stems.length; j++) {
          const [a, b] = [stems[i] ?? "", stems[j] ?? ""];
          if (a !== b && distance(a, b) <= 1) tooClose.push(`${directory}: ${a} / ${b}`);
        }
      }
    }

    expect(tooClose, "name one of them for what it holds").toEqual([]);
  });
});

describe("the repo root", () => {
  it("holds no TypeScript but the config", () => {
    const loose = readdirSync(REPO).filter((name) => name.endsWith(".ts") && !name.startsWith("vitest.config"));

    expect(loose, "a module at the root belongs to no idea: put it in src/").toEqual([]);
  });
});

// Levenshtein, small and readable: two names this close in one directory is the bug.
function distance(a: string, b: string): number {
  let previous = [...Array(b.length + 1).keys()];
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      row.push(Math.min((row[j - 1] ?? 0) + 1, (previous[j] ?? 0) + 1, (previous[j - 1] ?? 0) + cost));
    }
    previous = row;
  }
  return previous[b.length] ?? 0;
}
