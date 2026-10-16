/** The core's suite: what its pure parts can be held to in node — a parser, a fold, a table. */

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    name: "core",
    include: ["test/**/*.test.ts", "test/**/*.test.tsx"],
  },
});
