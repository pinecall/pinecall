/** The suite: the framework, in node, against our own JSX-to-text runtime. */

import { defineConfig } from "vitest/config";

// One program lives in this package now: the framework. The CLI is ../../cli, a package of its
// own. The console — a browser page whose JSX compiles against React's — is a folder of its own
// (../../console), and it took its two directories of tests with it, which is why this config
// has no projects in it any more.
//
// Decorators: measured, not assumed — tsc, esbuild and tsx all take TC39 standard decorators and
// vite's oxc transform does not, so the package is written against the legacy ones. The table and
// the migration are in docs/decisions/agent.md.
//
// JSX: a view is a .tsx file whose factory is our own text runtime, reached by the specifier a
// tenant writes — package.json's exports point at the sources, so nothing here is aliased and
// there is no dist between the source and the test.
export default defineConfig({
  oxc: {
    decorator: { legacy: true },
    jsx: { runtime: "automatic", importSource: "@pinecall/agents/views" },
  },
  test: {
    name: "pinecall",
    include: ["test/**/*.test.ts", "test/**/*.test.tsx"],
  },
});
