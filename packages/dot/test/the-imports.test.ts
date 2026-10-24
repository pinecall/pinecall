// The import table, as a test. Read top to bottom it is the whole architecture: the wire is plain
// data, the page's parts know only the DOM, and the agent's side is the one place Node is named.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL("../src", import.meta.url));

/** What each part of src/ may import: our own parts as `./name` (`.` for the top), and packages by name. */
const MAY_IMPORT: Record<string, string[]> = {
  // What the page and the agent say to each other: plain data, nothing else.
  "wire": [],
  // The face: the DOM, Web Audio, and the room it moves with.
  "face": ["@pinecall/room"],
  // The page as the agent reads it: the DOM, and the wire's shape of the site's lines.
  "page": ["./wire"],
  // The person with a pointer: the DOM alone.
  "pointer": [],
  // The tutor on a page: everything of the page's side, the room, and the wire.
  "tutor": ["./face", "./page", "./pointer", "./wire", "@pinecall/room"],
  // The agent's side: the framework, Node, and the wire. Never the DOM's parts.
  "agent": ["@pinecall/agents", "node:fs", "node:path", "node:url", "./wire"],
  // The page's entry: what a page imports.
  "": ["./face", "./page", "./tutor", "./wire"],
};

/** Files held to a narrower line than their directory's. */
const ONLY: Record<string, string[]> = {
  // The macro player counts words: the wire, and nothing of the DOM.
  "tutor/macro.ts": ["./wire"],
};

/** The only part that may name Node. */
const NODE = "agent";

/** Which line of the table a file falls under: the longest declared prefix of its path. */
function partOf(path: string): string {
  const parts = path.split("/").slice(0, -1);
  for (let depth = parts.length; depth >= 0; depth--) {
    const candidate = parts.slice(0, depth).join("/");
    if (candidate in MAY_IMPORT) return candidate;
  }
  throw new Error(`src/${path} is in no part of the table: give its directory a line`);
}

// What an import looks like once the comments are gone; the third form is `import("x")`, a
// package loaded when it is needed.
const SPECIFIER = /^(?:import|export)[\s\S]*?from\s+"([^"]+)"|^import\s+"([^"]+)"|\bimport\("([^"]+)"\)/gm;

/** Our own part as an import names it, so a part called `react` is never the package `react`. */
function ownPart(part: string): string {
  return part === "" ? "." : `./${part}`;
}

function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** Every import in the tree, a part's imports of itself included: the file, its part, what it named. */
function everyEdge(): { from: string; to: string; file: string }[] {
  const found: { from: string; to: string; file: string }[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (extname(full) !== ".ts") continue;
      const file = relative(SRC, full);
      const from = partOf(file);
      for (const [, named, bare, lazy] of withoutComments(readFileSync(full, "utf8")).matchAll(SPECIFIER)) {
        const spec = named ?? bare ?? lazy;
        if (spec === undefined) continue;
        const to = spec.startsWith(".")
          ? ownPart(partOf(relative(SRC, resolve(dir, spec))))
          : spec.replace(/^(@[^/]+\/[^/]+|[^@/][^/]*).*$/, "$1");
        found.push({ from, to, file });
      }
    }
  };
  walk(SRC);
  return found;
}

/** The imports that cross from one part to another: what the table is about. */
function edges(): { from: string; to: string; file: string }[] {
  return everyEdge().filter(({ from, to }) => to !== ownPart(from));
}

describe("the import table", () => {
  it("is obeyed, line by line", () => {
    const broken = edges()
      .filter(({ from, to, file }) => !(ONLY[file] ?? MAY_IMPORT[from] ?? []).includes(to))
      .map(({ from, to, file }) => `src/${file}: ${from || "src"} may not import ${to}`);

    expect([...new Set(broken)].sort()).toEqual([]);
  });

  it("holds the narrower files to their narrower line, their own part included", () => {
    const broken = everyEdge()
      .filter(({ file, to }) => file in ONLY && !(ONLY[file] ?? []).includes(to))
      .map(({ file, to }) => `src/${file} may not import ${to}`);

    expect(broken).toEqual([]);
  });

  it("lets only agent/ name Node", () => {
    const naming = edges().filter(({ to }) => to.startsWith("node:")).map(({ from }) => from);

    expect([...new Set(naming)]).toEqual([NODE]);
  });

  // A line nobody needs is a line that stops being read. Every entry is either used or gone.
  it("names nothing the tree does not actually import", () => {
    const used = new Set(edges().map(({ from, to }) => `${from} -> ${to}`));
    const idle = Object.entries(MAY_IMPORT).flatMap(([part, allowed]) =>
      allowed.filter((one) => !used.has(`${part} -> ${one}`)).map((one) => `${part || "src"} -> ${one}`),
    );

    expect(idle, "delete the line, or the import it was written for is missing").toEqual([]);
  });

  it("gives every directory of src/ a line of its own", () => {
    const walk = (dir: string): string[] =>
      readdirSync(dir)
        .map((name) => join(dir, name))
        .filter((full) => statSync(full).isDirectory())
        .flatMap((full) => [relative(SRC, full), ...walk(full)]);

    expect(walk(SRC).filter((dir) => !(dir in MAY_IMPORT))).toEqual([]);
  });
});
