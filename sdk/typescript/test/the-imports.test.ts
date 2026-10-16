// Import rules for src/: every directory has a line listing what it may import, ours and external.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL("../src", import.meta.url));

/** Allowed imports per directory of src/: our own directories and external packages. */
const MAY_IMPORT: Record<string, string[]> = {
  // The runtime's shapes and the reducer: data, no framework.
  "wire": ["zod"],
  // The socket: wire only.
  "client": ["wire", "ws"],
  // `views` only for the type `render()` returns; the JSX runtime imports nothing of ours.
  "agent": ["call", "views", "wire", "oxc-parser", "zod"],
  "call": ["agent", "wire"],
  // Uses the wire's rule for block names.
  "views": ["agent", "wire"],
  "runtime": ["agent", "call", "views", "client", "wire"],
  // The entry the CLI starts an agent with; `tsx` is imported lazily, for a tenant's .ts.
  "serve": ["agent", "call", "views", "runtime", "client", "wire", "tsx"],
  // src/index.ts: the public surface.
  "": ["agent", "call", "views", "runtime"],
};

/** The table entry for a file: the longest declared prefix of its path. */
function partOf(path: string): string {
  const parts = path.split("/").slice(0, -1);
  for (let depth = parts.length; depth >= 0; depth--) {
    const candidate = parts.slice(0, depth).join("/");
    if (candidate in MAY_IMPORT) return candidate;
  }
  throw new Error(`src/${path} is in no part of the table: give its directory a line`);
}

// Matched after comments are stripped. The third alternative catches dynamic `import("x")`.
const SPECIFIER = /^(?:import|export)[\s\S]*?from\s+"([^"]+)"|^import\s+"([^"]+)"|\bimport\("([^"]+)"\)/gm;

/** Strip comments so prose that names a package is not read as an import. */
function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** Every cross-directory import in src/. */
function edges(): { from: string; to: string; file: string }[] {
  const found: { from: string; to: string; file: string }[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (extname(full) !== ".ts" && extname(full) !== ".tsx") continue;
      const path = relative(SRC, full);
      const from = partOf(path);
      for (const [, named, bare, lazy] of withoutComments(readFileSync(full, "utf8")).matchAll(SPECIFIER)) {
        const spec = named ?? bare ?? lazy;
        if (spec === undefined || spec.startsWith("node:")) continue;
        const to = spec.startsWith(".")
          ? partOf(relative(SRC, resolve(dir, spec)))
          : spec.replace(/^(@[^/]+\/[^/]+|[^@/][^/]*).*$/, "$1");
        if (to !== from) found.push({ from, to, file: path });
      }
    }
  };
  walk(SRC);
  return found;
}

describe("the import table", () => {
  it("is obeyed, line by line", () => {
    const broken = edges()
      .filter(({ from, to }) => !MAY_IMPORT[from]!.includes(to))
      .map(({ from, to, file }) => `src/${file}: ${from || "src"} may not import ${to}`);

    expect([...new Set(broken)].sort()).toEqual([]);
  });

  it("names nothing the tree does not actually import", () => {
    const used = new Set(edges().map(({ from, to }) => `${from} -> ${to}`));
    const idle: string[] = [];
    for (const [part, allowed] of Object.entries(MAY_IMPORT)) {
      for (const one of allowed) {
        if (!used.has(`${part} -> ${one}`)) idle.push(`${part || "src"} -> ${one}`);
      }
    }

    expect(idle, "delete the line, or the import it was written for is missing").toEqual([]);
  });

  it("gives every directory of src/ a line of its own or of its parent", () => {
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        if (!statSync(full).isDirectory()) continue;
        expect(() => partOf(join(relative(SRC, full), "a.ts"))).not.toThrow();
        walk(full);
      }
    };

    walk(SRC);
  });
});
