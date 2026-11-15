// The suite: test/ mirrors src/, and the gateway is a server of the test's own on a free port.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    testTimeout: 20_000,
  },
});
