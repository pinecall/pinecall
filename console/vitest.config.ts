/** The console's suite: what a browser page can be held to in node — an absence, a shape, a pure function. */

import { defineConfig } from "vitest/config";

// There are no UI suites here and there will not be: `tsc` against the DOM and a clean build are
// the gates. What these tests prove is what a rendering cannot — that no key is in the bundle,
// that one file touches storage, that a door's shape is the runtime's, that a fold adds up.
export default defineConfig({
  test: {
    name: "console",
    include: ["test/**/*.test.ts", "test/**/*.test.tsx"],
  },
});
