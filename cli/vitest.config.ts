// The suite: test/ mirrors src/; test/conventions/ holds the canon of CONTRIBUTING.md; the gateway is msw's (test/support/).
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    setupFiles: ["test/support/setup.ts"],
    testTimeout: 20_000,
  },
});
