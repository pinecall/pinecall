/** The org key is never in the page, the tab's own key lives in one file, and the bundle carries neither. */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

const REPOSITORY = fileURLToPath(new URL("../../..", import.meta.url));
const THE_PAGE = join(REPOSITORY, "console");
// The two directories that ARE the browser: the page, and the core it stands on.
const SOURCES = ["console/src", "packages/core/src"];

// A key read out loud, as the runtime's auth/keys.py mints it: a person's `pc_`, a server's
// `pc_live_` / `pc_test_`, or the `pk_` of before — and the bytes after it. If one of these is ever
// in a built file, somebody put a credential in the bundle.
const SHAPED_LIKE_A_KEY = /\bp[ck]_(?:live_|test_)?[A-Za-z0-9_-]{20,}/;
// The test runs vite itself, and a production build takes seconds, not vitest's default five.
const BUILDING_TAKES_MS = 60_000;

// The two environment names the CLI reads its key from. A build that carries either of them is a
// build that was handed a key at compile time.
const AN_ENVIRONMENT_KEY = /PINECALL_(API|DEV)_KEY/;

// The page holds ONE credential — a person's scoped key — and keeps it in exactly one file,
// `console/src/lib/session-key.ts`, the storage it hands core's `session-key.ts`, which names
// the key and reaches no storage itself. It is the browser's since 2026-09-16 — a login code spends once,
// and a per-tab store left every other tab signed out — so the keys are in localStorage and
// signing out forgets them in every tab, while the world and the corner a tab looks at stay the
// tab's, in sessionStorage, which is why that one file reaches both. There is no second page and
// no second credential any more: the operator's page kept the box's ops key in sessionStorage,
// and the box is operated from the console's own Box screens by a person the box made an
// operator. Two other files reach localStorage and neither keeps a credential: `preferences.ts`
// keeps how wide a person dragged a pane and how they read a call, and core's `theme.ts` whether they flipped the page to
// light or dark (or, in the phone app, which of auto, light and dark they chose).
test("one file reaches a browser's storage", () => {
  expect(sourceFilesReaching("sessionStorage")).toEqual(["console/src/lib/session-key.ts"]);
  expect(sourceFilesReaching("localStorage")).toEqual([
    "console/src/lib/preferences.ts",
    "console/src/lib/session-key.ts",
    "packages/core/src/theme.ts",
  ]);
});

// The key rides one header and that header is spelled in one place: every door goes through
// core's api.ts, and the stream and the recording ask it for the headers rather than
// writing their own.
test("only core's api.ts writes the authorization header", () => {
  expect(sourceFilesReaching("authorization")).toEqual(["packages/core/src/api.ts"]);
});

// The test builds what it greps, into a directory of its own: a check about the bundle that
// depended on somebody having run the build first was a check that passed by being skipped.
test("the built console carries no key of its own", () => {
  const built = builtFiles(buildThePage());
  expect(built.length, "vite built nothing").toBeGreaterThan(0);
  for (const [name, text] of built) {
    expect(text, `${name} carries something shaped like a key`).not.toMatch(SHAPED_LIKE_A_KEY);
    expect(text, `${name} names an environment key`).not.toMatch(AN_ENVIRONMENT_KEY);
  }
}, BUILDING_TAKES_MS);

// A USE and not a mention: the name followed by a dot, a bracket or a colon. Prose is free to say
// which storage the console does not touch and why.
/** Every source file that uses that name, named from the repository's root, so a failure names it. */
function sourceFilesReaching(name: string): string[] {
  const reaching = new RegExp(`\\b${name}\\s*[.[:]`);
  return SOURCES.flatMap((source) => filesUnder(join(REPOSITORY, source)))
    .filter((file) => reaching.test(readFileSync(file, "utf8")))
    .map((file) => relative(REPOSITORY, file))
    .sort();
}

/** The page, built by vite into a fresh directory: the very bundle the gateway would serve. */
function buildThePage(): string {
  const out = mkdtempSync(join(tmpdir(), "pinecall-console-"));
  execFileSync("pnpm", ["exec", "vite", "build", "--outDir", out, "--emptyOutDir", "--logLevel", "error"], {
    cwd: THE_PAGE,
    stdio: "pipe",
  });
  return out;
}

/** The built page and everything it loads, as name and text. */
function builtFiles(built: string): [string, string][] {
  return filesUnder(built)
    .filter((file) => /\.(js|css|html|map)$/.test(file))
    .map((file) => [relative(built, file), readFileSync(file, "utf8")]);
}

function filesUnder(root: string): string[] {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const here = join(root, entry.name);
    return entry.isDirectory() ? filesUnder(here) : [here];
  });
}
