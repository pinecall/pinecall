// Vitest reads no tsconfig: the framework's two compiler facts, legacy decorators and its JSX runtime, again.
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: {
    decorator: { legacy: true },
    jsx: { runtime: "automatic", importSource: "@pinecall/agents/views" },
  },
  // Each agent's tests live in its own folder: agents/<name>/test/.
  test: { include: ["agents/*/test/**/*.test.ts", "agents/*/test/**/*.test.tsx"] },
});
